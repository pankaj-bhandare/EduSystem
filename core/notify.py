from django.core.mail import send_mail

from . import models as m


def notify(users, title, message, category="result"):
    m.Notification.objects.bulk_create([m.Notification(user=u, title=title, message=message, category=category) for u in users])


def notify_admins(title, message):
    notify(m.User.objects.filter(role="admin", is_active=True), title, message)


def email_user(user, subject, body):
    send_mail(subject, body, None, [user.email], fail_silently=True)  # never block the workflow on mail
