
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django Admin Panel
    path("django-admin/", admin.site.urls),

    # Main application URLs
    path("", include("core.urls")),
]
