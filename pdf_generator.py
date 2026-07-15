# pdf_generator.py - ReportLab PDF Generator  v5
# v5 CHANGES:
#   - Clickable link paragraph placed BELOW each QR code (vertically stacked in cell)
#   - PDF header shows: College Name, Exam Name (Paper Name), Hall Name, Exam Date, Start Time, End Time
#   - All roll_no references replaced with register_number

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, Image, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.colors import HexColor
from reportlab.platypus import Flowable
import io

# Brand colors
PRIMARY_COLOR = HexColor('#1a3c5e')
ACCENT_COLOR  = HexColor('#e8a020')
HEADER_BG     = HexColor('#1a3c5e')
ALT_ROW_BG    = HexColor('#f0f4f8')
WHITE         = colors.white
LIGHT_GRAY    = HexColor('#e2e8f0')
LINK_COLOR    = HexColor('#2563eb')


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles():
    styles = getSampleStyleSheet()

    college_style = ParagraphStyle(
        'CollegeName', fontSize=17, fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=3)

    exam_style = ParagraphStyle(
        'ExamName', fontSize=12, fontName='Helvetica-Bold',
        textColor=ACCENT_COLOR, alignment=TA_CENTER, spaceAfter=3)

    info_style = ParagraphStyle(
        'InfoLine', fontSize=9, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=2)

    hall_style = ParagraphStyle(
        'HallTitle', fontSize=13, fontName='Helvetica-Bold',
        textColor=WHITE, alignment=TA_CENTER)

    footer_style = ParagraphStyle(
        'Footer', fontSize=8, fontName='Helvetica',
        textColor=colors.gray, alignment=TA_CENTER)

    cell_style = ParagraphStyle(
        'CellText', fontSize=8, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, leading=10)

    link_style = ParagraphStyle(
        'LinkText', fontSize=6, fontName='Helvetica',
        textColor=LINK_COLOR, alignment=TA_CENTER, leading=8)

    return {
        'college': college_style,
        'exam':    exam_style,
        'info':    info_style,
        'hall':    hall_style,
        'footer':  footer_style,
        'cell':    cell_style,
        'link':    link_style,
    }


