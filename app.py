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
#   - Integrated SQLite Master Data Management: Student, Faculty, and Room Masters.
#   - Removed Year and Semester details. All roll number parsing uses generic format.

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
    load_faculty_master_from_excel,
)
from seating_algorithm import (generate_multiple_hall_distribution, get_seating_stats,
                                validate_hall_layouts)
from pdf_generator import generate_all_pdfs
from roll_range_helper import generate_roll_range
from roll_parser import parse_manual_rolls, generate_start_end, remove_missing_rolls

import db

# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config.from_object(Config)

for folder in [Config.UPLOAD_FOLDER, Config.PDF_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Initialize persistent master SQLite database
db.init_db()


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


def log_activity(activity_type, text):
    """
    Store the last 5 activities in the Flask session.
    """
    try:
        activities = load_session_data('activities') or []
        # Keep only the last 4 to make room for the new one (capped at 5)
        activities = activities[-4:]
        
        # Add new activity with current timestamp
        activities.append({
            'type': activity_type,
            'text': text,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_session_data('activities', activities)
    except Exception as e:
        app.logger.error(f'log_activity error: {e}')


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
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if check_credentials(username, password):
            login_user()
            flash('Welcome back! You have logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    flash('You have logged out successfully.', 'info')
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
    activities = load_session_data('activities') or []
    return render_template('dashboard.html',
                           student_count=len(students) if students else 0,
                           halls_generated=len(halls) if halls else 0,
                           exam_info=exam_info,
                           stats=stats,
                           activities=activities)


# ---------------------------------------------------------------------------
# Upload (Stays for backward compatibility)
# ---------------------------------------------------------------------------

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['excel_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            is_valid, msg = validate_excel_format(filepath)
            if not is_valid:
                os.remove(filepath)
                flash(f'Validation failed: {msg}', 'danger')
                return redirect(request.url)

            students, error = load_students_from_excel(filepath)
            os.remove(filepath)

            if error:
                flash(f'Error loading students: {error}', 'danger')
                return redirect(request.url)

            save_session_data('students',     students)
            save_session_data('dept_summary', get_department_summary(students))
            session['excel_filename'] = filename
            session.pop('roll_range_input', None)

            log_activity('upload_students', f"Uploaded student data: {len(students)} students loaded from Excel ({filename}).")
            flash(f'✓ {msg}', 'success')
            return redirect(url_for('generate'))

    students = load_session_data('students')
    return render_template('upload.html',
                           excel_filename=session.get('excel_filename'),
                           roll_range_input=session.get('roll_range_input'),
                           student_count=len(students) if students else 0)


@app.route('/upload-faculty', methods=['POST'])
@login_required
def upload_faculty():
    if 'faculty_file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('upload'))
    file = request.files['faculty_file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('upload'))
    if not file or not allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        flash('Invalid file type.', 'danger')
        return redirect(url_for('upload'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    is_valid, message = validate_faculty_excel_format(filepath)
    if not is_valid:
        os.remove(filepath)
        flash(f'Validation failed: {message}', 'danger')
        return redirect(url_for('upload'))

    faculty, error = load_faculty_from_excel(filepath)
    os.remove(filepath)
    if error:
        flash(f'Error loading faculty: {error}', 'danger')
        return redirect(url_for('upload'))

    save_session_data('faculty_data', faculty)
    session['faculty_filename'] = filename

    log_activity('upload_faculty', f"Uploaded faculty data: {len(faculty)} invigilators loaded from Excel ({filename}).")
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

    log_activity('upload_faculty', f"Loaded faculty data: {len(faculty)} invigilators from manual input.")
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

    log_activity('upload_faculty', f"Generated faculty data: {count} invigilators auto-generated with prefix '{prefix}'.")
    flash(f'✓ Generated {count} faculty entries with prefix "{prefix}".', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Roll Number Range  (new in v6)
# ---------------------------------------------------------------------------

@app.route('/generate-roll-range', methods=['POST'])
@login_required
def generate_roll_range_route():
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
    session.pop('excel_filename', None)
    session['roll_range_input'] = roll_range_input

    log_activity('upload_students', f"Generated student data: {len(students)} students loaded from Roll Range.")
    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(f'✓ {len(students)} students generated from roll range. ({dept_str})', 'success')
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
        flash(f'Manual Roll Error: {error}', 'danger')
        return redirect(url_for('upload'))

    if missing_input:
        students, removed = remove_missing_rolls(students, missing_input)
        flash(f'Excluded {removed} absent students based on list.', 'info')

    save_session_data('students',     students)
    save_session_data('dept_summary', get_department_summary(students))
    session.pop('excel_filename', None)

    log_activity('upload_students', f"Generated student data: {len(students)} students loaded manually.")
    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(f'✓ {len(students)} students loaded manually. ({dept_str})', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Start-End Range Route (v8 new)
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
        flash(f'Excluded {removed} absent students based on list.', 'info')

    save_session_data('students',     students)
    save_session_data('dept_summary', get_department_summary(students))
    session.pop('excel_filename', None)

    log_activity('upload_students', f"Generated student data: {len(students)} students loaded from Start–End range.")
    dept_counts = get_department_summary(students)
    dept_str    = ', '.join(f"{d}: {c}" for d, c in sorted(dept_counts.items()))
    flash(f'✓ {len(students)} students generated from {start_roll} → {end_roll}. ({dept_str})', 'success')
    return redirect(url_for('generate'))


# ---------------------------------------------------------------------------
# Generate seating - Redesigned to use persistent SQLite Master Data
# ---------------------------------------------------------------------------

@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    if request.method == 'POST':
        exam_name        = request.form.get('exam_name', '').strip()
        exam_date        = request.form.get('exam_date', '').strip()
        exam_start_time  = request.form.get('exam_start_time', '').strip()
        exam_end_time    = request.form.get('exam_end_time', '').strip()
        flow_type        = request.form.get('flow_type', 'mixed')

        depts        = request.form.getlist('depts')
        room_numbers = request.form.getlist('rooms')
        faculty_ids  = request.form.getlist('faculty')

        if not room_numbers:
            flash('Please select at least one examination room.', 'danger')
            return redirect(url_for('generate'))

        # Fetch selected students matching Department filter from Master DB
        conn = db.get_db_connection()
        student_query = 'SELECT register_number, name, department FROM students_master WHERE 1=1'
        student_params = []
        if depts:
            placeholders = ', '.join('?' for _ in depts)
            student_query += f' AND department IN ({placeholders})'
            student_params.extend(depts)
            
        student_rows = conn.execute(student_query, student_params).fetchall()
        students = [dict(r) for r in student_rows]

        if not students:
            conn.close()
            flash('No students match the selected Department filters.', 'danger')
            return redirect(url_for('generate'))

        # Fetch selected Rooms details from Master DB
        placeholders = ', '.join('?' for _ in room_numbers)
        room_rows = conn.execute(f'SELECT * FROM rooms_master WHERE room_number IN ({placeholders})', room_numbers).fetchall()
        selected_rooms = [dict(r) for r in room_rows]
        total_capacity = sum(r['capacity'] for r in selected_rooms)

        # Fetch selected Faculty details from Master DB
        selected_faculty = []
        if faculty_ids:
            placeholders = ', '.join('?' for _ in faculty_ids)
            faculty_rows = conn.execute(f'SELECT name FROM faculty_master WHERE faculty_id IN ({placeholders})', faculty_ids).fetchall()
            selected_faculty = [r['name'] for r in faculty_rows]

        conn.close()

        # Validate Capacity Block
        if total_capacity < len(students):
            shortage = len(students) - total_capacity
            flash(f'⚠️ Seating Generation Blocked: Insufficient Seating Capacity! Required Seats: {len(students)}, Available Seats: {total_capacity} (Shortage of {shortage} seat{"s" if shortage != 1 else ""}). Please select more rooms.', 'danger')
            return redirect(url_for('generate'))

        # Map selected Rooms to layouts expected by algorithm
        hall_layouts = [{'rows': room['rows'], 'cols': room['cols'], 'name': room['room_number']} for room in selected_rooms]
        num_halls = len(hall_layouts)

        exam_info = {
            'exam_name':        exam_name,
            'exam_date':        exam_date,
            'exam_start_time':  exam_start_time,
            'exam_end_time':    exam_end_time,
            'num_halls':        num_halls,
            'benches_per_hall': selected_rooms[0]['rows'] if selected_rooms else 10,
            'seats_per_bench':  selected_rooms[0]['cols'] if selected_rooms else 3,
            'flow_type':        flow_type,
            'total_capacity':   total_capacity,
            'hall_layouts':     hall_layouts,
        }

        # Generate seating arrangement
        halls = generate_multiple_hall_distribution(
            students, num_halls, 10, 3,
            flow_type, hall_layouts=hall_layouts
        )

        for idx, h in enumerate(halls):
            layout_name = hall_layouts[idx].get('name', '').strip() if idx < len(hall_layouts) else ''
            if layout_name:
                h['hall_name'] = layout_name
            elif 'hall_name' not in h:
                h['hall_name'] = f"Hall {h['hall_number']}"

        # Assign invigilators (faculty)
        faculty_data = [{'hall_number': None, 'hall_name': None, 'invigilator': name} for name in selected_faculty]
        try:
            if faculty_data:
                halls = assign_invigilators(halls, faculty_data=faculty_data)
            else:
                halls = assign_invigilators(halls)
        except Exception:
            halls = assign_invigilators(halls)

        stats     = get_seating_stats(halls)
        pdf_files = generate_all_pdfs(halls, exam_info, Config.PDF_FOLDER)

        # Save to database history
        db.save_exam(
            exam_name=exam_name,
            exam_date=exam_date,
            exam_start_time=exam_start_time,
            exam_end_time=exam_end_time,
            flow_type=flow_type,
            total_students=len(students),
            total_halls=num_halls,
            halls=halls,
            stats=stats,
            pdf_files=pdf_files
        )

        # Save to session (backward compatibility)
        save_session_data('students',     students)
        save_session_data('dept_summary', get_department_summary(students))
        save_session_data('halls',     halls)
        save_session_data('stats',     stats)
        save_session_data('exam_info', exam_info)
        save_session_data('pdf_files', pdf_files)

        log_activity('generate_seating', f"Generated seating: {len(students)} students placed across {len(halls)} halls.")
        flash(f'✓ Seating arrangement generated successfully! Required Seats: {len(students)}, Available Seats: {total_capacity}. Utilization Rate: {round(len(students) / total_capacity * 100, 1)}%.', 'success')
        return redirect(url_for('seating_result'))

    # GET Request: Fetch selectors
    filters = db.get_student_filters()
    rooms = db.get_all_rooms()
    faculty = db.get_all_faculty()

    return render_template('generate.html',
                           filters=filters,
                           rooms=rooms,
                           faculty=faculty,
                           seating_flows=Config.SEATING_FLOWS)


# ---------------------------------------------------------------------------
# Seating generation Live Summary API
# ---------------------------------------------------------------------------

@app.route('/api/generate-summary', methods=['POST'])
@login_required
def api_generate_summary():
    data = request.get_json() or {}
    depts = data.get('depts', [])
    room_numbers = data.get('rooms', [])
    faculty_ids = data.get('faculty', [])

    conn = db.get_db_connection()
    
    # Fetch matching student details
    student_query = 'SELECT register_number, department FROM students_master WHERE 1=1'
    student_params = []
    if depts:
        placeholders = ', '.join('?' for _ in depts)
        student_query += f' AND department IN ({placeholders})'
        student_params.extend(depts)
        
    students = conn.execute(student_query, student_params).fetchall()
    students_selected = len(students)

    # Calculate department breakdown
    dept_summary = {}
    for s in students:
        d = s['department']
        dept_summary[d] = dept_summary.get(d, 0) + 1

    # Fetch selected rooms details
    total_capacity = 0
    if room_numbers:
        placeholders = ', '.join('?' for _ in room_numbers)
        room_rows = conn.execute(f'SELECT capacity FROM rooms_master WHERE room_number IN ({placeholders})', room_numbers).fetchall()
        total_capacity = sum(r['capacity'] for r in room_rows)

    conn.close()

    utilization = round((students_selected / total_capacity * 100), 1) if total_capacity > 0 else 0
    insufficient = total_capacity < students_selected if total_capacity > 0 or students_selected > 0 else False

    return jsonify({
        'students_selected': students_selected,
        'faculty_selected': len(faculty_ids),
        'rooms_selected': len(room_numbers),
        'total_capacity': total_capacity,
        'seat_utilization': f"{utilization}%" if total_capacity > 0 else "0%",
        'insufficient': insufficient,
        'dept_summary': dept_summary
    })


# ---------------------------------------------------------------------------
# STUDENT MASTER ROUTES
# ---------------------------------------------------------------------------

@app.route('/admin/students')
@login_required
def admin_students():
    search = request.args.get('search', '').strip()
    dept = request.args.get('dept', '').strip()
    
    students = db.get_all_students(search_query=search, department=dept)
    filters = db.get_student_filters()
    
    return render_template('admin_students.html', 
                           students=students, 
                           filters=filters,
                           search=search, 
                           selected_dept=dept)


@app.route('/admin/students/add', methods=['POST'])
@login_required
def admin_students_add():
    reg_no = request.form.get('register_number', '').strip().upper()
    name = request.form.get('name', '').strip()
    dept = request.form.get('department', '').strip().upper()
    
    if not reg_no or not name or not dept:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin_students'))
        
    success, err = db.add_student(reg_no, name, dept)
    if not success:
        flash(f'Error: {err}', 'danger')
    else:
        log_activity('add_student', f"Manually added student: {name} ({reg_no})")
        flash(f'✓ Student {name} added successfully.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/edit', methods=['POST'])
@login_required
def admin_students_edit():
    reg_no = request.form.get('register_number', '').strip().upper()
    name = request.form.get('name', '').strip()
    dept = request.form.get('department', '').strip().upper()
    
    if not reg_no or not name or not dept:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin_students'))
        
    db.update_student(reg_no, name, dept)
    log_activity('edit_student', f"Updated student info: {name} ({reg_no})")
    flash(f'✓ Student details updated.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/delete/<register_number>')
@login_required
def admin_students_delete(register_number):
    db.delete_student(register_number)
    log_activity('delete_student', f"Deleted student: {register_number}")
    flash(f'✓ Student {register_number} deleted.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/upload', methods=['POST'])
@login_required
def admin_students_upload():
    if 'excel_file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('admin_students'))
    file = request.files['excel_file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('admin_students'))
    if file and allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        is_valid, msg = validate_excel_format(filepath)
        if not is_valid:
            os.remove(filepath)
            flash(f'Validation failed: {msg}', 'danger')
            return redirect(url_for('admin_students'))
            
        students, err = load_students_from_excel(filepath)
        os.remove(filepath)
        
        if err:
            flash(f'Error reading file: {err}', 'danger')
            return redirect(url_for('admin_students'))
            
        added = db.add_students_batch(students)
        log_activity('upload_students', f"Uploaded student master: {added} records loaded from Excel ({filename}).")
        flash(f'✓ Successfully loaded/updated {added} students in Master database.', 'success')
    else:
        flash('Invalid file extension. Please upload an Excel sheet.', 'danger')
    return redirect(url_for('admin_students'))


# ---------------------------------------------------------------------------
# FACULTY MASTER ROUTES
# ---------------------------------------------------------------------------

@app.route('/admin/faculty')
@login_required
def admin_faculty():
    search = request.args.get('search', '').strip()
    dept = request.args.get('dept', '').strip()
    faculty = db.get_all_faculty(search_query=search, department=dept)
    
    conn = db.get_db_connection()
    depts = [r[0] for r in conn.execute('SELECT DISTINCT department FROM faculty_master ORDER BY department').fetchall() if r[0]]
    conn.close()
    
    return render_template('admin_faculty.html', 
                           faculty=faculty, 
                           departments=depts,
                           search=search, 
                           selected_dept=dept)


@app.route('/admin/faculty/add', methods=['POST'])
@login_required
def admin_faculty_add():
    fid = request.form.get('faculty_id', '').strip().upper()
    name = request.form.get('name', '').strip()
    dept = request.form.get('department', '').strip().upper()
    
    if not fid or not name or not dept:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin_faculty'))
        
    success, err = db.add_faculty(fid, name, dept)
    if not success:
        flash(f'Error: {err}', 'danger')
    else:
        log_activity('add_faculty', f"Manually added faculty: {name} ({fid})")
        flash(f'✓ Faculty member {name} added.', 'success')
    return redirect(url_for('admin_faculty'))


@app.route('/admin/faculty/edit', methods=['POST'])
@login_required
def admin_faculty_edit():
    fid = request.form.get('faculty_id', '').strip().upper()
    name = request.form.get('name', '').strip()
    dept = request.form.get('department', '').strip().upper()
    
    if not fid or not name or not dept:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin_faculty'))
        
    db.update_faculty(fid, name, dept)
    log_activity('edit_faculty', f"Updated faculty info: {name} ({fid})")
    flash(f'✓ Faculty details updated.', 'success')
    return redirect(url_for('admin_faculty'))


@app.route('/admin/faculty/delete/<faculty_id>')
@login_required
def admin_faculty_delete(faculty_id):
    db.delete_faculty(faculty_id)
    log_activity('delete_faculty', f"Deleted faculty member: {faculty_id}")
    flash(f'✓ Faculty member {faculty_id} deleted.', 'success')
    return redirect(url_for('admin_faculty'))


@app.route('/admin/faculty/upload', methods=['POST'])
@login_required
def admin_faculty_upload():
    if 'excel_file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('admin_faculty'))
    file = request.files['excel_file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('admin_faculty'))
    if file and allowed_file(file.filename, Config.ALLOWED_EXTENSIONS):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        is_valid, msg = validate_faculty_excel_format(filepath)
        if not is_valid:
            os.remove(filepath)
            flash(f'Validation failed: {msg}', 'danger')
            return redirect(url_for('admin_faculty'))
            
        faculty, err = load_faculty_master_from_excel(filepath)
        os.remove(filepath)
        
        if err:
            flash(f'Error reading file: {err}', 'danger')
            return redirect(url_for('admin_faculty'))
            
        added = db.add_faculty_batch(faculty)
        log_activity('upload_faculty', f"Uploaded faculty master: {added} records loaded from Excel ({filename}).")
        flash(f'✓ Successfully loaded/updated {added} faculty in Master database.', 'success')
    else:
        flash('Invalid file extension. Please upload an Excel sheet.', 'danger')
    return redirect(url_for('admin_faculty'))


# ---------------------------------------------------------------------------
# ROOM MASTER ROUTES
# ---------------------------------------------------------------------------

@app.route('/admin/rooms')
@login_required
def admin_rooms():
    search = request.args.get('search', '').strip()
    rooms = db.get_all_rooms(search_query=search)
    return render_template('admin_rooms.html', rooms=rooms, search=search)


@app.route('/admin/rooms/add', methods=['POST'])
@login_required
def admin_rooms_add():
    room_no = request.form.get('room_number', '').strip().upper()
    block = request.form.get('block', '').strip()
    
    try:
        rows = int(request.form.get('rows', 10))
        cols = int(request.form.get('cols', 3))
        capacity = int(request.form.get('capacity', rows * cols))
    except Exception:
        flash('Rows, Columns, and Capacity must be positive integers.', 'danger')
        return redirect(url_for('admin_rooms'))
        
    if not room_no or not block or rows <= 0 or cols <= 0 or capacity <= 0:
        flash('All fields are required and must be valid.', 'danger')
        return redirect(url_for('admin_rooms'))
        
    success, err = db.add_room(room_no, block, capacity, rows, cols)
    if not success:
        flash(f'Error: {err}', 'danger')
    else:
        log_activity('add_room', f"Added classroom: {room_no} in {block} (Capacity: {capacity})")
        flash(f'✓ Room {room_no} added successfully.', 'success')
    return redirect(url_for('admin_rooms'))


@app.route('/admin/rooms/edit', methods=['POST'])
@login_required
def admin_rooms_edit():
    room_no = request.form.get('room_number', '').strip().upper()
    block = request.form.get('block', '').strip()
    
    try:
        rows = int(request.form.get('rows', 10))
        cols = int(request.form.get('cols', 3))
        capacity = int(request.form.get('capacity', rows * cols))
    except Exception:
        flash('Rows, Columns, and Capacity must be positive integers.', 'danger')
        return redirect(url_for('admin_rooms'))
        
    if not room_no or not block or rows <= 0 or cols <= 0 or capacity <= 0:
        flash('All fields are required and must be valid.', 'danger')
        return redirect(url_for('admin_rooms'))
        
    db.update_room(room_no, block, capacity, rows, cols)
    log_activity('edit_room', f"Updated room details: {room_no} (Capacity: {capacity})")
    flash(f'✓ Room details updated.', 'success')
    return redirect(url_for('admin_rooms'))


@app.route('/admin/rooms/delete/<room_number>')
@login_required
def admin_rooms_delete(room_number):
    db.delete_room(room_number)
    log_activity('delete_room', f"Deleted classroom: {room_number}")
    flash(f'✓ Room {room_number} deleted.', 'success')
    return redirect(url_for('admin_rooms'))


# ---------------------------------------------------------------------------
# EXAM HISTORY ROUTES
# ---------------------------------------------------------------------------

@app.route('/admin/exams')
@login_required
def admin_exams():
    exams = db.get_all_exams()
    return render_template('admin_exams.html', exams=exams)


@app.route('/admin/exams/load/<int:exam_id>')
@login_required
def admin_exams_load(exam_id):
    exam = db.get_exam_by_id(exam_id)
    if not exam:
        flash('Exam record not found.', 'danger')
        return redirect(url_for('admin_exams'))

    try:
        halls = json.loads(exam['halls_json'])
        stats = json.loads(exam['stats_json'])
        pdf_files = json.loads(exam['pdf_files_json'])
        
        exam_info = {
            'exam_name':        exam['exam_name'],
            'exam_date':        exam['exam_date'],
            'exam_start_time':  exam['exam_start_time'],
            'exam_end_time':    exam['exam_end_time'],
            'num_halls':        exam['total_halls'],
            'flow_type':        exam['flow_type'],
            'total_capacity':   stats.get('total_capacity', 0)
        }
        
        students = []
        for h in halls:
            for r in h.get('benches', []):
                for s in r:
                    if s:
                        students.append({
                            'register_number': s.get('register_number') or s.get('roll_no', ''),
                            'name':            s.get('name', ''),
                            'department':      s.get('department', '')
                        })

        save_session_data('students',     students)
        save_session_data('dept_summary', get_department_summary(students))
        save_session_data('halls',     halls)
        save_session_data('stats',     stats)
        save_session_data('exam_info', exam_info)
        save_session_data('pdf_files', pdf_files)

        log_activity('load_exam', f"Loaded seating arrangement for historical exam: {exam['exam_name']}.")
        flash(f"✓ Exam '{exam['exam_name']}' loaded into current session. You can now view, edit, or download its plans.", 'success')
        return redirect(url_for('seating_result'))
    except Exception as e:
        app.logger.error(f'admin_exams_load error: {e}')
        flash(f'Error restoring exam session: {str(e)}', 'danger')
        return redirect(url_for('admin_exams'))


@app.route('/admin/exams/delete/<int:exam_id>')
@login_required
def admin_exams_delete(exam_id):
    exam = db.get_exam_by_id(exam_id)
    if exam:
        db.delete_exam(exam_id)
        log_activity('delete_exam', f"Deleted exam history: {exam['exam_name']}.")
        flash(f"✓ Exam history for '{exam['exam_name']}' deleted.", 'success')
    else:
        flash('Exam record not found.', 'danger')
    return redirect(url_for('admin_exams'))


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
            log_activity('download_pdf', f"Downloaded PDF seating plan for Hall {hall_number}.")
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
    log_activity('download_pdf', "Downloaded all seating plans as a ZIP archive.")
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

        log_activity('edit_seating', f"Edited seating layout: Rearranged seats in the preview editor (total {stats['total_students']} students).")
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

        log_activity('edit_seating', "Edited seating layout: Updated exam details / hall names in the admin edit view.")
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
