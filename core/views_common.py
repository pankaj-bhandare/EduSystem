from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import exam_visible_to, materials_for_student
from .decorators import role_required
from .forms_app import AnnouncementForm
from . import models as m


@login_required
def notifications(request):
    items = m.Notification.objects.filter(user=request.user)[:100]
    return render(request, "core/notifications.html", {"items": items})


@login_required
@require_POST
def mark_notification_read(request, pk):
    m.Notification.objects.filter(pk=pk, user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications")


@role_required("admin", "teacher")
def announcements(request):
    form = AnnouncementForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        roles = {"students": ["student"], "teachers": ["teacher"], "all": ["student", "teacher", "admin"]}[d["target"]]
        users = m.User.objects.filter(role__in=roles, is_active=True)
        m.Notification.objects.bulk_create([m.Notification(user=u, title=d["title"], message=d["message"], category=d["category"]) for u in users])
        messages.success(request, f"Announcement published to {users.count()} account(s).")
        return redirect("announcements")
    return render(request, "core/form_page.html", {"title": "Academic Announcements", "form": form, "submit": "Publish announcement",
                                                   "subtitle": "Publishes an in-app notification to the selected audience."})


# ---- file.php replacement: files are only ever served after a permission check ----
def _send(field, inline=True):
    if not field:
        raise Http404
    try:
        return FileResponse(field.open("rb"), as_attachment=not inline, filename=field.name.split("/")[-1])
    except FileNotFoundError:
        raise Http404


@login_required
def file_material(request, pk):
    mat = get_object_or_404(m.Material, pk=pk)
    u = request.user
    if u.role == "student" and not materials_for_student(u).filter(pk=pk).exists():
        raise Http404
    return _send(mat.file, inline="download" not in request.GET)


@login_required
def file_exam(request, pk):
    exam = get_object_or_404(m.Exam, pk=pk)
    u = request.user
    if u.role == "student" and not (exam.start_time <= timezone.now() and exam_visible_to(u, exam)):
        raise Http404
    return _send(exam.paper_file)


@login_required
def file_submission(request, pk):
    sub = get_object_or_404(m.Submission, pk=pk)
    u = request.user
    if u.role == "student" and sub.student_id != u.id:
        raise Http404
    return _send(sub.file)


@login_required
def file_checked(request, pk):
    sub = get_object_or_404(m.Submission, pk=pk)
    u = request.user
    if u.role == "student" and not (sub.student_id == u.id and sub.result_status == "published"
                                    and sub.verification_status in ("verified", "not_required")):
        raise Http404
    return _send(sub.checked_file)
