from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views, views_admin, views_common, views_student, views_teacher

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.RoleLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),  # POST only (CSRF-protected)
    path("register/", views.register, name="register"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("reset-password/", views.reset_password, name="reset_password"),

    # shared
    path("notifications/", views_common.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views_common.mark_notification_read, name="mark_notification_read"),
    path("announcements/", views_common.announcements, name="announcements"),
    path("files/material/<int:pk>/", views_common.file_material, name="file_material"),
    path("files/exam/<int:pk>/", views_common.file_exam, name="file_exam"),
    path("files/submission/<int:pk>/", views_common.file_submission, name="file_submission"),
    path("files/checked/<int:pk>/", views_common.file_checked, name="file_checked"),

    # admin
    path("manage/", views_admin.dashboard, name="admin_dashboard"),
    path("manage/users/", views_admin.manage_users, name="manage_users"),
    path("manage/academic/", views_admin.academic_structure, name="academic_structure"),
    path("manage/verify/", views_admin.verify_results, name="verify_results"),
    path("manage/reports/", views_admin.reports, name="reports"),

    # teacher
    path("teacher/", views_teacher.dashboard, name="teacher_dashboard"),
    path("teacher/exams/new/", views_teacher.create_exam, name="create_exam"),
    path("teacher/check/", views_teacher.check_papers, name="check_papers"),
    path("teacher/check/<int:pk>/", views_teacher.check_paper, name="check_paper"),
    path("teacher/check/<int:pk>/annotate/", views_teacher.annotate_paper, name="annotate_paper"),
    path("teacher/check/<int:pk>/annotate/save/", views_teacher.annotate_save, name="annotate_save"),
    path("teacher/materials/new/", views_teacher.upload_material, name="upload_material"),
    path("teacher/questions/new/", views_teacher.add_question, name="add_question"),

    # student
    path("student/", views_student.dashboard, name="student_dashboard"),
    path("student/exams/", views_student.available_exams, name="available_exams"),
    path("student/exams/<int:pk>/start/", views_student.start_exam, name="start_exam"),
    path("student/exams/<int:pk>/upload/", views_student.upload_answer, name="upload_answer"),
    path("student/materials/", views_student.view_material, name="view_material"),
    path("student/history/", views_student.history, name="history"),
    path("student/results/", views_student.results, name="results"),
    path("student/results/download/", views_student.download_result, name="download_result"),
]

# Independent Examination Cell module
from . import views_examcell, examcell_documents
urlpatterns += [
    path("examination-cell/admin/", views_examcell.admin_exam_cell, name="examcell_admin"),
    path("examination-cell/teacher/", views_examcell.teacher_exam_cell, name="examcell_teacher"),
    path("examination-cell/student/", views_examcell.student_exam_cell, name="examcell_student"),
    path("examination-cell/admin/export/registrations.xlsx", examcell_documents.export_exam_registrations, name="examcell_export_registrations"),
    path("examination-cell/admin/import/registrations.xlsx", examcell_documents.import_exam_registrations, name="examcell_import_registrations"),
    path("examination-cell/admin/paper/<int:session_id>/<int:subject_id>/docx/", examcell_documents.generate_question_paper, name="examcell_generate_question_paper"),
    path("examination-cell/admin/export/results.xlsx", examcell_documents.export_exam_results, name="examcell_export_results"),
    path("examination-cell/admin/seating/<int:entry_id>/print/", examcell_documents.print_seating_plan, name="examcell_print_seating"),
    path("examination-cell/student/hall-ticket.pdf", examcell_documents.student_hall_ticket, name="examcell_hall_ticket"),
    path("examination-cell/student/marksheet.pdf", examcell_documents.student_marksheet, name="examcell_marksheet"),
]
