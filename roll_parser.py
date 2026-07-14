# roll_parser.py  – v8 helpers
# New functions:
#   parse_manual_rolls()   – comma / newline separated roll numbers
#   generate_start_end()   – prefix+number range via regex
#   remove_missing_rolls() – filter out absent/missing roll numbers

import re
from roll_range_helper import detect_department


# ─────────────────────────────────────────────────────────────
# 1.  MANUAL ROLL ENTRY
# ─────────────────────────────────────────────────────────────

def parse_manual_rolls(text: str, override_dept: str = ''):
    """
    Accept comma-separated or newline-separated roll numbers.

    Returns:
        (students: list[dict], error: str | None)
    """
    if not text or not text.strip():
        return [], "Manual roll entry is empty."

    # Split on comma or newline, clean up whitespace
    raw_tokens = re.split(r'[,\n]+', text)
    tokens = [t.strip().upper() for t in raw_tokens if t.strip()]

    if not tokens:
        return [], "No valid roll numbers found."

    seen = set()
    students = []

    for token in tokens:
        if not re.match(r'^[A-Z0-9]+$', token):
            return [], f"Invalid roll number format: '{token}'. Use alphanumeric characters only."

        if token in seen:
            continue  # silently remove duplicates
        seen.add(token)

        m = re.match(r'^(.*?)(\d+)$', token)
        prefix = m.group(1) if m else token
        dept = override_dept.strip().upper() if override_dept else detect_department(prefix)

        students.append({
            'register_number': token,
            'name':            token,
            'department':      dept,
            'roll_no':         token,
        })

    if not students:
        return [], "No valid roll numbers were parsed."

    return students, None


# ─────────────────────────────────────────────────────────────
# 2.  START–END SIMPLE INPUT
# ─────────────────────────────────────────────────────────────

def generate_start_end(start_roll: str, end_roll: str, override_dept: str = ''):
    """
    Generate a list of roll numbers from start_roll to end_roll.
    Uses regex ^(.*?)(\\d+)$ to split prefix from numeric part.

    Returns:
        (students: list[dict], error: str | None)
    """
    start_roll = start_roll.strip().upper()
    end_roll   = end_roll.strip().upper()

    if not start_roll:
        return [], "Start roll number is required."
    if not end_roll:
        return [], "End roll number is required."

    m_start = re.match(r'^(.*?)(\d+)$', start_roll)
    m_end   = re.match(r'^(.*?)(\d+)$', end_roll)

    if not m_start:
        return [], f"Cannot parse start roll number: '{start_roll}'. Format: 24IT001"
    if not m_end:
        return [], f"Cannot parse end roll number: '{end_roll}'. Format: 24IT120"

    start_prefix, start_num_str = m_start.group(1), m_start.group(2)
    end_prefix,   end_num_str   = m_end.group(1),   m_end.group(2)

    if start_prefix != end_prefix:
        return [], (f"Prefix mismatch: '{start_prefix}' ≠ '{end_prefix}'. "
                    "Start and End must share the same prefix (e.g., both 24IT).")

    start_num = int(start_num_str)
    end_num   = int(end_num_str)

    if start_num > end_num:
        return [], f"Start number ({start_num}) must be ≤ end number ({end_num})."

    if (end_num - start_num + 1) > 2000:
        return [], f"Range too large ({end_num - start_num + 1}). Maximum is 2000 per range."

    padding = len(start_num_str)
    prefix  = start_prefix
    dept    = override_dept.strip().upper() if override_dept else detect_department(prefix)

    students = []
    for n in range(start_num, end_num + 1):
        roll = f"{prefix}{str(n).zfill(padding)}"
        students.append({
            'register_number': roll,
            'name':            roll,
            'department':      dept,
            'roll_no':         roll,
        })

    return students, None


# ─────────────────────────────────────────────────────────────
# 3.  REMOVE MISSING ROLLS
# ─────────────────────────────────────────────────────────────

def remove_missing_rolls(students: list, missing_text: str):
    """
    Remove roll numbers listed in missing_text from the students list.
    missing_text: comma-separated or newline-separated roll numbers.

    Returns:
        (filtered_students: list[dict], removed_count: int)
    """
    if not missing_text or not missing_text.strip():
        return students, 0

    raw = re.split(r'[,\n]+', missing_text)
    missing_set = {t.strip().upper() for t in raw if t.strip()}

    if not missing_set:
        return students, 0

    filtered = [s for s in students
                if s.get('register_number', '').upper() not in missing_set]
    removed  = len(students) - len(filtered)
    return filtered, removed
