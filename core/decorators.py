from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """requireUserRole(): not logged in -> login page; wrong role -> 403 'Access denied'."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied("Access denied.")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
