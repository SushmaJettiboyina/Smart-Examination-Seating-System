# app.py - AI Exam Seating Arrangement System  v5
# v5 UPGRADES:
#   - register_number everywhere (no more roll_no in UI/API)
#   - exam_start_time & exam_end_time in exam_info, student page, PDF, admin edit
#   - paper_name alias for exam_name (Paper Name shown in UI)
#   - /student & /student/<register_number> show all times
#   - /admin/edit: editable start/end time + hall name + college + exam name
#   - /admin/save_edit: persists start/end times
#   - /api/filter: returns start/end time fields
#   - build_student_lookup: uses register_number natively

import os
import json
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_file, jsonify)
from werkzeug.utils import secure_filename

from config import Config
from auth import login_required, check_credentials, login_user, logout_user
from excel_loader import (
    load_students_from_excel,
    validate_excel_format,
    validate_faculty_excel_format,
    load_faculty_from_excel,
    get_department_summary,
)
from seating_algorithm import (generate_multiple_hall_distribution, get_seating_stats,
                                validate_hall_layouts)
from pdf_generator import generate_all_pdfs
from roll_range_helper import generate_roll_range
from roll_parser import parse_manual_rolls, generate_start_end, remove_missing_rolls

# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

for folder in [Config.UPLOAD_FOLDER, Config.PDF_FOLDER]:
    os.makedirs(folder, exist_ok=True)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def save_session_data(key, data):
    session[key] = json.dumps(data)


def load_session_data(key):
    raw = session.get(key)
    return json.loads(raw) if raw else None


def build_student_lookup(halls, exam_info=None):
    """
    Returns a dict keyed by register_number (string) with full seating + exam-time details.
    Handles both 'register_number' and legacy 'roll_no' seat fields.
    """
    lookup = {}
    if not halls:
        return lookup

    ei = exam_info or {}
    for hall in halls:
        hall_num  = hall.get('hall_number', '?')
        hall_name = hall.get('hall_name', f'Hall {hall_num}')
        for row_idx, row in enumerate(hall.get('benches', []), start=1):
            for col_idx, seat in enumerate(row, start=1):
                if seat is None:
                    continue
                # support both register_number and legacy roll_no
                reg_no = str(
                    seat.get('register_number') or seat.get('roll_no', '')
                ).strip()
                if reg_no:
                    lookup[reg_no] = {
                        'register_number': reg_no,
                        'name':            seat.get('name', reg_no),
                        'department':      seat.get('department', 'N/A'),
                        'exam_name':       ei.get('exam_name', 'N/A'),
                        'paper_name':      ei.get('exam_name', 'N/A'),
                        'hall_number':     hall_num,
                        'hall_name':       hall_name,
                        'room':            f'Hall {hall_num}',
                        'row':             row_idx,
                        'seat':            col_idx,
                        'seat_label':      f'Row {row_idx}, Seat {col_idx}',
                        'exam_date':       ei.get('exam_date', ''),
                        'exam_start_time': ei.get('exam_start_time', ''),
                        'exam_end_time':   ei.get('exam_end_time', ''),
                    }
    return lookup


