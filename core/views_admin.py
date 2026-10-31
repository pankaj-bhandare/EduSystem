from django.contrib import messages
from django.contrib.auth import password_validation
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import role_required
from .notify import email_user, notify
from .forms_app import (ClassForm, ClassSubjectForm, CourseForm, EnrollForm, PasswordSetForm, SubjectForm,
                        TeacherAssignForm, TeacherCreateForm)
from . import models as m


@role_required("admin")
def dashboard(request):
    sub = m.Submission.objects
    stats = {
        "students": m.User.objects.filter(role="student").count(),
        "teachers": m.User.objects.filter(role="teacher").count(),
        "admins": m.User.objects.filter(role="admin").count(),
        "exams": m.Exam.objects.count(),
        "submissions": sub.count(),
        "published": sub.filter(result_status="published").count(),
        "pending": sub.filter(result_status="pending").count(),
        "awaiting_verification": sub.filter(verification_status="pending_verification").count(),
    }
    chart = [stats["students"], stats["teachers"], stats["exams"], stats["submissions"], stats["published"]]
    return render(request, "core/admin_dashboard.html", {"stats": stats, "chart": chart})


def _active_admins():
    return m.User.objects.filter(role="admin", is_active=True).count()


@role_required("admin")
def manage_users(request):
    create_form = TeacherCreateForm()
    pw_errors = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_teacher":
            create_form = TeacherCreateForm(request.POST)
            if create_form.is_valid():
                create_form.save()
                messages.success(request, "Teacher account created.")
                return redirect("manage_users")
        else:
            target = get_object_or_404(m.User, pk=request.POST.get("user_id"))
            last_admin = target.role == "admin" and target.is_active and _active_admins() <= 1
            if action == "update_role":
                new_role = request.POST.get("role")
                if new_role not in dict(m.User.Role.choices):
                    messages.error(request, "Invalid role.")
                elif last_admin and new_role != "admin":
                    messages.error(request, "You cannot demote the last active administrator.")
                else:
                    target.role = new_role
                    target.is_staff = target.is_staff if new_role != "admin" else target.is_staff
                    target.save(update_fields=["role"])
                    messages.success(request, f"{target.email} is now {new_role}.")
            elif action == "toggle_status":
                if last_admin:
                    messages.error(request, "You cannot deactivate the last active administrator.")
                else:
                    target.is_active = not target.is_active
                    target.save(update_fields=["is_active"])
                    messages.success(request, f"{target.email} {'activated' if target.is_active else 'deactivated'}.")
            elif action == "reset_password":
                f = PasswordSetForm(request.POST, user=target)
                if f.is_valid():
                    target.set_password(f.cleaned_data["password"])
                    target.save(update_fields=["password"])
                    messages.success(request, f"Password reset for {target.email}.")
                else:
                    messages.error(request, " ".join(e for errs in f.errors.values() for e in errs))
            return redirect("manage_users")
    q = request.GET.get("q", "").strip()
    users = m.User.objects.order_by("role", "name")
    if q:
        users = users.filter(Q(email__icontains=q) | Q(name__icontains=q) | Q(reg_no__icontains=q))
    return render(request, "core/manage_users.html", {
        "users": users, "create_form": create_form, "q": q, "pw_form": PasswordSetForm(),
        "roles": m.User.Role.choices})


STRUCTURE_FORMS = [
    ("add_course", "Add course", CourseForm, "Course added."),
    ("add_class", "Add class", ClassForm, "Class added."),
    ("add_subject", "Add subject", SubjectForm, "Subject added."),
    ("assign_subject", "Assign subject to class", ClassSubjectForm, "Subject assigned to the class."),
    ("assign_teacher", "Assign teacher to class + subject", TeacherAssignForm, "Teacher assigned."),
    ("enroll_student", "Enroll student in class", EnrollForm, "Student enrolled."),
]


