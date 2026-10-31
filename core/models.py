"""
Django models for Edu System, derived from the tables and columns used in the PHP code.
Put this in an app (e.g. `core/models.py`) and set in settings.py:
    AUTH_USER_MODEL = "core.User"
Checked against database/001-008 SQL. Only the original users/exams/submissions/materials/questions/results
tables (created before 001) were not provided, so those columns are inferred from the PHP code.
"""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------- users
class EmailUserManager(UserManager):
    def _create_user(self, email, password, **extra):
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """PHP `users` table. Login is by email; `is_active` already exists on AbstractUser."""

    class Role(models.TextChoices):
        STUDENT = "student"
        TEACHER = "teacher"
        ADMIN = "admin"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)

    # Student profile fields (profile.php)
    reg_no = models.CharField(max_length=50, unique=True, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    branch = models.CharField(max_length=100, blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    division = models.CharField(max_length=20, blank=True)
    semester = models.CharField(max_length=20, blank=True)
    admission_year = models.CharField(max_length=10, blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(upload_to="profile_photos/", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]
    objects = EmailUserManager()

    def __str__(self):
        return f"{self.name} <{self.email}>"


# ------------------------------------------------------ academic structure
class Course(models.Model):  # academic_courses
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class AcademicClass(models.Model):  # academic_classes
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=100)
    section = models.CharField(max_length=30, blank=True)
    academic_year = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    subjects = models.ManyToManyField("Subject", through="ClassSubject", related_name="classes")

    class Meta:
        unique_together = [("course", "name", "section", "academic_year")]

    def __str__(self):
        return f"{self.name} {self.section} ({self.academic_year})".replace("  ", " ")


class Subject(models.Model):  # academic_subjects
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="subjects")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("course", "code")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class ClassSubject(models.Model):  # class_subjects
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.CASCADE, db_column="class_id")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("academic_class", "subject")]

    def clean(self):
        # PHP rule: class and subject must belong to the same course
        from django.core.exceptions import ValidationError
        if not (self.academic_class_id and self.subject_id):
            return
        if self.academic_class.course_id != self.subject.course_id:
            raise ValidationError("Class and subject must belong to the same course.")


class TeacherClassSubject(models.Model):  # teacher_class_subjects
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, limit_choices_to={"role": "teacher", "is_active": True},
        related_name="teaching_assignments",
    )
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("teacher", "academic_class", "subject")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.academic_class_id and self.subject_id and not ClassSubject.objects.filter(
                academic_class_id=self.academic_class_id, subject_id=self.subject_id).exists():
            raise ValidationError("That subject is not assigned to the selected class.")


class StudentClassEnrollment(models.Model):  # student_class_enrollments
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, limit_choices_to={"role": "student"},
        related_name="enrollments",
    )
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.PROTECT, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("student", "academic_class")]


# ---------------------------------------------------------------- materials
class Material(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True)  # NULL = whole course
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="materials/")  # pdf, jpg, png, ppt, pptx
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="materials")
    created_at = models.DateTimeField(auto_now_add=True)  # inferred


# -------------------------------------------------------------------- exams
class Exam(models.Model):
    title = models.CharField(max_length=200)
    academic_class = models.ForeignKey(AcademicClass, on_delete=models.PROTECT, null=True, blank=True)  # NULL = open to all
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True)
    paper_file = models.FileField(upload_to="exam_papers/")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    upload_deadline = models.DateTimeField()

    class Meta:
        ordering = ["start_time"]


class Question(models.Model):  # questions (MCQ bank)
    question = models.TextField()
    option1 = models.CharField(max_length=500)
    option2 = models.CharField(max_length=500)
    option3 = models.CharField(max_length=500)
    option4 = models.CharField(max_length=500)
    correct_option = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4")])


class McqResult(models.Model):  # results
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mcq_results")
    score = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)  # inferred


