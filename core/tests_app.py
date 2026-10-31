import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import models as m

PW = "correct horse battery"
PDF = b"%PDF-1.4\n%test file\n"
TMP = tempfile.mkdtemp()


def mk(email, role):
    return m.User.objects.create_user(email=email, password=PW, name=email.split("@")[0].title(), role=role)


def pdf(name="x.pdf", data=PDF):
    return SimpleUploadedFile(name, data, content_type="application/pdf")


def dt(delta):
    return (timezone.now() + delta).strftime("%Y-%m-%dT%H:%M")


@override_settings(MEDIA_ROOT=TMP)
class AppFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.admin, self.teacher = mk("admin@x.com", "admin"), mk("teach@x.com", "teacher")
        self.s1, self.s2 = mk("s1@x.com", "student"), mk("s2@x.com", "student")
        self.course = m.Course.objects.create(code="BTECH", name="B.Tech E&TC")
        self.other_course = m.Course.objects.create(code="MBA", name="MBA")
        self.klass = m.AcademicClass.objects.create(course=self.course, name="VII Sem", academic_year="2026-27")
        self.subject = m.Subject.objects.create(course=self.course, code="PEC411", name="DMDW")
        m.ClassSubject.objects.create(academic_class=self.klass, subject=self.subject)
        m.TeacherClassSubject.objects.create(teacher=self.teacher, academic_class=self.klass, subject=self.subject)
        m.StudentClassEnrollment.objects.create(student=self.s1, academic_class=self.klass)  # s2 NOT enrolled

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(username=user.email, password=PW))

    # ---------------- admin
    def test_admin_pages_render_and_are_admin_only(self):
        self.login(self.admin)
        for name in ("admin_dashboard", "manage_users", "academic_structure", "reports", "announcements", "notifications"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.login(self.teacher)
        for name in ("admin_dashboard", "manage_users", "academic_structure", "reports"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_admin_builds_structure_through_forms(self):
        self.login(self.admin)
        post = lambda data: self.client.post(reverse("academic_structure"), data, follow=True)
        post({"action": "add_course", "code": "mca", "name": "MCA", "description": ""})
        c = m.Course.objects.get(code="MCA")  # upper-cased
        post({"action": "add_class", "course": c.id, "name": "Sem 1", "section": "", "academic_year": "2026-27"})
        post({"action": "add_subject", "course": c.id, "code": "py101", "name": "Python", "description": ""})
        k, s = m.AcademicClass.objects.get(course=c), m.Subject.objects.get(code="PY101")
        post({"action": "assign_subject", "academic_class": k.id, "subject": s.id})
        post({"action": "assign_teacher", "teacher": self.teacher.id, "academic_class": k.id, "subject": s.id})
        post({"action": "enroll_student", "student": self.s2.id, "academic_class": k.id})
        self.assertTrue(m.ClassSubject.objects.filter(academic_class=k, subject=s).exists())
        self.assertTrue(m.TeacherClassSubject.objects.filter(teacher=self.teacher, subject=s).exists())
        self.assertTrue(m.StudentClassEnrollment.objects.filter(student=self.s2, academic_class=k).exists())
        # a subject from a different course cannot be assigned to this class
        r = post({"action": "assign_subject", "academic_class": k.id, "subject": self.subject.id})
        self.assertFalse(m.ClassSubject.objects.filter(academic_class=k, subject=self.subject).exists())
        # duplicate course code is rejected, not a crash
        post({"action": "add_course", "code": "MCA", "name": "dup", "description": ""})
        self.assertEqual(m.Course.objects.filter(code="MCA").count(), 1)

    def test_user_management_rules(self):
        self.login(self.admin)
        url = reverse("manage_users")
        self.client.post(url, {"action": "create_teacher", "name": "New Teacher", "email": "NT@x.com", "password": PW, "confirm": PW})
        self.assertEqual(m.User.objects.get(email="nt@x.com").role, "teacher")
        # last active admin is protected
        self.client.post(url, {"action": "toggle_status", "user_id": self.admin.id})
        self.client.post(url, {"action": "update_role", "user_id": self.admin.id, "role": "student"})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.role, "admin")
        # deactivating a student works, and they can no longer log in
        self.client.post(url, {"action": "toggle_status", "user_id": self.s1.id})
        self.client.logout()
        r = self.client.post(reverse("login"), {"username": "s1@x.com", "password": PW})
        self.assertContains(r, "deactivated")
        # weak admin-set passwords are refused
        self.login(self.admin)
        self.client.post(url, {"action": "reset_password", "user_id": self.s2.id, "password": "short", "confirm": "short"})
        self.assertTrue(self.s2.__class__.objects.get(pk=self.s2.pk).check_password(PW))

    # ---------------- teacher
    def exam_post(self, **over):
        data = {"title": "ISE-1", "class_subject": m.ClassSubject.objects.get().id, "start_time": dt(timedelta(hours=-1)),
                "end_time": dt(timedelta(hours=1)), "upload_deadline": dt(timedelta(hours=3)), "paper": pdf()}
        data.update(over)
        return self.client.post(reverse("create_exam"), data, follow=True)

    def test_teacher_creates_exam_and_bad_files_are_rejected(self):
        self.login(self.teacher)
        self.exam_post()
        exam = m.Exam.objects.get()
        self.assertEqual(exam.academic_class, self.klass)
        self.assertRegex(exam.paper_file.name, r"^exam_papers/[0-9a-f]{32}\.pdf$")  # random name
        self.exam_post(title="fake", paper=pdf("evil.pdf", b"<?php echo 1; ?>"))
        self.exam_post(title="dates", end_time=dt(timedelta(hours=-2)))
        self.assertEqual(m.Exam.objects.count(), 1)

    def test_teacher_only_sees_assigned_class_subjects(self):
        other = mk("t2@x.com", "teacher")
        self.login(other)
        r = self.client.get(reverse("create_exam"))
        self.assertContains(r, "No class/subject is available")

    def test_material_upload_visibility_and_file_access(self):
        self.login(self.teacher)
        self.client.post(reverse("upload_material"), {"course": self.course.id, "subject": "", "title": "Unit 1 notes", "file": pdf()})
        self.client.post(reverse("upload_material"), {"course": self.other_course.id, "subject": "", "title": "MBA notes", "file": pdf()})
        self.client.post(reverse("upload_material"), {"course": self.course.id, "title": "bad", "file": pdf("a.pdf", b"not a pdf")})
        self.assertEqual(m.Material.objects.count(), 2)
        mine, theirs = m.Material.objects.get(title="Unit 1 notes"), m.Material.objects.get(title="MBA notes")
        self.login(self.s1)
        page = self.client.get(reverse("view_material"))
        self.assertContains(page, "Unit 1 notes")
        self.assertNotContains(page, "MBA notes")
        self.assertEqual(self.client.get(reverse("file_material", args=[mine.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("file_material", args=[theirs.id])).status_code, 404)
        self.login(self.s2)  # not enrolled anywhere
        self.assertEqual(self.client.get(reverse("file_material", args=[mine.id])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("file_material", args=[mine.id])).status_code, 302)

    # ---------------- student exam flow
    def make_exam(self, start, end, deadline, cls="set"):
        now = timezone.now()
        e = m.Exam(title="Exam", academic_class=self.klass if cls == "set" else None, subject=self.subject,
                   start_time=now + start, end_time=now + end, upload_deadline=now + deadline)
        e.paper_file.save("p.pdf", pdf(), save=True)
        return e

    def test_exam_states_paper_access_and_upload(self):
        live = self.make_exam(timedelta(hours=-1), timedelta(hours=1), timedelta(hours=2))
        self.login(self.s1)
        self.assertContains(self.client.get(reverse("available_exams")), "Start Exam")
        self.assertEqual(self.client.get(reverse("start_exam", args=[live.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("file_exam", args=[live.id])).status_code, 200)
        self.client.get(reverse("upload_answer", args=[live.id]))
        self.assertEqual(m.Submission.objects.count(), 0)  # cannot upload while exam is live
        # non-enrolled student: 403 on exam pages, 404 on the paper
        self.login(self.s2)
        self.assertEqual(self.client.get(reverse("start_exam", args=[live.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("file_exam", args=[live.id])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("available_exams")), "Exam<")
        # future exam: paper not downloadable yet
        future = self.make_exam(timedelta(hours=2), timedelta(hours=3), timedelta(hours=4))
        self.login(self.s1)
        self.assertEqual(self.client.get(reverse("file_exam", args=[future.id])).status_code, 404)
        # upload window
        upl = self.make_exam(timedelta(hours=-3), timedelta(hours=-1), timedelta(hours=1))
        self.assertContains(self.client.get(reverse("available_exams")), "Upload Answer")
        r = self.client.post(reverse("upload_answer", args=[upl.id]), {"file": pdf("ans.pdf")}, follow=True)
        sub = m.Submission.objects.get(exam=upl, student=self.s1)
        self.assertEqual(sub.status, "submitted")
        self.client.post(reverse("upload_answer", args=[upl.id]), {"file": pdf("ans2.pdf")})
        self.assertEqual(m.Submission.objects.filter(exam=upl).count(), 1)  # one submission only
        # own answer sheet: owner and teacher yes, other student no
        self.assertEqual(self.client.get(reverse("file_submission", args=[sub.id])).status_code, 200)
        self.login(self.s2)
        self.assertEqual(self.client.get(reverse("file_submission", args=[sub.id])).status_code, 404)
        self.login(self.teacher)
        self.assertEqual(self.client.get(reverse("file_submission", args=[sub.id])).status_code, 200)
        # closed
        closed = self.make_exam(timedelta(hours=-5), timedelta(hours=-4), timedelta(hours=-3))
        self.login(self.s1)
        self.assertContains(self.client.get(reverse("available_exams")), "Closed")

    def test_results_show_only_published_and_history_hides_unpublished_marks(self):
        ex = self.make_exam(timedelta(hours=-5), timedelta(hours=-4), timedelta(hours=-3))
        ex2 = self.make_exam(timedelta(hours=-6), timedelta(hours=-5), timedelta(hours=-4))
        m.Submission.objects.create(student=self.s1, exam=ex, status="submitted", result_status="checked", marks=88, grade="A", remarks="secret-unpublished")
        m.Submission.objects.create(student=self.s1, exam=ex2, status="submitted", result_status="published", verification_status="verified", marks=70, grade="B+", remarks="well done")
        self.login(self.s1)
        res = self.client.get(reverse("results"))
        self.assertContains(res, "well done")
        self.assertNotContains(res, "secret-unpublished")
        self.assertEqual(res.context["count"], 1)
        self.assertEqual(res.context["average"], 70)
        hist = self.client.get(reverse("history"))
        self.assertNotContains(hist, "secret-unpublished")
        self.assertNotContains(hist, ">88<")
        txt = self.client.get(reverse("download_result"))
        self.assertContains(txt, "Marks   : 70")
        self.assertNotContains(txt, "88")

    def test_checked_paper_only_when_published(self):
        ex = self.make_exam(timedelta(hours=-5), timedelta(hours=-4), timedelta(hours=-3))
        sub = m.Submission.objects.create(student=self.s1, exam=ex, status="submitted", result_status="checked", marks=50, verification_status="pending_verification")
        sub.checked_file.save("c.pdf", pdf(), save=True)
        self.login(self.s1)
        self.assertEqual(self.client.get(reverse("file_checked", args=[sub.id])).status_code, 404)
        m.Submission.objects.filter(pk=sub.pk).update(result_status="published", verification_status="verified")
        self.assertEqual(self.client.get(reverse("file_checked", args=[sub.id])).status_code, 200)

    # ---------------- admin reports / announcements
    def test_mark_absent_only_for_class_students_and_announcements(self):
        old = self.make_exam(timedelta(hours=-5), timedelta(hours=-4), timedelta(hours=-3))
        self.login(self.admin)
        self.client.post(reverse("reports"), {"action": "mark_absent"})
        self.assertEqual(list(m.Submission.objects.filter(status="ABSENT").values_list("student__email", flat=True)), ["s1@x.com"])  # s2 not in class
        self.assertContains(self.client.get(reverse("reports")), "Exam")
        self.client.post(reverse("announcements"), {"title": "Holiday", "message": "College closed Friday", "target": "students", "category": "general"})
        self.assertEqual(m.Notification.objects.filter(title="Holiday").count(), 2)
        self.login(self.s1)
        page = self.client.get(reverse("notifications"))
        self.assertContains(page, "College closed Friday")
        n = m.Notification.objects.get(user=self.s1)
        self.client.post(reverse("mark_notification_read", args=[n.id]))
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)
        self.login(self.teacher)  # teachers can address students only
        self.client.post(reverse("announcements"), {"title": "To all", "message": "hello there", "target": "all", "category": "general"})
        self.assertEqual(m.Notification.objects.filter(title="To all").count(), 0)
