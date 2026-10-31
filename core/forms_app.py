from django import forms
from django.contrib.auth import password_validation
from django.db.models import Exists, OuterRef

from . import models as m
from .uploads import clean_upload

DT_FMT = "%Y-%m-%dT%H:%M"


def dt_field(label):
    return forms.DateTimeField(label=label, input_formats=[DT_FMT],
                               widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FMT))


class BS:
    """Give every widget a Bootstrap class."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for f in self.fields.values():
            w = f.widget
            cls = "form-select" if isinstance(w, forms.Select) else "form-check-input" if isinstance(w, forms.CheckboxInput) else "form-control"
            w.attrs["class"] = (w.attrs.get("class", "") + " " + cls).strip()


# ---------------------------------------------------------------- admin
class TeacherCreateForm(BS, forms.Form):
    name = forms.CharField(min_length=3, max_length=150)
    email = forms.EmailField()
    password = forms.CharField(label="Temporary password", strip=False, widget=forms.PasswordInput)
    confirm = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput)

    def clean_email(self):
        e = self.cleaned_data["email"].strip().lower()
        if m.User.objects.filter(email=e).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return e

    def clean(self):
        d = super().clean()
        if d.get("password"):
            if d["password"] != d.get("confirm"):
                self.add_error("confirm", "Passwords do not match.")
            else:
                password_validation.validate_password(d["password"])
        return d

    def save(self):
        d = self.cleaned_data
        return m.User.objects.create_user(email=d["email"], password=d["password"], name=d["name"], role="teacher")


class PasswordSetForm(BS, forms.Form):
    password = forms.CharField(label="New temporary password", strip=False, widget=forms.PasswordInput)
    confirm = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput)

    def __init__(self, *a, user=None, **k):
        super().__init__(*a, **k)
        self.user = user

    def clean(self):
        d = super().clean()
        if d.get("password"):
            if d["password"] != d.get("confirm"):
                self.add_error("confirm", "Passwords do not match.")
            else:
                password_validation.validate_password(d["password"], self.user)
        return d


class CourseForm(BS, forms.ModelForm):
    class Meta:
        model = m.Course
        fields = ["code", "name", "description"]

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class ClassForm(BS, forms.ModelForm):
    class Meta:
        model = m.AcademicClass
        fields = ["course", "name", "section", "academic_year"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["course"].queryset = m.Course.objects.filter(is_active=True)
        self.fields["section"].required = False


class SubjectForm(BS, forms.ModelForm):
    class Meta:
        model = m.Subject
        fields = ["course", "code", "name", "description"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["course"].queryset = m.Course.objects.filter(is_active=True)

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class ClassSubjectForm(BS, forms.ModelForm):
    class Meta:
        model = m.ClassSubject
        fields = ["academic_class", "subject"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["academic_class"].queryset = m.AcademicClass.objects.filter(is_active=True).select_related("course")
        self.fields["subject"].queryset = m.Subject.objects.filter(is_active=True).select_related("course")


class TeacherAssignForm(BS, forms.ModelForm):
    class Meta:
        model = m.TeacherClassSubject
        fields = ["teacher", "academic_class", "subject"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["teacher"].queryset = m.User.objects.filter(role="teacher", is_active=True).order_by("name")
        self.fields["academic_class"].queryset = m.AcademicClass.objects.filter(is_active=True)


class EnrollForm(BS, forms.ModelForm):
    class Meta:
        model = m.StudentClassEnrollment
        fields = ["student", "academic_class"]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["student"].queryset = m.User.objects.filter(role="student", is_active=True).order_by("name")
        self.fields["academic_class"].queryset = m.AcademicClass.objects.filter(is_active=True)


class AnnouncementForm(BS, forms.Form):
    title = forms.CharField(min_length=3, max_length=180)
    message = forms.CharField(min_length=5, max_length=4000, widget=forms.Textarea(attrs={"rows": 5}))
    target = forms.ChoiceField(choices=[("students", "All students"), ("teachers", "All teachers"), ("all", "All users")], label="Send to")
    category = forms.ChoiceField(choices=[(c, c.title()) for c in m.Notification.CATEGORIES])

    def __init__(self, *a, user=None, **k):
        super().__init__(*a, **k)
        if user is not None and user.role == "teacher":  # teachers may only address students
            self.fields["target"].choices = [("students", "All students")]


# ---------------------------------------------------------------- teacher
class ExamForm(BS, forms.Form):
    title = forms.CharField(max_length=200)
    class_subject = forms.ModelChoiceField(queryset=m.ClassSubject.objects.none(), label="Class and subject")
    start_time = dt_field("Start time")
    end_time = dt_field("End time")
    upload_deadline = dt_field("Upload deadline (extra time)")
    paper = forms.FileField(label="Question paper (PDF)", widget=forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}))

    def __init__(self, *a, user, **k):
        super().__init__(*a, **k)
        qs = m.ClassSubject.objects.filter(academic_class__is_active=True, subject__is_active=True).select_related("academic_class__course", "subject")
        if user.role == "teacher":  # teachers only see class/subject pairs the admin assigned to them
            qs = qs.filter(Exists(m.TeacherClassSubject.objects.filter(
                teacher=user, academic_class=OuterRef("academic_class"), subject=OuterRef("subject"))))
        self.fields["class_subject"].queryset = qs
        self.fields["class_subject"].label_from_instance = lambda o: f"{o.academic_class.course.code} · {o.academic_class} — {o.subject}"

    def clean_paper(self):
        return clean_upload(self.cleaned_data["paper"], {"pdf"})

    def clean(self):
        d = super().clean()
        s, e, dl = d.get("start_time"), d.get("end_time"), d.get("upload_deadline")
        if s and e and dl and not (e > s and dl >= e):
            raise forms.ValidationError("Enter chronological dates: start < end ≤ upload deadline.")
        return d

    def save(self):
        d = self.cleaned_data
        cs = d["class_subject"]
        return m.Exam.objects.create(title=d["title"], academic_class=cs.academic_class, subject=cs.subject,
                                     paper_file=d["paper"], start_time=d["start_time"], end_time=d["end_time"],
                                     upload_deadline=d["upload_deadline"])


class MaterialForm(BS, forms.ModelForm):
    class Meta:
        model = m.Material
        fields = ["course", "subject", "title", "file"]
        widgets = {"file": forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.ppt,.pptx"})}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["course"].queryset = m.Course.objects.filter(is_active=True)
        self.fields["subject"].queryset = m.Subject.objects.filter(is_active=True, classes__is_active=True).distinct()
        self.fields["subject"].required = False
        self.fields["subject"].empty_label = "All subjects in this course"

    def clean_file(self):
        return clean_upload(self.cleaned_data["file"], {"pdf", "jpg", "png", "ppt", "pptx"})

    def clean(self):
        d = super().clean()
        if d.get("subject") and d.get("course") and d["subject"].course_id != d["course"].id:
            self.add_error("subject", "Choose a subject that belongs to the selected course.")
        return d


class QuestionForm(BS, forms.ModelForm):
    class Meta:
        model = m.Question
        fields = ["question", "option1", "option2", "option3", "option4", "correct_option"]
        widgets = {"question": forms.Textarea(attrs={"rows": 3})}


class AnswerUploadForm(BS, forms.Form):
    file = forms.FileField(label="Answer sheet (PDF, JPG or PNG)")

    def clean_file(self):
        return clean_upload(self.cleaned_data["file"], {"pdf", "jpg", "png"})


class CheckForm(BS, forms.Form):
    marks = forms.IntegerField(min_value=0, max_value=100)
    remarks = forms.CharField(required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))
    checked_file = forms.FileField(required=False, label="Checked paper (PDF, optional)",
                                   help_text="Leave empty to keep the current file. You can also annotate the paper online.")

    def clean_checked_file(self):
        f = self.cleaned_data.get("checked_file")
        return clean_upload(f, {"pdf"}) if f else None
