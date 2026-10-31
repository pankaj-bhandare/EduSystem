"""Examination Cell document exports (Excel and PDF)."""
from io import BytesIO
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from . import models as m
from .decorators import role_required


def _xlsx_response(filename, headers, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "Examination Data"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center")
    for row in rows: ws.append(list(row))
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        width = min(42, max(12, max(len(str(c.value or "")) for c in col) + 2))
        ws.column_dimensions[col[0].column_letter].width = width
    buf = BytesIO(); wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required("admin")
def export_exam_registrations(request):
    qs = m.ExamRegistration.objects.select_related("student", "session", "subject").order_by("session_id", "student__name")
    rows = [(r.student.reg_no or "", r.student.name, r.student.email, r.session.title, r.session.kind,
             r.session.candidate_type, r.session.semester, r.subject.code if r.subject else "", r.status, r.backlog_semester)
            for r in qs]
    return _xlsx_response("exam_registrations.xlsx", ["Enrollment", "Student", "Email", "Session", "Exam Type", "Candidate Type", "Semester", "Subject", "Status", "Backlog Semester"], rows)


@role_required("admin")
def export_exam_results(request):
    qs = m.ExamCellResult.objects.select_related("registration__student", "registration__session", "registration__subject")
    rows = [(r.registration.student.reg_no or "", r.registration.student.name, r.registration.session.title,
             r.registration.subject.code if r.registration.subject else "", r.marks_obtained, r.registration.session.total_marks,
             r.grade, "Published" if r.published else "Draft") for r in qs]
    return _xlsx_response("exam_results.xlsx", ["Enrollment", "Student", "Session", "Subject", "Marks", "Max Marks", "Grade", "Publication"], rows)


def _pdf_response(filename, title, data_rows):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    buf = BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet(); story = [Paragraph("Shri Guru Gobind Singhji Institute of Engineering and Technology, Nanded", styles["Title"]), Paragraph(title, styles["Heading2"]), Spacer(1, 8)]
    table = Table(data_rows, repeatRows=1, colWidths=None)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.5,colors.grey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F2F5F9")])]))
    story.append(table); doc.build(story)
    response = HttpResponse(buf.getvalue(), content_type="application/pdf"); response["Content-Disposition"] = f'attachment; filename="{filename}"'; return response


@role_required("student")
def student_hall_ticket(request):
    regs = m.ExamRegistration.objects.filter(student=request.user, status="approved").select_related("session", "subject")
    rows = [["Exam Session", "Subject", "Type", "Semester", "Marks", "Duration"]]
    for r in regs:
        rows.append([r.session.title, str(r.subject or "—"), r.session.kind, r.session.semester, str(r.session.total_marks), f"{r.session.duration_minutes} min"])
    if len(rows) == 1: rows.append(["No approved registrations", "—", "—", "—", "—", "—"])
    return _pdf_response("hall_ticket.pdf", f"Hall Ticket · {request.user.name} · {request.user.reg_no or ''}", rows)


@role_required("student")
def student_marksheet(request):
    results = m.ExamCellResult.objects.filter(registration__student=request.user, published=True).select_related("registration__session", "registration__subject")
    rows = [["Examination", "Subject", "Marks Obtained", "Maximum", "Grade"]]
    for r in results:
        rows.append([r.registration.session.title, str(r.registration.subject or "—"), str(r.marks_obtained or "—"), str(r.registration.session.total_marks), r.grade or "—"])
    if len(rows) == 1: rows.append(["No published results", "—", "—", "—", "—"])
    return _pdf_response("marksheet.pdf", f"Statement of Results · {request.user.name} · {request.user.reg_no or ''}", rows)


@role_required("admin")
def print_seating_plan(request, entry_id):
    entry = get_object_or_404(m.ExamTimetableEntry.objects.select_related("session", "subject"), pk=entry_id)
    seats = m.ExamSeat.objects.filter(timetable_entry=entry).select_related("student", "hall").order_by("hall__name", "seat_number")
    rows = [["Hall", "Seat", "Enrollment", "Student", "Division"]]
    for seat in seats:
        rows.append([seat.hall.name, seat.seat_number, seat.student.reg_no or "", seat.student.name, seat.student.division])
    if len(rows) == 1: rows.append(["No seating assignments", "—", "—", "—", "—"])
    return _pdf_response("seating_plan.pdf", f"Seating Plan · {entry.session.title} · {entry.subject}", rows)

# ------------------------- Excel registration import and template paper DOCX
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from pathlib import Path


def _registration_import_template():
    """Download a clean Excel sheet with the supported registration columns."""
    return _xlsx_response(
        "exam_registration_import_template.xlsx",
        ["Session ID", "Enrollment", "Subject Code", "Backlog Semester"],
        [["(required)", "(required; student reg_no)", "(optional; subject code)", "(optional)" ]],
    )


@role_required("admin")
@require_http_methods(["GET", "POST"])
def import_exam_registrations(request):
    """Admin import: one registration per row; validates every row before saving it."""
    if request.method == "GET":
        return _registration_import_template()
    from openpyxl import load_workbook
    uploaded = request.FILES.get("file")
    if not uploaded or not uploaded.name.lower().endswith((".xlsx", ".xlsm")):
        messages.error(request, "Choose an Excel .xlsx file. Download the import template first to see the required columns.")
        return redirect("examcell_admin")
    try:
        wb = load_workbook(uploaded, read_only=True, data_only=True)
        ws = wb.active
        raw = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        messages.error(request, f"Could not read the Excel file: {exc}")
        return redirect("examcell_admin")
    if not raw:
        messages.error(request, "The Excel sheet is empty.")
        return redirect("examcell_admin")
    headers = [str(v or "").strip().casefold() for v in raw[0]]
    required = ["session id", "enrollment"]
    if any(h not in headers for h in required):
        messages.error(request, "Missing required columns: Session ID and Enrollment. Download the template for the correct format.")
        return redirect("examcell_admin")
    col = {h: headers.index(h) for h in headers if h}
    def cell(row, key):
        i = col.get(key)
        return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""
    created = skipped = 0
    errors = []
    for line_no, row in enumerate(raw[1:], start=2):
        if not row or not any(v is not None and str(v).strip() for v in row):
            continue
        try:
            sid, enrollment = cell(row, "session id"), cell(row, "enrollment")
            if not sid.isdigit() or not enrollment:
                raise ValueError("Session ID must be numeric and Enrollment is required")
            session = m.ExamSession.objects.get(pk=int(sid))
            student = m.User.objects.get(reg_no__iexact=enrollment, role="student")
            subject = None
            subject_code = cell(row, "subject code")
            if subject_code:
                subject = m.Subject.objects.get(code__iexact=subject_code)
            _, was_created = m.ExamRegistration.objects.get_or_create(
                session=session, student=student, subject=subject,
                defaults={"backlog_semester": cell(row, "backlog semester"), "status": "pending"},
            )
            if was_created: created += 1
            else: skipped += 1
        except m.ExamSession.DoesNotExist:
            errors.append(f"Row {line_no}: session ID {cell(row, 'session id')} was not found.")
        except m.User.DoesNotExist:
            errors.append(f"Row {line_no}: student enrollment {cell(row, 'enrollment')} was not found.")
        except m.Subject.DoesNotExist:
            errors.append(f"Row {line_no}: subject code {cell(row, 'subject code')} was not found.")
        except m.Subject.MultipleObjectsReturned:
            errors.append(f"Row {line_no}: subject code {cell(row, 'subject code')} is ambiguous; use a unique code.")
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {line_no}: {exc}")
    messages.success(request, f"Excel import complete: {created} registration(s) added, {skipped} duplicate(s) skipped, {len(errors)} row(s) rejected.")
    for err in errors[:8]: messages.error(request, err)
    if len(errors) > 8: messages.warning(request, f"{len(errors)-8} additional row errors were omitted from the message list.")
    return redirect("examcell_admin")


def _replace_cell(cell, text):
    """Replace cell text while retaining its first paragraph/run formatting."""
    if cell.paragraphs:
        p = cell.paragraphs[0]
        if p.runs:
            p.runs[0].text = str(text)
            for run in p.runs[1:]: run.text = ""
        else: p.add_run(str(text))
        for p_extra in cell.paragraphs[1:]:
            for run in p_extra.runs: run.text = ""
    else: cell.text = str(text)


@role_required("admin")
@require_http_methods(["GET"])
def generate_question_paper(request, session_id, subject_id):
    """Generate a DOCX question paper from the uploaded ISE/ESE institute template."""
    from docx import Document
    from docx.shared import Inches
    session = get_object_or_404(m.ExamSession, pk=session_id)
    subject = get_object_or_404(m.Subject, pk=subject_id)
    if session.kind == "ESE":
        template_name = "ESE template.docx"
    elif session.kind in ("ISE-1", "ISE-2"):
        template_name = "ISE template.docx"
    else:
        messages.error(request, "This session type does not have a supported paper template.")
        return redirect("examcell_admin")
    template_path = Path(__file__).resolve().parent / "templates" / "core" / "examcell_paper_templates" / template_name
    if not template_path.exists():
        messages.error(request, f"The paper template file is missing: {template_name}. Add it to core/templates/core/examcell_paper_templates/.")
        return redirect("examcell_admin")
    doc = Document(str(template_path))
    # Fill metadata fields in the template's first header table.
    if doc.tables:
        header = doc.tables[0]
        for row in header.rows:
            for cell in row.cells:
                old = cell.text
                updated = old.replace("Academic Year: ", f"Academic Year: {session.academic_year}")
                updated = updated.replace("Subject: ", f"Subject: {subject.name}")
                updated = updated.replace("Subject Code: ", f"Subject Code: {subject.code}")
                updated = updated.replace("Max. Marks: 20", f"Max. Marks: {session.total_marks}")
                updated = updated.replace("Max. Marks: 60", f"Max. Marks: {session.total_marks}")
                if updated != old: _replace_cell(cell, updated)
    questions = list(m.ExamPaperQuestion.objects.filter(session=session, subject=subject).order_by("section", "order", "id"))
    # Template question tables have columns Q.N., Q.N., Questions, Marks, CO, BT.
    question_tables = [t for t in doc.tables if len(t.columns) >= 6 and any("Questions" in c.text for c in t.rows[0].cells)]
    if question_tables:
        table = question_tables[0]
        # Reuse existing body rows; add styled rows as needed.
        body_rows = list(table.rows[1:])
        for idx, q in enumerate(questions):
            if idx < len(body_rows): row = body_rows[idx]
            else: row = table.add_row()
            cells = row.cells
            vals = [q.number, "", q.prompt, str(q.marks), q.co, q.bt]
            for j, val in enumerate(vals[:len(cells)]): _replace_cell(cells[j], val)
        # Clear unused template rows to avoid phantom question placeholders.
        for row in body_rows[len(questions):]:
            for cell in row.cells: _replace_cell(cell, "")
    output = BytesIO(); doc.save(output)
    filename = f"{session.kind}_{subject.code}_question_paper.docx"
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
