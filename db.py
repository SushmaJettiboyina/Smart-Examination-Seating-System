# db.py - Persistent SQLite Database Wrapper for Smart Examination Seating System (Generic Version)

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'seating_system.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Student Master Table (Removed year and semester)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students_master (
            register_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL
        )
    ''')
    
    # 2. Faculty Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faculty_master (
            faculty_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL
        )
    ''')
    
    # 3. Room Master Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms_master (
            room_number TEXT PRIMARY KEY,
            block TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            rows INTEGER NOT NULL,
            cols INTEGER NOT NULL
        )
    ''')
    
    conn.commit()
    
    # 4. Seed Data if database tables are empty
    seed_data_if_empty(cursor)
    
    conn.commit()
    conn.close()

def seed_data_if_empty(cursor):
    # Check and Seed Rooms
    cursor.execute('SELECT COUNT(*) FROM rooms_master')
    if cursor.fetchone()[0] == 0:
        rooms = [
            ('LH-101', 'A Block', 30, 10, 3),
            ('LH-102', 'A Block', 30, 10, 3),
            ('LH-201', 'B Block', 40, 10, 4),
            ('LH-202', 'B Block', 40, 10, 4),
            ('LH-301', 'C Block', 50, 10, 5),
            ('LH-302', 'C Block', 50, 10, 5),
        ]
        cursor.executemany(
            'INSERT INTO rooms_master (room_number, block, capacity, rows, cols) VALUES (?, ?, ?, ?, ?)',
            rooms
        )

    # Check and Seed Faculty
    cursor.execute('SELECT COUNT(*) FROM faculty_master')
    if cursor.fetchone()[0] == 0:
        faculty = [
            ('FAC001', 'Dr. Aris Thorne', 'CSE'),
            ('FAC002', 'Prof. Sarah Vance', 'IT'),
            ('FAC003', 'Dr. Ramesh Kumar', 'ECE'),
            ('FAC004', 'Prof. Priya Sharma', 'EEE'),
            ('FAC005', 'Dr. Alan Mercer', 'MECH'),
            ('FAC006', 'Prof. David Miller', 'CSE'),
            ('FAC007', 'Dr. Emily Watson', 'IT'),
            ('FAC008', 'Prof. Robert Evans', 'ECE'),
        ]
        cursor.executemany(
            'INSERT INTO faculty_master (faculty_id, name, department) VALUES (?, ?, ?)',
            faculty
        )

    # Check and Seed Students (Removed Year/Sem details, using generic format)
    cursor.execute('SELECT COUNT(*) FROM students_master')
    if cursor.fetchone()[0] == 0:
        students = []
        # Generate some mock CSE students
        for i in range(1, 41):
            num = f"{i:03d}"
            students.append((f"24CSE{num}", f"CSE Student {num}", 'CSE'))
        
        # Generate some mock IT students
        for i in range(1, 31):
            num = f"{i:03d}"
            students.append((f"24IT{num}", f"IT Student {num}", 'IT'))
            
        # Generate some mock ECE students
        for i in range(1, 26):
            num = f"{i:03d}"
            students.append((f"24ECE{num}", f"ECE Student {num}", 'ECE'))
            
        cursor.executemany(
            'INSERT INTO students_master (register_number, name, department) VALUES (?, ?, ?)',
            students
        )

# ─────────────────────────────────────────────────────────────
# STUDENT MASTER CRUD (Removed year and semester)
# ─────────────────────────────────────────────────────────────

def add_student(register_number, name, department):
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO students_master (register_number, name, department) VALUES (?, ?, ?)',
            (register_number, name, department)
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, f"Student with Register Number '{register_number}' already exists."
    finally:
        conn.close()

def add_students_batch(students_list):
    conn = get_db_connection()
    success_count = 0
    for s in students_list:
        try:
            conn.execute(
                '''INSERT OR REPLACE INTO students_master 
                   (register_number, name, department) 
                   VALUES (?, ?, ?)''',
                (s['register_number'], s['name'], s['department'])
            )
            success_count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return success_count

def update_student(register_number, name, department):
    conn = get_db_connection()
    conn.execute(
        'UPDATE students_master SET name = ?, department = ? WHERE register_number = ?',
        (name, department, register_number)
    )
    conn.commit()
    conn.close()

def delete_student(register_number):
    conn = get_db_connection()
    conn.execute('DELETE FROM students_master WHERE register_number = ?', (register_number,))
    conn.commit()
    conn.close()

def get_all_students(search_query=None, department=None):
    conn = get_db_connection()
    query = 'SELECT * FROM students_master WHERE 1=1'
    params = []
    if search_query:
        query += ' AND (register_number LIKE ? OR name LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if department:
        query += ' AND department = ?'
        params.append(department)
    
    query += ' ORDER BY register_number'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_filters():
    conn = get_db_connection()
    departments = [r[0] for r in conn.execute('SELECT DISTINCT department FROM students_master ORDER BY department').fetchall() if r[0]]
    conn.close()
    return {'departments': departments}


# ─────────────────────────────────────────────────────────────
# FACULTY MASTER CRUD
# ─────────────────────────────────────────────────────────────

def add_faculty(faculty_id, name, department):
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO faculty_master (faculty_id, name, department) VALUES (?, ?, ?)',
            (faculty_id, name, department)
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, f"Faculty ID '{faculty_id}' already exists."
    finally:
        conn.close()

def add_faculty_batch(faculty_list):
    conn = get_db_connection()
    success_count = 0
    for f in faculty_list:
        try:
            fid = f.get('faculty_id') or f.get('id')
            if not fid:
                fid = 'FAC' + str(abs(hash(f['invigilator'])) % 100000).zfill(5)
            
            conn.execute(
                'INSERT OR REPLACE INTO faculty_master (faculty_id, name, department) VALUES (?, ?, ?)',
                (fid, f['invigilator'], f.get('department', 'N/A'))
            )
            success_count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return success_count

def update_faculty(faculty_id, name, department):
    conn = get_db_connection()
    conn.execute(
        'UPDATE faculty_master SET name = ?, department = ? WHERE faculty_id = ?',
        (name, department, faculty_id)
    )
    conn.commit()
    conn.close()

def delete_faculty(faculty_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM faculty_master WHERE faculty_id = ?', (faculty_id,))
    conn.commit()
    conn.close()

def get_all_faculty(search_query=None, department=None):
    conn = get_db_connection()
    query = 'SELECT * FROM faculty_master WHERE 1=1'
    params = []
    if search_query:
        query += ' AND (faculty_id LIKE ? OR name LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if department:
        query += ' AND department = ?'
        params.append(department)
    
    query += ' ORDER BY name'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────
# ROOM MASTER CRUD
# ─────────────────────────────────────────────────────────────

def add_room(room_number, block, capacity, rows_count, cols_count):
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO rooms_master (room_number, block, capacity, rows, cols) VALUES (?, ?, ?, ?, ?)',
            (room_number, block, capacity, rows_count, cols_count)
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, f"Room '{room_number}' already exists."
    finally:
        conn.close()

def update_room(room_number, block, capacity, rows_count, cols_count):
    conn = get_db_connection()
    conn.execute(
        'UPDATE rooms_master SET block = ?, capacity = ?, rows = ?, cols = ? WHERE room_number = ?',
        (block, capacity, rows_count, cols_count, room_number)
    )
    conn.commit()
    conn.close()

def delete_room(room_number):
    conn = get_db_connection()
    conn.execute('DELETE FROM rooms_master WHERE room_number = ?', (room_number,))
    conn.commit()
    conn.close()

def get_all_rooms(search_query=None):
    conn = get_db_connection()
    query = 'SELECT * FROM rooms_master WHERE 1=1'
    params = []
    if search_query:
        query += ' AND (room_number LIKE ? OR block LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    query += ' ORDER BY room_number'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
