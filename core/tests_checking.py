import shutil
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import models as m

PW = "correct horse battery"
PDF = b"%PDF-1.4\n%checked\n"
TMP = tempfile.mkdtemp()


def mk(email, role):
    return m.User.objects.create_user(email=email, password=PW, name=email.split("@")[0].title(), role=role)


def pdf(name="c.pdf", data=PDF):
    return SimpleUploadedFile(name, data, content_type="application/pdf")


@override_settings(MEDIA_ROOT=TMP)
class CheckingFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.admin, self.teacher, self.other_teacher = mk("admin@x.com", "admin"), mk("t@x.com", "teacher"), mk("t2@x.com", "teacher")
        self.s1, self.s2 = mk("s1@x.com", "student"), mk("s2@x.com", "student")
        course = m.Course.objects.create(code="C", name="C")
        self.k1 = m.AcademicClass.objects.create(course=course, name="A", academic_year="26")
        self.k2 = m.AcademicClass.objects.create(course=course, name="B", academic_year="26")
        self.sub1 = m.Subject.objects.create(course=course, code="S1", name="One")
        for k in (self.k1, self.k2):
            m.ClassSubject.objects.create(academic_class=k, subject=self.sub1)
        m.TeacherClassSubject.objects.create(teacher=self.teacher, academic_class=self.k1, subject=self.sub1)
        m.TeacherClassSubject.objects.create(teacher=self.other_teacher, academic_class=self.k2, subject=self.sub1)
        now = timezone.now()
        self.exam = m.Exam(title="ISE-1", academic_class=self.k1, subject=self.sub1, start_time=now - timedelta(hours=5),
                           end_time=now - timedelta(hours=4), upload_deadline=now - timedelta(hours=3))
        self.exam.paper_file.save("p.pdf", pdf(), save=True)
        self.sub = m.Submission(student=self.s1, exam=self.exam, status="submitted", submitted_at=now)
        self.sub.file.save("a.pdf", pdf("a.pdf"), save=True)

    def login(self, u):
        self.client.logout()
        self.assertTrue(self.client.login(username=u.email, password=PW))

    def save_marks(self, marks=72, **extra):
        data = {"marks": marks, "remarks": "Good effort"}
        data.update(extra)
        return self.client.post(reverse("check_paper", args=[self.sub.id]), data, follow=True)

    def test_teacher_checks_paper_and_admin_is_notified(self):
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("check_papers")), "s1@x.com")
        self.assertEqual(self.client.get(reverse("check_paper", args=[self.sub.id])).status_code, 200)
        self.save_marks(72, checked_file=pdf())
        self.sub.refresh_from_db()
        self.assertEqual((self.sub.marks, self.sub.grade, self.sub.result_status, self.sub.verification_status),
                         (72, "B+", "checked", "pending_verification"))
        self.assertTrue(self.sub.checked_file)
        self.assertEqual(m.Notification.objects.filter(user=self.admin, title="Paper awaiting verification").count(), 1)
        # student sees nothing yet
        self.login(self.s1)
        self.assertEqual(self.client.get(reverse("results")).context["count"], 0)
        self.assertEqual(self.client.get(reverse("file_checked", args=[self.sub.id])).status_code, 404)

    def test_validation_and_grade_bands(self):
        self.login(self.teacher)
        self.save_marks(101)
        self.save_marks(-1)
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.marks)
        self.save_marks(60, checked_file=pdf("x.pdf", b"<?php evil ?>"))
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.marks)  # bad checked file rejects the whole save
        for marks, grade in ((95, "A+"), (85, "A"), (75, "B+"), (65, "B"), (55, "C+"), (45, "C"), (40, "D"), (39, "F")):
            self.assertEqual(m.Submission.grade_for(marks), grade)

    def test_teacher_scope_and_role_gates(self):
        self.login(self.other_teacher)  # assigned to class B, not A
        self.assertNotContains(self.client.get(reverse("check_papers")), "s1@x.com")
        self.assertEqual(self.client.get(reverse("check_paper", args=[self.sub.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("check_paper", args=[self.sub.id]), {"marks": 50}).status_code, 404)
        self.login(self.s1)
        self.assertEqual(self.client.get(reverse("check_papers")).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("check_papers")).status_code, 403)
        self.assertEqual(self.client.get(reverse("verify_results")).status_code, 200)
        self.login(self.teacher)
        self.assertEqual(self.client.get(reverse("verify_results")).status_code, 403)

    def test_admin_verify_publishes_and_student_sees_result(self):
        self.login(self.teacher)
        self.save_marks(72, checked_file=pdf())
        self.login(self.admin)
        self.assertContains(self.client.get(reverse("verify_results")), "s1@x.com")
        self.client.post(reverse("verify_results"), {"submission_id": self.sub.id, "action": "verify"})
        self.sub.refresh_from_db()
        self.assertEqual((self.sub.result_status, self.sub.verification_status, self.sub.verified_by), ("published", "verified", self.admin))
        self.assertIsNotNone(self.sub.verified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(m.Notification.objects.filter(user=self.s1, title="Result verified and published").count(), 1)
        # a second verify of the same paper is refused (no duplicate notification)
        self.client.post(reverse("verify_results"), {"submission_id": self.sub.id, "action": "verify"})
        self.assertEqual(m.Notification.objects.filter(user=self.s1, title="Result verified and published").count(), 1)
        self.login(self.s1)
        res = self.client.get(reverse("results"))
        self.assertEqual((res.context["count"], res.context["average"]), (1, 72))
        self.assertContains(res, "Good effort")
        self.assertEqual(self.client.get(reverse("file_checked", args=[self.sub.id])).status_code, 200)
        self.login(self.s2)
        self.assertEqual(self.client.get(reverse("file_checked", args=[self.sub.id])).status_code, 404)
        # teacher can no longer edit a published result
        self.login(self.teacher)
        self.save_marks(10)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.marks, 72)
        self.assertContains(self.client.get(reverse("check_paper", args=[self.sub.id])), "published and can no longer be edited")

    def test_return_flow(self):
        self.login(self.teacher)
        self.save_marks(30)
        self.login(self.admin)
        self.client.post(reverse("verify_results"), {"submission_id": self.sub.id, "action": "return"})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.verification_status, "returned")
        self.assertEqual(self.sub.result_status, "checked")  # still not visible to the student
        self.assertEqual(m.Notification.objects.filter(user=self.teacher, title="Paper returned for review").count(), 1)
        self.assertEqual(m.Notification.objects.filter(user=self.other_teacher, title="Paper returned for review").count(), 0)
        self.assertNotContains(self.client.get(reverse("verify_results")), "s1@x.com")
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("check_papers")), "Returned")
        self.save_marks(55)  # re-check goes back to the admin queue
        self.sub.refresh_from_db()
        self.assertEqual((self.sub.marks, self.sub.verification_status), (55, "pending_verification"))

    def test_annotation_save(self):
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("annotate_paper", args=[self.sub.id])), "annotate/save")
        url = reverse("annotate_save", args=[self.sub.id])
        r = self.client.post(url, {"pdf": pdf("checked.pdf")})
        self.assertEqual(r.json(), {"ok": True})
        self.sub.refresh_from_db()
        self.assertRegex(self.sub.checked_file.name, r"^checked_papers/[0-9a-f]{32}\.pdf$")
        self.assertEqual(self.client.post(url, {"pdf": pdf("x.pdf", b"MZ not a pdf")}).status_code, 422)
        self.assertEqual(self.client.get(url).status_code, 405)
        # CSRF is enforced on the save endpoint
        c = Client(enforce_csrf_checks=True)
        c.login(username=self.teacher.email, password=PW)
        self.assertEqual(c.post(url, {"pdf": pdf()}).status_code, 403)
        # other teachers cannot annotate this paper
        self.login(self.other_teacher)
        self.assertEqual(self.client.post(url, {"pdf": pdf()}).status_code, 404)
        # published papers are locked
        m.Submission.objects.filter(pk=self.sub.pk).update(result_status="published")
        self.login(self.teacher)
        self.assertEqual(self.client.post(url, {"pdf": pdf()}).status_code, 409)
