from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Avg, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .access import exam_visible_to, exams_for_student, materials_for_student
from .decorators import role_required
from .forms_app import AnswerUploadForm
from . import models as m


def exam_state(exam, now, sub_status):
    if sub_status == m.Submission.Status.ABSENT:
        return "absent"
    if sub_status:
        return "submitted"
    if now < exam.start_time:
        return "upcoming"
    if now <= exam.end_time:
        return "live"
    if now <= exam.upload_deadline:
        return "upload"
    return "closed"


@role_required("student")
def dashboard(request):
    mine = m.Submission.objects.filter(student=request.user)
    stats = {"exams": exams_for_student(request.user).count(),
             "submitted": mine.filter(status="submitted").count(),
             "absent": mine.filter(status="ABSENT").count()}
    return render(request, "core/student_dashboard.html", {"stats": stats})


@role_required("student")
def available_exams(request):
    exams = list(exams_for_student(request.user))
    subs = dict(m.Submission.objects.filter(student=request.user, exam__in=exams).values_list("exam_id", "status"))
    now = timezone.now()
    rows = [{"exam": e, "state": exam_state(e, now, subs.get(e.id))} for e in exams]
    return render(request, "core/available_exams.html", {"rows": rows})


def _exam_for(request, pk):
    exam = get_object_or_404(m.Exam, pk=pk)
    if not exam_visible_to(request.user, exam):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("This exam is not assigned to your class.")
    return exam


@role_required("student")
def start_exam(request, pk):
    exam = _exam_for(request, pk)
    sub = m.Submission.objects.filter(student=request.user, exam=exam).values_list("status", flat=True).first()
    state = exam_state(exam, timezone.now(), sub)
    if state == "upload":
        return redirect("upload_answer", pk=pk)
    if state != "live":
        messages.warning(request, "This exam is not open right now.")
        return redirect("available_exams")
    return render(request, "core/start_exam.html", {"exam": exam, "end_iso": exam.end_time.strftime("%Y-%m-%dT%H:%M:%S")})


@role_required("student")
def upload_answer(request, pk):
    exam = _exam_for(request, pk)
    now = timezone.now()
    if now < exam.end_time:
        messages.warning(request, "Upload has not started yet.")
        return redirect("available_exams")
    if now > exam.upload_deadline:
        messages.error(request, "Upload time is over.")
        return redirect("available_exams")
    if m.Submission.objects.filter(student=request.user, exam=exam).exists():
        messages.info(request, "You have already submitted this exam.")
        return redirect("available_exams")
    form = AnswerUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            m.Submission.objects.create(student=request.user, exam=exam, file=form.cleaned_data["file"],
                                        submitted_at=now, status="submitted", result_status="pending")
        except IntegrityError:
            messages.info(request, "You have already submitted this exam.")
        else:
            messages.success(request, "Answer uploaded successfully!")
        return redirect("available_exams")
    return render(request, "core/form_page.html", {"title": f"Upload Answer Sheet — {exam.title}", "form": form,
                                                   "multipart": True, "submit": "Submit"})


@role_required("student")
def view_material(request):
    return render(request, "core/view_material.html", {"materials": materials_for_student(request.user)})


@role_required("student")
def history(request):
    rows = m.Submission.objects.filter(student=request.user).select_related("exam").order_by("-id")
    return render(request, "core/history.html", {"rows": rows})


def _published(user):
    return m.Submission.objects.filter(student=user, result_status="published").select_related("exam").order_by("-id")


@role_required("student")
def results(request):
    rows = _published(request.user)
    graded = rows.filter(marks__isnull=False)
    agg = graded.aggregate(avg=Avg("marks"), top=Max("marks"))
    labels = [r.exam.title if r.exam else "Written exam" for r in graded]
    ctx = {"rows": rows, "average": round(agg["avg"] or 0, 2), "highest": agg["top"] or 0, "count": graded.count(),
           "labels": labels, "marks": [r.marks for r in graded]}
    return render(request, "core/results.html", ctx)


@role_required("student")
def download_result(request):
    u = request.user
    lines = ["=" * 37, "         STUDENT RESULT REPORT", "=" * 37, "", f"Name   : {u.name}", f"Email  : {u.email}",
             f"Date   : {timezone.now():%d-%m-%Y %H:%M:%S}", "", "-" * 37]
    rows = list(_published(u))
    total = 0
    for r in rows:
        lines += [f"Exam    : {r.exam.title if r.exam else 'Written exam'}", f"Marks   : {r.marks}", f"Grade   : {r.grade}",
                  f"Remarks : {r.remarks}", "-" * 37]
        total += r.marks or 0
    lines.append("No results available." if not rows else f"\nAverage Marks : {round(total / len(rows), 2)}")
    lines += ["", "=" * 37, "      Generated by Edu System", "=" * 37]
    resp = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="Student_Result.txt"'
    return resp
