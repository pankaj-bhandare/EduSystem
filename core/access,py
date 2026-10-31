"""Who may see what (the visibility rules that were repeated across the PHP pages)."""
from django.db.models import Q

from .models import AcademicClass, ClassSubject, Exam, Material


def student_classes(user):
    return AcademicClass.objects.filter(enrollments__student=user, is_active=True, course__is_active=True)


def materials_for_student(user):
    classes = student_classes(user)
    assigned_subjects = ClassSubject.objects.filter(academic_class__in=classes).values("subject_id")
    return (Material.objects
            .filter(course_id__in=classes.values("course_id"))
            .filter(Q(subject__isnull=True) | Q(subject_id__in=assigned_subjects))
            .select_related("course", "subject").distinct().order_by("-id"))


def exams_for_student(user):
    return (Exam.objects
            .filter(Q(academic_class__isnull=True) | Q(academic_class__enrollments__student=user))
            .select_related("subject").distinct().order_by("start_time"))


def exam_visible_to(user, exam):
    return exam.academic_class_id is None or exam.academic_class.enrollments.filter(student=user).exists()


def submissions_for_teacher(user):
    """Answer sheets a teacher may check: exams of their assigned class+subject (or open-to-all exams)."""
    from django.db.models import Exists, OuterRef
    from .models import Submission, TeacherClassSubject
    assigned = TeacherClassSubject.objects.filter(
        teacher=user, academic_class=OuterRef("exam__academic_class"), subject=OuterRef("exam__subject"))
    return (Submission.objects.filter(status="submitted")
            .filter(Q(exam__academic_class__isnull=True) | Exists(assigned))
            .select_related("student", "exam").order_by("-id"))