class Submission(models.Model):
    """submissions: written answer sheets, plus ABSENT markers. Replaces `written_exam` too."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        ABSENT = "ABSENT"

    class ResultStatus(models.TextChoices):
        PENDING = "pending"
        CHECKED = "checked"
        PUBLISHED = "published"

    class Verification(models.TextChoices):
        NOT_REQUIRED = "not_required"
        PENDING = "pending_verification"
        VERIFIED = "verified"
        RETURNED = "returned"

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submissions")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True)  # NULL for written_exam.php uploads
    file = models.FileField(upload_to="submissions/", blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)

    marks = models.PositiveSmallIntegerField(null=True, blank=True)
    grade = models.CharField(max_length=3, blank=True)
    remarks = models.CharField(max_length=1000, blank=True)
    result_status = models.CharField(max_length=20, choices=ResultStatus.choices, default=ResultStatus.PENDING)
    checked_file = models.FileField(upload_to="checked_papers/", blank=True)

    verification_status = models.CharField(max_length=30, choices=Verification.choices, default=Verification.NOT_REQUIRED)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_submissions")
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # PHP checked "already submitted" in code; enforce it in the DB instead
            models.UniqueConstraint(fields=["student", "exam"], name="one_submission_per_student_exam"),
        ]

    @staticmethod
    def grade_for(marks: int) -> str:
        """Same bands as check_papers.php (note: PHP gives 41-49 'C', 40 'D')."""
        if marks >= 90: return "A+"
        if marks >= 80: return "A"
        if marks >= 70: return "B+"
        if marks >= 60: return "B"
        if marks >= 50: return "C+"
        if marks > 40:  return "C"
        if marks == 40: return "D"
        return "F"


# ------------------------------------------------- notifications & integrity
class Notification(models.Model):  # user_notifications
    CATEGORIES = ["announcement", "assignment", "exam", "result", "deadline", "general"]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=180)
    message = models.TextField(max_length=4000)
    category = models.CharField(max_length=40, choices=[(c, c.title()) for c in CATEGORIES], default="announcement")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class IntegrityEvent(models.Model):  # exam_integrity_events
    EVENT_TYPES = ["camera_denied", "camera_ready", "fullscreen_exit", "tab_hidden", "window_blur"]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=30, choices=[(e, e) for e in EVENT_TYPES])
    detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MonitorImage(models.Model):  # exam_monitor_images
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="monitor/")  # serve through a permission-checked view, not MEDIA_URL
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at"]


# ------------------------------------------------------------ password reset
class PasswordResetOTP(models.Model):
    """PHP `otp_verify`. Code is stored hashed; attempts are counted in the DB (the PHP kept
    the counter in the session, which an attacker could reset by dropping the cookie)."""
    email = models.EmailField(db_index=True)
    otp_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

# ---------------------------------------------------- Examination Cell module
class ExamSession(models.Model):
    """An examination-cell session (regular or backlog) for an academic term."""
    class Kind(models.TextChoices):
        ISE1 = "ISE-1", "ISE-1"
        ISE2 = "ISE-2", "ISE-2"
        ESE = "ESE", "End Term Examination"

    class CandidateType(models.TextChoices):
        REGULAR = "regular", "Regular"
        BACKLOG = "backlog", "Backlog / Reappearing"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REGISTRATION = "registration", "Registration Open"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        COMPLETED = "completed", "Completed"

    title = models.CharField(max_length=180)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    candidate_type = models.CharField(max_length=12, choices=CandidateType.choices, default=CandidateType.REGULAR)
    academic_year = models.CharField(max_length=20)
    semester = models.CharField(max_length=20)
    total_marks = models.PositiveSmallIntegerField(default=20)
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    registration_start = models.DateTimeField(null=True, blank=True)
    registration_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="exam_cell_sessions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.kind in (self.Kind.ISE1, self.Kind.ISE2):
            self.total_marks, self.duration_minutes = 20, 45
        elif self.kind == self.Kind.ESE:
            self.total_marks, self.duration_minutes = 60, 120
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_candidate_type_display()})"


class ExamRegistration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="registrations")
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={"role": "student"}, related_name="exam_registrations")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True)
    backlog_semester = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_exam_registrations")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "student", "subject"], name="unique_exam_registration_subject")]


class ExamTimetableEntry(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="timetable_entries")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, blank=True)
    invigilator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={"role": "teacher"}, related_name="invigilation_entries")
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["exam_date", "start_time"]


class ExamCellResult(models.Model):
    registration = models.OneToOneField(ExamRegistration, on_delete=models.CASCADE, related_name="cell_result")
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=8, blank=True)
    remarks = models.TextField(blank=True)
    published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

# Extended examination delivery/evaluation records.
class ExamAttempt(models.Model):
    """One server-timed attempt per student and examination registration."""
    registration = models.OneToOneField(ExamRegistration, on_delete=models.CASCADE, related_name="attempt")
    started_at = models.DateTimeField(default=timezone.now)
    deadline_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    auto_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_submitted = models.BooleanField(default=False)

    def remaining_seconds(self, now=None):
        from django.utils import timezone
        now = now or timezone.now()
        return max(0, int((self.deadline_at - now).total_seconds()))


class ExamPaperQuestion(models.Model):
    """Structured template paper question; question types include MCQ and descriptive."""
    class Type(models.TextChoices):
        MCQ = "mcq", "MCQ"
        WRITTEN = "written", "Written"

    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="paper_questions")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True)
    section = models.CharField(max_length=40, default="A")
    number = models.CharField(max_length=20)
    prompt = models.TextField()
    question_type = models.CharField(max_length=12, choices=Type.choices, default=Type.WRITTEN)
    marks = models.DecimalField(max_digits=5, decimal_places=2)
    co = models.CharField(max_length=20, blank=True)
    bt = models.CharField(max_length=10, blank=True)
    options = models.JSONField(default=list, blank=True)
    correct_option = models.PositiveSmallIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["section", "order", "id"]


class ExamHall(models.Model):
    name = models.CharField(max_length=100, unique=True)
    capacity = models.PositiveIntegerField()
    building = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class ExamSeat(models.Model):
    timetable_entry = models.ForeignKey(ExamTimetableEntry, on_delete=models.CASCADE, related_name="seats")
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={"role": "student"})
    hall = models.ForeignKey(ExamHall, on_delete=models.PROTECT)
    seat_number = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["timetable_entry", "student"], name="unique_exam_student_seat"),
            models.UniqueConstraint(fields=["timetable_entry", "hall", "seat_number"], name="unique_exam_seat_number"),
        ]


class ExamPaperUpload(models.Model):
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="uploaded_papers")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    file = models.FileField(upload_to="exam_cell/papers/")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
