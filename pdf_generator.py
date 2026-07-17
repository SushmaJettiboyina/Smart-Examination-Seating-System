# pdf_generator.py - ReportLab PDF Generator  v5
# v5 CHANGES:
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
    Generate a single hall seating PDF (v9).
    Header: Clean top title and metadata, followed by hall info, and seating grid. No footers or page numbers.
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = _build_styles()
    story  = []

    # 1. Main Title Header (Only Once)
    title_style = ParagraphStyle(
        'ArrangementTitle', fontSize=18, fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=8)
    story.append(Paragraph("Examination Seating Arrangement", title_style))
    story.append(HRFlowable(width='100%', thickness=2, color=PRIMARY_COLOR, spaceAfter=12))

    # 2. Common metadata fields (Only Once)
    start_time = exam_info.get('exam_start_time', '')
    end_time = exam_info.get('exam_end_time', '')
    
    def format_time_12hr(time_str):
        try:
            from datetime import datetime
            t = datetime.strptime(time_str, "%H:%M")
            formatted = t.strftime("%I:%M %p")
            if formatted.startswith("0"):
                return formatted[1:]
            return formatted
        except Exception:
            return time_str
            
    time_range_str = f"{format_time_12hr(start_time)} – {format_time_12hr(end_time)}" if start_time and end_time else f"{start_time} – {end_time}"
    
    meta_style_left = ParagraphStyle(
        'ArrangementMetaLeft', fontSize=10, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_LEFT, leading=14)

    meta_text = [
        [Paragraph("<b>Exam / Paper</b>", meta_style_left), Paragraph(f": {exam_info.get('exam_name', 'N/A')}", meta_style_left)],
        [Paragraph("<b>Exam Date</b>", meta_style_left), Paragraph(f": {exam_info.get('exam_date', 'N/A')}", meta_style_left)],
        [Paragraph("<b>Exam Time</b>", meta_style_left), Paragraph(f": {time_range_str}", meta_style_left)],
    ]
    meta_table = Table(meta_text, colWidths=[3.2*cm, 14.8*cm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.6*cm))

    # 3. Clean Hall and Invigilator Heading
    story.append(HRFlowable(width='100%', thickness=1.5, color=ACCENT_COLOR, spaceAfter=8))
    
    hall_heading_style = ParagraphStyle(
        'HallHeadingText', fontSize=13, fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR, alignment=TA_LEFT, spaceAfter=4)
    
    hall_info_style = ParagraphStyle(
        'HallInfoText', fontSize=10, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_LEFT, leading=14)

    hall_num = hall_data['hall_number']
    hall_name = hall_data.get('hall_name', f'Hall {hall_num}')
    invigilator = hall_data.get('invigilator', '').strip() or 'Not Assigned'
    total_students = hall_data.get('total_students', 0)

    story.append(Paragraph(f"Hall {hall_num} ({hall_name})", hall_heading_style))
    story.append(Paragraph(f"<b>Invigilator:</b> {invigilator}", hall_info_style))
    story.append(Paragraph(f"<b>Total Students:</b> {total_students}", hall_info_style))
    story.append(Spacer(1, 0.4*cm))

    # 4. Seating Table
    benches         = hall_data['benches']
    seats_per_bench = (hall_data.get('cols') or
                       (max(len(b) for b in benches) if benches else None) or
                       exam_info.get('seats_per_bench', 3))

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

        while len(row) < seats_per_bench + 1:
            row.append('—')
        table_data.append(row)

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
        ('TOPPADDING',    (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('ALIGN',         (0, 1), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
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

    # 5. Build doc (No footers, no page numbers)
    doc.build(story)
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


def generate_faculty_duty_register_pdf(records, exam_info, output_path):
    """
    Generate a single PDF containing the duty details of ALL assigned faculty members (v9).
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=2*cm)

    styles = _build_styles()
    story  = []

    # 1. Title
    title_style = ParagraphStyle(
        'DutyTitle', fontSize=18, fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, spaceAfter=8)
    story.append(Paragraph("Faculty Invigilation Duty Register", title_style))
    story.append(HRFlowable(width='100%', thickness=2, color=PRIMARY_COLOR, spaceAfter=15))

    # 2. Metadata table
    meta_style_left = ParagraphStyle(
        'MetaLeft', fontSize=10, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_LEFT, leading=14)
    
    reporting_time = records[0]['reporting_time'] if records else "N/A"
    exam_time = records[0]['time'] if records else "N/A"

    meta_text = [
        [Paragraph("<b>Exam/Paper</b>", meta_style_left), Paragraph(f": {exam_info.get('exam_name', 'N/A')}", meta_style_left)],
        [Paragraph("<b>Exam Date</b>", meta_style_left), Paragraph(f": {exam_info.get('exam_date', 'N/A')}", meta_style_left)],
        [Paragraph("<b>Exam Time</b>", meta_style_left), Paragraph(f": {exam_time}", meta_style_left)],
        [Paragraph("<b>Reporting Time</b>", meta_style_left), Paragraph(f": {reporting_time}", meta_style_left)],
        [Paragraph("<b>Total Faculty</b>", meta_style_left), Paragraph(f": {len(records)}", meta_style_left)]
    ]
    meta_table = Table(meta_text, colWidths=[3.2*cm, 14.8*cm])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.8*cm))

    # 3. Duty Table
    headers = ["Faculty Name", "Department", "Hall"]
    
    cell_style = ParagraphStyle(
        'RegisterCellText', fontSize=9, fontName='Helvetica',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, leading=11)
        
    cell_bold_style = ParagraphStyle(
        'RegisterCellBoldText', fontSize=9, fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR, alignment=TA_CENTER, leading=11)

    table_data = []
    header_row = [Paragraph(f"<b>{h}</b>", ParagraphStyle('HText', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE, alignment=TA_CENTER)) for h in headers]
    table_data.append(header_row)
    
    for r in records:
        table_data.append([
            Paragraph(f"<b>{r['name']}</b>", cell_bold_style),
            Paragraph(r['department'], cell_style),
            Paragraph(r['hall'], cell_bold_style)
        ])
        
    col_widths = [8.0*cm, 5.0*cm, 5.0*cm]
    
    duty_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    table_style = TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY_COLOR),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
    ])
    
    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), ALT_ROW_BG)
            
    duty_table.setStyle(table_style)
    story.append(duty_table)

    doc.build(story, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
    return output_path
