from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import models


@admin.register(models.User)
class EduUserAdmin(UserAdmin):
    list_display = ("email", "name", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("email", "name", "reg_no")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (("Edu System", {"fields": ("name", "role", "reg_no", "dob", "gender", "phone", "address", "branch", "academic_year", "division", "semester", "admission_year", "guardian_name", "guardian_phone", "profile_photo")}),)
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "role", "password1", "password2")}),)


for m in (models.Course, models.AcademicClass, models.Subject, models.ClassSubject, models.TeacherClassSubject,
          models.StudentClassEnrollment, models.Material, models.Exam, models.Question, models.McqResult,
          models.Submission, models.Notification, models.IntegrityEvent, models.MonitorImage):
    admin.site.register(m)
