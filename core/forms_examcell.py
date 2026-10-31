from django import forms
from .models import ExamSession, ExamRegistration, ExamTimetableEntry, ExamCellResult

class ExamSessionForm(forms.ModelForm):
    class Meta:
        model = ExamSession
        fields = ["title", "kind", "candidate_type", "academic_year", "semester", "registration_start", "registration_end", "status"]
        widgets = {"registration_start": forms.DateTimeInput(attrs={"type":"datetime-local"}), "registration_end": forms.DateTimeInput(attrs={"type":"datetime-local"})}

class ExamRegistrationForm(forms.ModelForm):
    class Meta:
        model = ExamRegistration
        fields = ["session", "subject", "backlog_semester"]

class ExamTimetableEntryForm(forms.ModelForm):
    class Meta:
        model = ExamTimetableEntry
        fields = ["session", "subject", "exam_date", "start_time", "end_time", "room", "invigilator"]
        widgets = {"exam_date": forms.DateInput(attrs={"type":"date"}), "start_time": forms.TimeInput(attrs={"type":"time"}), "end_time": forms.TimeInput(attrs={"type":"time"})}

class ExamCellResultForm(forms.ModelForm):
    class Meta:
        model = ExamCellResult
        fields = ["marks_obtained", "grade", "remarks", "published"]
