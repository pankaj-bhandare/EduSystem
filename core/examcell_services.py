"""Domain services for Examination Cell; authoritative rules live here."""
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from . import models as m

PASS_PERCENT = Decimal('40')


def prior_backlogs(student, subject, through_semester=None):
    """Subjects the student has not cleared in completed regular registrations.

    A subject is failed if it has no published result or the published mark is below
    the configured 40% pass threshold. A passed later attempt clears the backlog.
    """
    regs = m.ExamRegistration.objects.filter(
        student=student, subject__isnull=False,
        session__candidate_type=m.ExamSession.CandidateType.REGULAR,
        status=m.ExamRegistration.Status.APPROVED,
    ).select_related('subject', 'session', 'cell_result').order_by('session__created_at')
    if through_semester is not None:
        regs = regs.filter(session__semester__lte=str(through_semester))
    latest = {}
    for reg in regs:
        latest[reg.subject_id] = reg
    failed = []
    for subject_id, reg in latest.items():
        result = getattr(reg, 'cell_result', None)
        if not result or not result.published or result.marks_obtained is None:
            failed.append(subject_id)
        elif result.marks_obtained < Decimal(reg.session.total_marks) * PASS_PERCENT / Decimal('100'):
            failed.append(subject_id)
    return m.Subject.objects.filter(pk__in=failed)


def is_eligible_for_registration(student, session, subject=None):
    if student.role != 'student' or not student.is_active:
        return False, 'Active student account required.'
    if session.status != m.ExamSession.Status.REGISTRATION:
        return False, 'Registration is not open for this examination.'
    now = timezone.now()
    if session.registration_start and now < session.registration_start:
        return False, 'Registration has not opened yet.'
    if session.registration_end and now > session.registration_end:
        return False, 'Registration deadline has passed.'
    if session.candidate_type == m.ExamSession.CandidateType.REGULAR:
        if str(student.semester) != str(session.semester):
            return False, 'Regular registration is limited to the student current semester.'
        if subject and not m.StudentClassEnrollment.objects.filter(student=student, academic_class__subjects=subject).exists():
            return False, 'Student is not enrolled in the selected subject/class.'
    else:
        if not subject:
            return False, 'Choose a subject for backlog/reappearing registration.'
        if not prior_backlogs(student, subject, through_semester=session.semester).filter(pk=subject.pk).exists():
            return False, 'No uncleared previous result was found for this subject.'
    return True, 'Eligible.'


def evaluate_mcq(paper_questions, answers):
    score = Decimal('0')
    for q in paper_questions:
        if q.question_type != m.ExamPaperQuestion.Type.MCQ or q.correct_option is None:
            continue
        try:
            selected = int(answers.get(str(q.pk), answers.get(q.pk, 0)))
        except (TypeError, ValueError):
            selected = 0
        if selected == q.correct_option:
            score += q.marks
    return score


@transaction.atomic
def start_attempt(registration):
    if registration.status != m.ExamRegistration.Status.APPROVED:
        raise ValueError('Only approved registrations may start an examination.')
    attempt, created = m.ExamAttempt.objects.select_for_update().get_or_create(
        registration=registration,
        defaults={'deadline_at': timezone.now() + timedelta(minutes=registration.session.duration_minutes)},
    )
    return attempt, created


@transaction.atomic
def save_attempt_answers(attempt, answers):
    attempt = m.ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.is_submitted or timezone.now() >= attempt.deadline_at or not isinstance(answers, dict):
        return False
    allowed = set(str(pk) for pk in attempt.registration.session.paper_questions.values_list('pk', flat=True))
    attempt.answers = {str(k): v for k, v in answers.items() if str(k) in allowed}
    attempt.auto_score = evaluate_mcq(attempt.registration.session.paper_questions.all(), attempt.answers)
    attempt.save(update_fields=['answers', 'auto_score'])
    return True


@transaction.atomic
def submit_attempt(attempt):
    attempt = m.ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.is_submitted:
        return attempt
    # Submission can occur at deadline; score only answers already saved server-side.
    attempt.auto_score = evaluate_mcq(attempt.registration.session.paper_questions.all(), attempt.answers)
    attempt.is_submitted = True
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=['auto_score', 'is_submitted', 'submitted_at'])
    return attempt