def assign_invigilators(halls, faculty_data=None, rotation_seed=None, force=False):
    """
    Ensure each hall dict has an 'invigilator' key.

    - If a hall already has an invigilator and `force` is False, leave it alone.
    - Otherwise pick from a small deterministic faculty pool using
      `(hall_index + rotation_seed) % len(pool)` so tests can vary the
      assignment by changing `rotation_seed`.

    Returns the updated halls list (modified in-place).
    """
    if not halls:
        return halls

    pool = [
        'Faculty A', 'Faculty B', 'Faculty C', 'Faculty D', 'Faculty E',
        'Faculty F', 'Faculty G', 'Faculty H', 'Faculty I', 'Faculty J'
    ]
    seed = int(rotation_seed) if rotation_seed is not None else 0

    # Work on a shallow copy so callers can call this repeatedly with
    # different seeds without mutating the original list in-place.
    new_halls = [dict(h) for h in halls]
    faculty_rows = faculty_data or []

    def normalize_value(value):
        if value is None:
            return ''
        return str(value).strip().lower()

    mapped_by_number = {}
    mapped_by_name = {}
    generic_faculty = []
    for row in faculty_rows:
        invigilator = str(row.get('invigilator', '')).strip()
        if not invigilator:
            continue
        hall_number = normalize_value(row.get('hall_number'))
        hall_name = normalize_value(row.get('hall_name'))
        if hall_number:
            mapped_by_number[hall_number] = invigilator
        elif hall_name:
            mapped_by_name[hall_name] = invigilator
        else:
            generic_faculty.append(invigilator)
    for idx, hall in enumerate(new_halls):
        existing = str(hall.get('invigilator', '')).strip()
        if existing and not force:
            continue

        hall_number_norm = normalize_value(hall.get('hall_number'))
        hall_name_norm = normalize_value(hall.get('hall_name'))

        invigilator = None
        if hall_number_norm and hall_number_norm in mapped_by_number:
            invigilator = mapped_by_number[hall_number_norm]
        elif hall_name_norm and hall_name_norm in mapped_by_name:
            invigilator = mapped_by_name[hall_name_norm]
        elif generic_faculty:
            invigilator = generic_faculty.pop(0)

        if invigilator:
            hall['invigilator'] = invigilator
            continue

        pick = pool[(idx + seed) % len(pool)]
        hall['invigilator'] = pick

    return new_halls


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if check_credentials(username, password):
            login_user()
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    students  = load_session_data('students')
    halls     = load_session_data('halls')
    stats     = load_session_data('stats')
    exam_info = load_session_data('exam_info')
    return render_template('dashboard.html',
                           student_count=len(students) if students else 0,
                           halls_generated=len(halls) if halls else 0,
                           exam_info=exam_info,
                           stats=stats)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        file = request.files['excel_file']
        if not file.filename:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
            flash('Invalid file type. Please upload .xlsx or .xls.', 'danger')
            return redirect(request.url)

        filename = secure_filename(f"students_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)

        is_valid, message = validate_excel_format(filepath)
        if not is_valid:
            os.remove(filepath)
            flash(f'Validation failed: {message}', 'danger')
            return redirect(request.url)

        students, error = load_students_from_excel(filepath)
        if error:
            flash(f'Error loading file: {error}', 'danger')
            return redirect(request.url)

        save_session_data('students',     students)
        save_session_data('dept_summary', get_department_summary(students))
        session['excel_filename'] = filename
        session.pop('faculty_filename', None)
        session.pop('faculty_data', None)

        flash(f'✓ {message}', 'success')
        return redirect(url_for('generate'))

    return render_template('upload.html')


@app.route('/upload-faculty', methods=['POST'])
@login_required
def upload_faculty():
    if 'faculty_file' not in request.files:
        flash('No faculty file selected.', 'danger')
        return redirect(url_for('upload'))

    file = request.files['faculty_file']
    if not file.filename:
        flash('No faculty file selected.', 'danger')
        return redirect(url_for('upload'))
    if not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        flash('Invalid file type. Please upload .xlsx or .xls.', 'danger')
        return redirect(url_for('upload'))

    filename = secure_filename(f"faculty_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
    file.save(filepath)

    is_valid, message = validate_faculty_excel_format(filepath)
    if not is_valid:
        os.remove(filepath)
        flash(f'Validation failed: {message}', 'danger')
        return redirect(url_for('upload'))

    faculty, error = load_faculty_from_excel(filepath)
    if error:
        flash(f'Error loading faculty: {error}', 'danger')
        return redirect(url_for('upload'))

    save_session_data('faculty_data', faculty)
    session['faculty_filename'] = filename

    flash(f'✓ {message}', 'success')
    return redirect(url_for('generate'))


@app.route('/generate-manual-faculty', methods=['POST'])
@login_required
def generate_manual_faculty():
    manual_input = request.form.get('manual_faculty', '').strip()
    if not manual_input:
        flash('Please enter at least one faculty entry.', 'danger')
        return redirect(url_for('upload'))

    import re
    tokens = re.split(r'[\r\n,]+', manual_input)
    faculty = []
    for t in tokens:
        s = t.strip()
        if not s:
            continue
        # support 'hall:invigilator' or 'hall|invigilator' or 'hall->invigilator'
        parts = re.split(r'\s*(?:\||:|->)\s*', s, maxsplit=1)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            hall_number = None
            hall_name = None
            if left.isdigit():
                hall_number = int(left)
            else:
                hall_name = left
            faculty.append({'hall_number': hall_number, 'hall_name': hall_name, 'invigilator': right})
        else:
            faculty.append({'hall_number': None, 'hall_name': None, 'invigilator': s})

    if not faculty:
        flash('No valid faculty entries found.', 'danger')
        return redirect(url_for('upload'))

    save_session_data('faculty_data', faculty)
    session['faculty_manual_input'] = manual_input
    session.pop('faculty_filename', None)

    flash(f'✓ {len(faculty)} faculty entries loaded from manual input.', 'success')
    return redirect(url_for('generate'))


@app.route('/generate-faculty', methods=['POST'])
@login_required
def generate_faculty():
    try:
        count = int(request.form.get('faculty_count', 0))
    except Exception:
        count = 0
    prefix = request.form.get('faculty_prefix', 'Faculty').strip()

    if count <= 0:
        flash('Please enter a positive number of faculty to generate.', 'danger')
        return redirect(url_for('upload'))

    faculty = []
    for i in range(1, count + 1):
        faculty.append({'hall_number': None, 'hall_name': None, 'invigilator': f"{prefix} {i}"})

    save_session_data('faculty_data', faculty)
    session['faculty_generated'] = {'count': count, 'prefix': prefix}
    session.pop('faculty_filename', None)

    flash(f'✓ Generated {count} faculty entries with prefix "{prefix}".', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Roll Number Range  (new in v6)
# ---------------------------------------------------------------------------

@app.route('/generate-roll-range', methods=['POST'])
@login_required
def generate_roll_range_route():
    """
    Accept a roll number range (or multiple comma-separated ranges) from
    the upload page form and store the generated student list in the session
    — exactly the same format as an Excel upload — then redirect to /generate.

    Form fields:
        roll_range   : e.g. "24IT001 TO 24IT120"
                       or    "24IT001 TO 24IT060, 24CSE001 TO 24CSE050"
        dept_override: optional manual department override
    """
    roll_range_input = request.form.get('roll_range', '').strip()
    dept_override    = request.form.get('dept_override', '').strip()

    if not roll_range_input:
        flash('Please enter a roll number range.', 'danger')
        return redirect(url_for('upload'))

    students, error = generate_roll_range(roll_range_input, override_dept=dept_override)

    if error:
        flash(f'Range Error: {error}', 'danger')
        return redirect(url_for('upload'))

    save_session_data('students',     students)
    save_session_data('dept_summary', get_department_summary(students))
    # Clear any leftover excel filename so the UI doesn't show a stale filename
    session.pop('excel_filename', None)
    session['roll_range_input'] = roll_range_input   # store for display

    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(
        f'✓ {len(students)} students generated from roll range. ({dept_str})',
        'success'
    )
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Manual Roll Entry  (v8 new)
# ---------------------------------------------------------------------------

@app.route('/generate-manual-rolls', methods=['POST'])
@login_required
def generate_manual_rolls_route():
    manual_input  = request.form.get('manual_rolls', '').strip()
    missing_input = request.form.get('missing_rolls', '').strip()
    dept_override = request.form.get('dept_override', '').strip()

    if not manual_input:
        flash('Please enter at least one roll number.', 'danger')
        return redirect(url_for('upload'))

    students, error = parse_manual_rolls(manual_input, override_dept=dept_override)
    if error:
        flash(f'Manual Entry Error: {error}', 'danger')
        return redirect(url_for('upload'))

    if missing_input:
        students, removed = remove_missing_rolls(students, missing_input)
        if removed:
            flash(f'ℹ {removed} missing roll(s) excluded.', 'info')

    save_session_data('students',     students)
    save_session_data('dept_summary', get_department_summary(students))
    session.pop('excel_filename', None)

    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(f'✓ {len(students)} students loaded from manual entry. ({dept_str})', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Start–End Simple Input  (v8 new)
# ---------------------------------------------------------------------------

@app.route('/generate-start-end', methods=['POST'])
@login_required
def generate_start_end_route():
    start_roll    = request.form.get('start_roll', '').strip()
    end_roll      = request.form.get('end_roll', '').strip()
    missing_input = request.form.get('missing_rolls', '').strip()
    dept_override = request.form.get('dept_override', '').strip()

    if not start_roll or not end_roll:
        flash('Please enter both Start and End roll numbers.', 'danger')
        return redirect(url_for('upload'))

    students, error = generate_start_end(start_roll, end_roll, override_dept=dept_override)
    if error:
        flash(f'Start–End Error: {error}', 'danger')
        return redirect(url_for('upload'))

    if missing_input:
        students, removed = remove_missing_rolls(students, missing_input)
        if removed:
            flash(f'ℹ {removed} missing roll(s) excluded.', 'info')

    save_session_data('students',     students)
    save_session_data('dept_summary', get_department_summary(students))
    session.pop('excel_filename', None)

    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(f'✓ {len(students)} students generated from {start_roll} → {end_roll}. ({dept_str})', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Generate seating
# ---------------------------------------------------------------------------

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    students     = load_session_data('students')
    dept_summary = load_session_data('dept_summary')

    if not students:
        flash('Please upload a student Excel file first.', 'warning')
        return redirect(url_for('upload'))

    if request.method == 'POST':
        exam_name        = request.form.get('exam_name', '').strip()
        exam_date        = request.form.get('exam_date', '').strip()
        exam_start_time  = request.form.get('exam_start_time', '').strip()
        exam_end_time    = request.form.get('exam_end_time', '').strip()
        num_halls        = int(request.form.get('num_halls', 1))
        flow_type        = request.form.get('flow_type', 'mixed')
        default_rows     = int(request.form.get('benches_per_hall', 10))
        default_cols     = int(request.form.get('seats_per_bench', 3))

        hall_layouts = []
        for i in range(1, num_halls + 1):
            rows      = int(request.form.get(f'hall_rows_{i}', default_rows))
            cols      = int(request.form.get(f'hall_cols_{i}', default_cols))
            hall_name = request.form.get(f'hall_name_{i}', '').strip()
            if not hall_name:
                hall_name = f'Hall {i}'
            hall_layouts.append({'rows': rows, 'cols': cols, 'name': hall_name})

        is_valid, msg, total_capacity = validate_hall_layouts(
            num_halls, hall_layouts, len(students))
        if not is_valid:
            flash(f'Capacity error: {msg}', 'danger')
            return redirect(request.url)

        exam_info = {
            'exam_name':        exam_name,
            'exam_date':        exam_date,
            'exam_start_time':  exam_start_time,
            'exam_end_time':    exam_end_time,
            'num_halls':        num_halls,
            'benches_per_hall': default_rows,
            'seats_per_bench':  default_cols,
            'flow_type':        flow_type,
            'total_capacity':   total_capacity,
            'hall_layouts':     hall_layouts,
        }

        halls = generate_multiple_hall_distribution(
            students, num_halls, default_rows, default_cols,
            flow_type, hall_layouts=hall_layouts)

        for idx, h in enumerate(halls):
            layout_name = hall_layouts[idx].get('name', '').strip() if idx < len(hall_layouts) else ''
            if layout_name:
                h['hall_name'] = layout_name
            elif 'hall_name' not in h:
                h['hall_name'] = f"Hall {h['hall_number']}"

        # Ensure every hall has an assigned invigilator (faculty)
        faculty_data = load_session_data('faculty_data') or []
        try:
            if faculty_data:
                halls = assign_invigilators(halls, faculty_data=faculty_data)
            else:
                halls = assign_invigilators(halls)
        except Exception:
            halls = assign_invigilators(halls)

        stats     = get_seating_stats(halls)
        pdf_files = generate_all_pdfs(halls, exam_info, Config.PDF_FOLDER)

        save_session_data('halls',     halls)
        save_session_data('stats',     stats)
        save_session_data('exam_info', exam_info)
        save_session_data('pdf_files', pdf_files)

        flash(f'✓ Seating generated for {len(halls)} hall(s)!', 'success')
        return redirect(url_for('seating_result'))

    return render_template('generate.html',
                           students=students,
                           dept_summary=dept_summary,
                           seating_flows=Config.SEATING_FLOWS,
                           student_count=len(students))


# ---------------------------------------------------------------------------
# Seating result
# ---------------------------------------------------------------------------

@app.route('/seating-result')
@login_required
def seating_result():
    halls     = load_session_data('halls')
    stats     = load_session_data('stats')
    exam_info = load_session_data('exam_info')
    pdf_files = load_session_data('pdf_files')

    if not halls:
        flash('No seating arrangement found. Please generate one first.', 'warning')
        return redirect(url_for('generate'))

    return render_template('seating_result.html',
                           halls=halls, stats=stats,
                           exam_info=exam_info, pdf_files=pdf_files)


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

@app.route('/download-pdf/<int:hall_number>')
@login_required
def download_pdf(hall_number):
    pdf_files = load_session_data('pdf_files')
    if not pdf_files:
        flash('No PDFs found. Please generate seating first.', 'warning')
        return redirect(url_for('dashboard'))
    for pdf in pdf_files:
        if pdf['hall_number'] == hall_number and os.path.exists(pdf['path']):
            return send_file(pdf['path'], as_attachment=True,
                             download_name=pdf['filename'],
                             mimetype='application/pdf')
    flash(f'PDF for Hall {hall_number} not found.', 'danger')
    return redirect(url_for('seating_result'))


@app.route('/download-all-pdfs')
@login_required
def download_all_pdfs():
    import zipfile, io
    pdf_files = load_session_data('pdf_files')
    if not pdf_files:
        flash('No PDFs found.', 'warning')
        return redirect(url_for('dashboard'))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            if os.path.exists(pdf['path']):
                zf.write(pdf['path'], pdf['filename'])
    buf.seek(0)
    exam_info = load_session_data('exam_info')
    exam_name = (exam_info.get('exam_name', 'Exam').replace(' ', '_')
                 if exam_info else 'Exam')
    return send_file(buf, as_attachment=True,
                     download_name=f'{exam_name}_All_Seating_Plans.zip',
                     mimetype='application/zip')


# ---------------------------------------------------------------------------
# Seating preview editor
# ---------------------------------------------------------------------------

@app.route('/seating-preview')
@login_required
def seating_preview():
    halls     = load_session_data('halls')
    exam_info = load_session_data('exam_info')
    if not halls:
        flash('No seating arrangement found. Please generate one first.', 'warning')
        return redirect(url_for('generate'))
    return render_template('seating_preview.html', halls=halls, exam_info=exam_info)


@app.route('/save_seating', methods=['POST'])
@login_required
def save_seating():
    try:
        payload = request.get_json(force=True)
        if not payload or 'halls' not in payload:
            return jsonify({'success': False, 'message': 'Missing halls data.'}), 400

        updated_halls = payload['halls']
        for hall in updated_halls:
            if 'hall_number' not in hall or 'benches' not in hall:
                return jsonify({'success': False, 'message': 'Malformed hall data.'}), 400
            hall['total_students'] = sum(
                1 for row in hall['benches'] for seat in row if seat)

        stats = get_seating_stats(updated_halls)
        save_session_data('halls', updated_halls)
        save_session_data('stats', stats)

        exam_info = load_session_data('exam_info')
        if exam_info:
            try:
                pdf_files = generate_all_pdfs(updated_halls, exam_info, Config.PDF_FOLDER)
                save_session_data('pdf_files', pdf_files)
            except Exception as pdf_err:
                app.logger.warning(f'PDF regen failed: {pdf_err}')

        return jsonify({
            'success': True,
            'message': (f'Saved. {stats["total_students"]} students '
                        f'across {stats["total_halls"]} halls.'),
            'stats': stats,
        })
    except Exception as e:
        app.logger.error(f'save_seating error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ---------------------------------------------------------------------------
# Student Search  /student  and  /student/<register_number>
# ---------------------------------------------------------------------------

@app.route('/student', methods=['GET', 'POST'])
def student_search():
    halls     = load_session_data('halls')
    exam_info = load_session_data('exam_info')
    lookup    = build_student_lookup(halls, exam_info)

    result    = None
    not_found = False
    reg_no    = ''

    if request.method == 'POST':
        reg_no = request.form.get('register_number', '').strip()
    else:
        reg_no = request.args.get('reg', '').strip()

    if reg_no:
        result = lookup.get(reg_no)
        if not result:
            not_found = True

    return render_template('student.html',
                           result=result,
                           not_found=not_found,
                           reg_no=reg_no,
                           exam_info=exam_info)


@app.route('/student/<register_number>')
def student_auto(register_number):
    halls     = load_session_data('halls')
    exam_info = load_session_data('exam_info')
    lookup    = build_student_lookup(halls, exam_info)

    reg_no    = str(register_number).strip()
    result    = lookup.get(reg_no)
    not_found = result is None

    return render_template('student.html',
                           result=result,
                           not_found=not_found,
                           reg_no=reg_no,
                           exam_info=exam_info)


# ---------------------------------------------------------------------------
# Admin Edit  /admin/edit  — v5: editable start/end times
# ---------------------------------------------------------------------------

@app.route('/admin/edit', methods=['GET'])
@login_required
def admin_edit():
    halls     = load_session_data('halls')
    exam_info = load_session_data('exam_info')
    if not halls:
        flash('No seating arrangement found. Please generate one first.', 'warning')
        return redirect(url_for('generate'))
    return render_template('admin_edit.html', halls=halls, exam_info=exam_info)


@app.route('/admin/save_edit', methods=['POST'])
@login_required
def admin_save_edit():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({'success': False, 'message': 'No data received.'}), 400

        exam_info = load_session_data('exam_info') or {}

        for field in ('exam_name', 'exam_start_time', 'exam_end_time', 'exam_date'):
            if field in payload:
                exam_info[field] = payload[field]

        save_session_data('exam_info', exam_info)

        if 'hall_names' in payload:
            halls    = load_session_data('halls') or []
            name_map = payload['hall_names']
            for hall in halls:
                hn = str(hall.get('hall_number', ''))
                if hn in name_map:
                    hall['hall_name'] = name_map[hn]
            save_session_data('halls', halls)

        if 'halls' in payload:
            updated_halls = payload['halls']
            for hall in updated_halls:
                hall['total_students'] = sum(
                    1 for row in hall.get('benches', []) for seat in row if seat)
            stats = get_seating_stats(updated_halls)
            save_session_data('halls', updated_halls)
            save_session_data('stats', stats)
            try:
                pdf_files = generate_all_pdfs(updated_halls, exam_info, Config.PDF_FOLDER)
                save_session_data('pdf_files', pdf_files)
            except Exception as pdf_err:
                app.logger.warning(f'PDF regen failed after edit: {pdf_err}')

        return jsonify({'success': True, 'message': 'Changes saved successfully!'})

    except Exception as e:
        app.logger.error(f'admin_save_edit error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ---------------------------------------------------------------------------
# Filter API  /api/filter
# ---------------------------------------------------------------------------

@app.route('/api/filter')
@login_required
def api_filter():
    halls     = load_session_data('halls')
    exam_info = load_session_data('exam_info')
    lookup    = build_student_lookup(halls, exam_info)

    dept_filter = request.args.get('department', '').strip().upper()
    hall_filter = request.args.get('hall', '').strip()
    exam_filter = request.args.get('exam', '').strip().upper()
    reg_filter  = request.args.get('reg', '').strip()

    results = list(lookup.values())

    if dept_filter:
        results = [r for r in results if r['department'].upper() == dept_filter]
    if hall_filter:
        results = [r for r in results if str(r['hall_number']) == hall_filter]
    if exam_filter:
        results = [r for r in results if exam_filter in r['exam_name'].upper()]
    if reg_filter:
        results = [r for r in results if reg_filter.lower() in r['register_number'].lower()]

    all_depts = sorted({r['department'] for r in lookup.values()})
    all_halls = sorted({str(r['hall_number']) for r in lookup.values()})

    return jsonify({
        'results':   results,
        'total':     len(results),
        'filters': {
            'departments': all_depts,
            'halls':       all_halls,
        }
    })


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify(load_session_data('stats') or {})


# ---------------------------------------------------------------------------
# Hall reorder  /update-hall-order
# ---------------------------------------------------------------------------

@app.route('/update-hall-order', methods=['POST'])
@login_required
def update_hall_order():
    """
    Receive JSON { "order": [2, 0, 1] } and reorder session['halls'] accordingly.
    After reordering, regenerate PDFs so download links stay in sync.
    """
    try:
        payload = request.get_json(force=True)
        if not payload or 'order' not in payload:
            return jsonify({'success': False, 'message': 'Missing order data.'}), 400

        new_order = payload['order']
        halls     = load_session_data('halls') or []

        if len(new_order) != len(halls):
            return jsonify({'success': False,
                            'message': 'Order length mismatch.'}), 400

        reordered = [halls[i] for i in new_order]
        save_session_data('halls', reordered)

        # Regenerate PDFs with new order
        exam_info = load_session_data('exam_info')
        if exam_info:
            try:
                pdf_files = generate_all_pdfs(reordered, exam_info, Config.PDF_FOLDER)
                save_session_data('pdf_files', pdf_files)
            except Exception as pdf_err:
                app.logger.warning(f'PDF regen after reorder failed: {pdf_err}')

        return jsonify({'success': True,
                        'message': f'Hall order updated ({len(reordered)} halls).'})
    except Exception as e:
        app.logger.error(f'update_hall_order error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template('login.html'), 404


@app.errorhandler(413)
def too_large(e):
    flash('File too large. Max upload size is 16 MB.', 'danger')
    return redirect(url_for('upload'))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("  AI Exam Seating Arrangement System  v5")
    print("  http://127.0.0.1:5000")
    print("  Login: admin / admin123")
    print("  /student  /student/<register_number>  /admin/edit")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)