@role_required("admin")
def academic_structure(request):
    posted = request.POST.get("action") if request.method == "POST" else None
    panels = []
    for action, title, form_cls, ok in STRUCTURE_FORMS:
        if posted == action:
            form = form_cls(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, ok)
                return redirect("academic_structure")
        else:
            form = form_cls()
        panels.append({"action": action, "title": title, "form": form, "open": posted == action})
    ctx = {
        "panels": panels,
        "courses": m.Course.objects.annotate(n_classes=Count("classes", distinct=True), n_subjects=Count("subjects", distinct=True)),
        "classes": m.AcademicClass.objects.select_related("course").annotate(n_students=Count("enrollments", distinct=True)),
        "class_subjects": m.ClassSubject.objects.select_related("academic_class__course", "subject").order_by("academic_class__course__code"),
        "teacher_assignments": m.TeacherClassSubject.objects.select_related("teacher", "academic_class", "subject"),
    }
    return render(request, "core/academic_structure.html", ctx)


@role_required("admin")
def reports(request):
    if request.method == "POST" and request.POST.get("action") == "mark_absent":
        marked = 0
        now = timezone.now()
        for exam in m.Exam.objects.filter(upload_deadline__lt=now):
            students = m.User.objects.filter(role="student", is_active=True)
            if exam.academic_class_id:  # only students of the exam's class (the PHP marked everyone)
                students = students.filter(enrollments__academic_class_id=exam.academic_class_id)
            done = m.Submission.objects.filter(exam=exam).values_list("student_id", flat=True)
            new = [m.Submission(student=s, exam=exam, status=m.Submission.Status.ABSENT) for s in students.exclude(id__in=done)]
            m.Submission.objects.bulk_create(new)
            marked += len(new)
        messages.success(request, f"Absent check completed: {marked} student(s) marked absent.")
        return redirect("reports")
    summary = {
        "students": m.User.objects.filter(role="student").count(),
        "teachers": m.User.objects.filter(role="teacher").count(),
        "exams": m.Exam.objects.count(),
        "submissions": m.Submission.objects.count(),
        "published": m.Submission.objects.filter(result_status="published").count(),
    }
    exams = m.Exam.objects.annotate(
        n_sub=Count("submission"),
        n_absent=Count("submission", filter=Q(submission__status="ABSENT")),
        avg_marks=Avg("submission__marks"),
    ).order_by("-start_time")
    return render(request, "core/reports.html", {"summary": summary, "exams": exams})


@role_required("admin")
def verify_results(request):
    if request.method == "POST":
        action = request.POST.get("action")
        pending = m.Submission.objects.filter(pk=request.POST.get("submission_id"), result_status="checked",
                                              verification_status="pending_verification", marks__isnull=False)
        sub = pending.select_related("student", "exam").first()
        if action not in ("verify", "return") or not sub:
            messages.error(request, "This paper is no longer awaiting verification.")
        elif action == "verify":
            # conditional update so two admins cannot publish the same paper twice
            done = pending.update(result_status="published", verification_status="verified",
                                  verified_by=request.user, verified_at=timezone.now())
            if done:
                notify([sub.student], "Result verified and published",
                       "Your written-exam result has been verified by the examination administrator and is now available.")
                email_user(sub.student, "Edu System: Result verified",
                           "Your written-exam result has been verified and published. Please log in to view it.")
                messages.success(request, "Result verified and published.")
        else:
            if pending.update(verification_status="returned"):
                exam = sub.exam
                teachers = m.User.objects.filter(role="teacher", is_active=True)
                if exam and exam.academic_class_id:
                    teachers = teachers.filter(teaching_assignments__academic_class_id=exam.academic_class_id,
                                               teaching_assignments__subject_id=exam.subject_id)
                notify(teachers.distinct(), "Paper returned for review",
                       f"The administrator returned the paper of {sub.student.email} for re-checking.")
                messages.success(request, "Paper returned for teacher review.")
        return redirect("verify_results")
    rows = (m.Submission.objects.filter(result_status="checked", verification_status="pending_verification")
            .select_related("student", "exam").order_by("-id"))
    return render(request, "core/verify_results.html", {"rows": rows})