def _add_page_number(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont('Helvetica', 8)
    canvas_obj.setFillColor(colors.gray)
    canvas_obj.drawRightString(A4[0] - 1.5*cm, 1*cm,
                               f"Page {canvas_obj.getPageNumber()}")
    canvas_obj.restoreState()


# ---------------------------------------------------------------------------
# Main PDF generator  v5
# ---------------------------------------------------------------------------

def generate_hall_pdf(hall_data, exam_info, output_path):
    """
    Generate a single hall seating PDF (v5).
    Header: College Name, Paper Name (Exam Name), Hall Name, Date, Start Time, End Time.
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=2*cm)

    styles = _build_styles()
    story  = []


    # ---- Header ----

    hall_num  = hall_data['hall_number']
    hall_name = hall_data.get('hall_name', f'Hall {hall_num}')
    invigilator = hall_data.get('invigilator', '').strip()

    # ── v8 Enhanced Header Block ──
    exam_name       = exam_info.get('exam_name', 'Examination') or 'Examination'
    exam_date       = exam_info.get('exam_date', '')
    exam_start_time = exam_info.get('exam_start_time', '')
    exam_end_time   = exam_info.get('exam_end_time', '')

    # Header table: [Logo | College + Exam details]
    header_left_items = [
    Paragraph(
        "Examination Seating Arrangement",
        styles['college']
    ),
    Spacer(1, 0.15*cm),

    Paragraph(
        f"<b>Exam / Paper:</b> {exam_name}",
        styles['exam']
    ),

    Spacer(1, 0.1*cm),

    Paragraph(
        f"<b>Hall:</b> {hall_name}",
        styles['info']
    ),
]
    if invigilator:
        header_left_items.append(Paragraph(f"<b>Invigilator:</b> {invigilator}", styles['info']))
    if exam_date or exam_start_time:
        parts = []
        if exam_date:       parts.append(f"Date: <b>{exam_date}</b>")
        if exam_start_time: parts.append(f"Start: <b>{exam_start_time}</b>")
        if exam_end_time:   parts.append(f"End: <b>{exam_end_time}</b>")
        header_left_items.append(Paragraph("  |  ".join(parts), styles['info']))
    for item in header_left_items:
        story.append(item)

    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width='100%', thickness=2, color=ACCENT_COLOR, spaceAfter=4))

    # ── Coloured Hall Banner ──
    hall_banner_text = f"HALL {hall_num}  –  {hall_name}  |  {exam_name}"
    if invigilator:
        hall_banner_text += f"  |  Invigilator: {invigilator}"
    hall_banner = Table(
        [[Paragraph(hall_banner_text, styles['hall'])]],
        colWidths=['100%'])
    hall_banner.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), PRIMARY_COLOR),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(hall_banner)
    story.append(Spacer(1, 0.35*cm))

    total_students = hall_data['total_students']
    total_benches  = len(hall_data['benches'])
    stats_text = (f"Total Students: {total_students}  |  "
                  f"Total Rows: {total_benches}")
    story.append(Paragraph(stats_text, styles['info']))
    story.append(Spacer(1, 0.4*cm))

    # ---- Seating Table ----
    benches         = hall_data['benches']
    seats_per_bench = (hall_data.get('cols') or
                       (max(len(b) for b in benches) if benches else None) or
                       exam_info.get('seats_per_bench', 3))

    # Header row
    header = ['Row'] + [f'Seat {i+1}' for i in range(seats_per_bench)]
    table_data = [header]

    for bench_idx, bench in enumerate(benches, start=1):
        row = [str(bench_idx)]
        first_reg = None

        for seat in bench:
            if seat is None:
                row.append('—')
            else:
                reg  = str(seat.get('register_number') or seat.get('roll_no', '')).strip()
                name = seat.get('name', reg)
                dept = seat.get('department', '')
                if first_reg is None and reg:
                    first_reg = reg
                cell_content = Paragraph(
                    f"<b>{reg}</b><br/>"
                    f"<font size='7'>{name}</font><br/>"
                    f"<font size='6' color='purple'>({dept})</font>",
                    styles['cell'])
                row.append(cell_content)

        # Pad short rows
        while len(row) < seats_per_bench + 1:
            row.append('—')
        table_data.append(row)

    # Column widths
    available_width = A4[0] - 3*cm
    row_col_width = 1.0*cm

    seat_col_width = (available_width - row_col_width) / seats_per_bench

    col_widths = [row_col_width] + [seat_col_width] * seats_per_bench

    seating_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_style = TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('ALIGN',         (0, 1), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('BACKGROUND',    (0, 1), (0, -1), LIGHT_GRAY),
        ('FONTNAME',      (0, 1), (0, -1), 'Helvetica-Bold'),
        ('GRID',          (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT_COLOR),
    ])

    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            table_style.add('BACKGROUND', (1, row_idx), (-1, row_idx), ALT_ROW_BG)

    seating_table.setStyle(table_style)
    story.append(seating_table)
    story.append(Spacer(1, 0.5*cm))


    # ---- Footer ----
    footer_text = (
    f"Paper: {exam_info.get('exam_name', '')}  |  "
    "Confidential - For Invigilator Use Only"
)
    story.append(HRFlowable(width='100%', thickness=1, color=LIGHT_GRAY))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(footer_text, styles['footer']))

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return output_path


def generate_all_pdfs(halls, exam_info, pdf_folder):
    os.makedirs(pdf_folder, exist_ok=True)
    generated_files = []
    for hall in halls:
        hall_num  = hall['hall_number']
        hall_name = hall.get('hall_name', f'Hall_{hall_num}').replace(' ', '_')
        filename  = f"Hall_{hall_num}_{hall_name}_Seating_Plan.pdf"
        out_path  = os.path.join(pdf_folder, filename)
        generate_hall_pdf(hall, exam_info, out_path)
        generated_files.append({
            'hall_number': hall_num,
            'filename':    filename,
            'path':        out_path,
        })
    return generated_files
