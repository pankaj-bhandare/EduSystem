from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from . import models as m
from .decorators import role_required
from .forms_examcell import ExamSessionForm, ExamRegistrationForm, ExamTimetableEntryForm


def _counts():
    students = m.User.objects.filter(role="student", is_active=True)
    return {
        "regular_students": students.count(),
        "backlog_students": m.ExamRegistration.objects.filter(session__candidate_type="backlog", status="approved").values("student_id").distinct().count(),
        "sessions": m.ExamSession.objects.count(),
        "pending_forms": m.ExamRegistration.objects.filter(status="pending").count(),
        "published_timetable": m.ExamTimetableEntry.objects.filter(published=True).count(),
        "results_pending": m.ExamCellResult.objects.filter(published=False).count(),
    }

@role_required("admin")
def admin_exam_cell(request):
    session_form = ExamSessionForm(request.POST or None, prefix="session")
    timetable_form = ExamTimetableEntryForm(request.POST or None, prefix="timetable")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_session" and session_form.is_valid():
            obj = session_form.save(commit=False); obj.created_by = request.user; obj.save()
            messages.success(request, "Examination session created. Default marks and duration were applied.")
            return redirect("examcell_admin")
        if action == "add_timetable" and timetable_form.is_valid():
            timetable_form.save(); messages.success(request, "Timetable entry saved as unpublished.")
            return redirect("examcell_admin")
        if action in ("approve_registration", "reject_registration"):
            reg = get_object_or_404(m.ExamRegistration, pk=request.POST.get("registration_id"))
            reg.status = "approved" if action == "approve_registration" else "rejected"
            reg.reviewed_by, reg.reviewed_at = request.user, timezone.now(); reg.save()
            messages.success(request, f"Registration {reg.get_status_display().lower()}.")
            return redirect("examcell_admin")
        if action == "publish_timetable":
            m.ExamTimetableEntry.objects.filter(pk=request.POST.get("entry_id")).update(published=True)
            messages.success(request, "Timetable entry published."); return redirect("examcell_admin")
        if action == "publish_result":
            m.ExamCellResult.objects.filter(pk=request.POST.get("result_id")).update(published=True)
            messages.success(request, "Result published."); return redirect("examcell_admin")
    regs = m.ExamRegistration.objects.select_related("student", "session", "subject").order_by("-submitted_at")[:100]
    entries = m.ExamTimetableEntry.objects.select_related("session", "subject", "invigilator")
    return render(request, "core/examcell_admin.html", {"stats": _counts(), "session_form": session_form, "timetable_form": timetable_form,
        "sessions": m.ExamSession.objects.annotate(reg_count=Count("registrations")), "registrations": regs, "entries": entries,
        "regular_count": m.User.objects.filter(role="student", is_active=True).count(),
        "backlog_count": m.ExamRegistration.objects.filter(session__candidate_type="backlog").values("student_id").distinct().count(), "subjects": m.Subject.objects.order_by("code")})

@role_required("teacher")
def teacher_exam_cell(request):
    assignments = m.TeacherClassSubject.objects.filter(teacher=request.user).select_related("academic_class", "subject")
    entries = m.ExamTimetableEntry.objects.filter(invigilator=request.user).select_related("session", "subject")
    return render(request, "core/examcell_teacher.html", {"assignments": assignments, "entries": entries,
        "papers": m.Exam.objects.filter(Q(academic_class__in=assignments.values("academic_class")) | Q(academic_class__isnull=True)).select_related("subject", "academic_class")})

@role_required("student")
def student_exam_cell(request):
    if request.method == "POST" and request.POST.get("action") == "register":
        session = get_object_or_404(m.ExamSession, pk=request.POST.get("session_id"))
        if session.candidate_type == "regular" and request.user.semester and str(session.semester) != str(request.user.semester):
            messages.error(request, "This regular examination session is not for your semester.")
        else:
            m.ExamRegistration.objects.get_or_create(session=session, student=request.user, subject_id=request.POST.get("subject_id") or None,
                defaults={"backlog_semester": request.POST.get("backlog_semester", "")})
            messages.success(request, "Examination registration submitted for review.")
        return redirect("examcell_student")
    registrations = m.ExamRegistration.objects.filter(student=request.user).select_related("session", "subject").order_by("-submitted_at")
    timetable = m.ExamTimetableEntry.objects.filter(published=True).filter(session__registrations__student=request.user).select_related("session", "subject").distinct()
    sessions = m.ExamSession.objects.filter(status__in=["registration", "scheduled", "published"])
    return render(request, "core/examcell_student.html", {"registrations": registrations, "timetable": timetable, "sessions": sessions,
        "results": m.ExamCellResult.objects.filter(registration__student=request.user, published=True).select_related("registration__session", "registration__subject")})
