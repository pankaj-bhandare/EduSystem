import os

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import submissions_for_teacher
from .decorators import role_required
from .forms_app import CheckForm, ExamForm, MaterialForm, QuestionForm
from .notify import notify_admins
from .uploads import clean_upload
from . import models as m


@role_required("teacher")
def dashboard(request):
    stats = {
        "materials": m.Material.objects.filter(uploaded_by=request.user).count(),
        "exams": m.Exam.objects.count(),
        "pending": submissions_for_teacher(request.user).filter(result_status="pending").count(),
    }
    return render(request, "core/teacher_dashboard.html", {"stats": stats})


@role_required("teacher", "admin")
def create_exam(request):
    form = ExamForm(request.POST or None, request.FILES or None, user=request.user)
    if not form.fields["class_subject"].queryset.exists():
        messages.warning(request, "No class/subject is available to you yet. An administrator must create the academic structure and assign you to a class and subject.")
    elif request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Exam created successfully!")
        return redirect("create_exam")
    return render(request, "core/form_page.html", {
        "title": "Create Exam", "form": form, "multipart": True, "submit": "Create Exam",
        "subtitle": "Schedule a written exam and upload the question paper (PDF)."})


@role_required("teacher")
def upload_material(request):
    form = MaterialForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.uploaded_by = request.user
        obj.save()
        messages.success(request, "Material uploaded successfully!")
        return redirect("upload_material")
    return render(request, "core/form_page.html", {
        "title": "Upload Study Material", "form": form, "multipart": True, "submit": "Upload",
        "subtitle": "PDF, image or PowerPoint, up to 10 MB."})


@role_required("teacher")
def add_question(request):
    form = QuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Question added successfully.")
        return redirect("add_question")
    return render(request, "core/form_page.html", {
        "title": "Add MCQ Question", "form": form, "submit": "Save Question",
        "subtitle": "Create a multiple-choice question for the question bank."})


# ---------------------------------------------------------------- checking
def _delete_file(field):
    try:
        if field and field.name:
            field.storage.delete(field.name)
    except OSError:
        pass


def _kind(sub):
    ext = os.path.splitext(sub.file.name or "")[1].lower()
    return "pdf" if ext == ".pdf" else "image" if ext in (".png", ".jpg", ".jpeg") else "other"


@role_required("teacher")
def check_papers(request):
    return render(request, "core/check_papers.html", {"rows": submissions_for_teacher(request.user)})


@role_required("teacher")
def check_paper(request, pk):
    sub = get_object_or_404(submissions_for_teacher(request.user), pk=pk)
    locked = sub.result_status == "published"
    form = CheckForm(request.POST or None, request.FILES or None,
                     initial={"marks": sub.marks, "remarks": sub.remarks})
    if request.method == "POST" and not locked and form.is_valid():
        d = form.cleaned_data
        sub.marks, sub.remarks, sub.grade = d["marks"], d["remarks"], m.Submission.grade_for(d["marks"])
        if d["checked_file"]:
            _delete_file(sub.checked_file)
            sub.checked_file = d["checked_file"]
        sub.result_status = "checked"
        sub.verification_status = "pending_verification"
        sub.save()
        notify_admins("Paper awaiting verification",
                      f"{request.user.name} checked a written paper ({sub.student.email}). Review it in Verify Results before publishing.")
        messages.success(request, "Marks saved and sent to the examination administrator for verification.")
        return redirect("check_papers")
    return render(request, "core/check_paper.html", {"sub": sub, "form": form, "locked": locked, "kind": _kind(sub)})


@role_required("teacher")
def annotate_paper(request, pk):
    sub = get_object_or_404(submissions_for_teacher(request.user), pk=pk)
    kind = _kind(sub)
    if sub.result_status == "published" or kind == "other":
        messages.error(request, "This paper cannot be annotated (it is already published, or not a PDF/image).")
        return redirect("check_paper", pk=pk)
    return render(request, "core/annotate.html", {"sub": sub, "config": {
        "kind": kind, "fileUrl": f"/files/submission/{sub.id}/", "saveUrl": f"/teacher/check/{sub.id}/annotate/save/"}})


@role_required("teacher")
@require_POST
def annotate_save(request, pk):
    sub = get_object_or_404(submissions_for_teacher(request.user), pk=pk)
    if sub.result_status == "published":
        return JsonResponse({"ok": False, "error": "Already published."}, status=409)
    upload = request.FILES.get("pdf")
    if not upload:
        return JsonResponse({"ok": False, "error": "No file."}, status=422)
    from django import forms
    try:
        upload = clean_upload(upload, {"pdf"}, max_mb=64)
    except forms.ValidationError as e:
        return JsonResponse({"ok": False, "error": e.messages[0]}, status=422)
    _delete_file(sub.checked_file)
    sub.checked_file = upload
    sub.save(update_fields=["checked_file"])
    return JsonResponse({"ok": True})
