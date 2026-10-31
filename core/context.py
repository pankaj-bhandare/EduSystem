from .models import Notification


def unread_notifications(request):
    u = request.user
    if u.is_authenticated:
        return {"unread_count": Notification.objects.filter(user=u, read_at__isnull=True).count()}
    return {}
