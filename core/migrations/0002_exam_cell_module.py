import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]
    operations = [
        migrations.CreateModel(name='ExamSession', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.CharField(max_length=180)),
            ('kind', models.CharField(choices=[('ISE-1', 'ISE-1'), ('ISE-2', 'ISE-2'), ('ESE', 'End Term Examination')], max_length=10)),
            ('candidate_type', models.CharField(choices=[('regular', 'Regular'), ('backlog', 'Backlog / Reappearing')], default='regular', max_length=12)),
            ('academic_year', models.CharField(max_length=20)), ('semester', models.CharField(max_length=20)),
            ('total_marks', models.PositiveSmallIntegerField(default=20)), ('duration_minutes', models.PositiveSmallIntegerField(default=45)),
            ('registration_start', models.DateTimeField(blank=True, null=True)), ('registration_end', models.DateTimeField(blank=True, null=True)),
            ('status', models.CharField(choices=[('draft', 'Draft'), ('registration', 'Registration Open'), ('scheduled', 'Scheduled'), ('published', 'Published'), ('completed', 'Completed')], default='draft', max_length=15)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exam_cell_sessions', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['-created_at']}),
        migrations.CreateModel(name='ExamRegistration', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('backlog_semester', models.CharField(blank=True, max_length=20)),
            ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=12)),
            ('submitted_at', models.DateTimeField(auto_now_add=True)), ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='registrations', to='core.examsession')),
            ('student', models.ForeignKey(limit_choices_to={'role': 'student'}, on_delete=django.db.models.deletion.CASCADE, related_name='exam_registrations', to=settings.AUTH_USER_MODEL)),
            ('subject', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='core.subject')),
            ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_exam_registrations', to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name='examregistration', constraint=models.UniqueConstraint(fields=('session', 'student', 'subject'), name='unique_exam_registration_subject')),
        migrations.CreateModel(name='ExamTimetableEntry', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('exam_date', models.DateField()), ('start_time', models.TimeField()), ('end_time', models.TimeField()), ('room', models.CharField(blank=True, max_length=100)), ('published', models.BooleanField(default=False)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('invigilator', models.ForeignKey(blank=True, limit_choices_to={'role': 'teacher'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invigilation_entries', to=settings.AUTH_USER_MODEL)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='timetable_entries', to='core.examsession')),
            ('subject', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.subject')),
        ], options={'ordering': ['exam_date', 'start_time']}),
        migrations.CreateModel(name='ExamCellResult', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('marks_obtained', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)), ('grade', models.CharField(blank=True, max_length=8)), ('remarks', models.TextField(blank=True)), ('published', models.BooleanField(default=False)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('registration', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='cell_result', to='core.examregistration')),
        ]),
    ]
