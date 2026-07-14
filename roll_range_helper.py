# roll_range_helper.py - Roll Number Range Generator
# Supports formats like:
#   "24IT001 TO 24IT120"
#   "22CSE01 TO 22CSE60"
#   "CS1 TO CS50"
#   "24IT001 TO 24IT060, 24CSE001 TO 24CSE050"  (multiple ranges)

import re

# ─────────────────────────────────────────────────────────────
# Department keyword detection map
# Longest match first to avoid "CS" matching inside "CSE"
# ─────────────────────────────────────────────────────────────
_DEPT_KEYWORDS = [
    ('MECH',  'MECH'),
    ('CIVIL', 'CIVIL'),
    ('AIDS',  'AIDS'),
    ('AIML',  'AIML'),
    ('CSBS',  'CSBS'),
    ('CSE',   'CSE'),
    ('ECE',   'ECE'),
    ('EEE',   'EEE'),
    ('MBA',   'MBA'),
    ('MCA',   'MCA'),
    ('MCE',   'MCE'),
    ('BME',   'BME'),
    ('CSD',   'CSD'),
    ('IT',    'IT'),
    ('CS',    'CS'),
    ('EE',    'EE'),
    ('ME',    'ME'),
    ('CE',    'CE'),
    ('IS',    'IS'),
    ('DS',    'DS'),
    ('AI',    'AI'),
]


def detect_department(prefix: str) -> str:
    """
    Extract a department label from a roll-number prefix.

    Examples:
        '24IT'   → 'IT'
        '22CSE'  → 'CSE'
        'CS'     → 'CS'
        '24MECH' → 'MECH'
        'ABC'    → 'ABC'   (falls back to the whole alpha portion)
    """
    upper = prefix.upper()
    # Strip leading digits (e.g., '24' from '24IT')
    alpha_part = re.sub(r'^\d+', '', upper)

    for keyword, dept in _DEPT_KEYWORDS:
        if keyword in alpha_part:
            return dept

    # Fallback: use the alpha portion itself, or the full prefix
    return alpha_part if alpha_part else upper


def _split_roll(roll: str):
    """
    Split a roll number string into (prefix, number_str).

    '24IT001' → ('24IT', '001')
    'CS50'    → ('CS',   '50')
    '22CSE01' → ('22CSE','01')
    """
    roll = roll.strip().upper()
    m = re.match(r'^(.*?)(\d+)$', roll)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _parse_single_range(range_str: str):
    """
    Parse one 'START TO END' range string.
    Returns list of student dicts, or raises ValueError with a human-readable message.
    """
    range_str = range_str.strip().upper()

    # Match: <ROLL> TO <ROLL>  (case-insensitive TO)
    m = re.match(r'^(.+?)\s+TO\s+(.+)$', range_str, re.IGNORECASE)
    if not m:
        raise ValueError(
            f"Invalid format: '{range_str}'. "
            "Expected format: '24IT001 TO 24IT120'"
        )

    start_raw, end_raw = m.group(1).strip(), m.group(2).strip()
    start_prefix, start_num_str = _split_roll(start_raw)
    end_prefix,   end_num_str   = _split_roll(end_raw)

    if start_prefix is None:
        raise ValueError(f"Cannot parse start roll number: '{start_raw}'")
    if end_prefix is None:
        raise ValueError(f"Cannot parse end roll number: '{end_raw}'")
    if start_prefix != end_prefix:
        raise ValueError(
            f"Prefix mismatch: '{start_prefix}' ≠ '{end_prefix}'. "
            "Both roll numbers must share the same prefix."
        )

    start_num = int(start_num_str)
    end_num   = int(end_num_str)

    if start_num > end_num:
        raise ValueError(
            f"Start number ({start_num}) must be ≤ end number ({end_num})."
        )

    max_range = 2000
    if (end_num - start_num + 1) > max_range:
        raise ValueError(
            f"Range too large: {end_num - start_num + 1} students. "
            f"Maximum allowed per range is {max_range}."
        )

    padding   = len(start_num_str)   # preserve zero-padding from start
    prefix    = start_prefix          # e.g. '24IT'
    dept      = detect_department(prefix)

    students = []
    for n in range(start_num, end_num + 1):
        roll_no = f"{prefix}{str(n).zfill(padding)}"
        students.append({
            'register_number': roll_no,
            'name':            roll_no,   # no name available; use roll number
            'department':      dept,
            'roll_no':         roll_no,   # backward-compat alias
        })

    return students


def generate_roll_range(input_text: str, override_dept: str = ''):
    """
    Public API — parse one or more comma-separated ranges.

    Args:
        input_text   : e.g. "24IT001 TO 24IT120"
                       or    "24IT001 TO 24IT060, 24CSE001 TO 24CSE050"
        override_dept: if non-empty, override auto-detected department for
                       ALL generated students (e.g. from a UI dropdown).

    Returns:
        (students: list[dict], error: str | None)

        students format:
            [{'register_number': '24IT001', 'name': '24IT001',
              'department': 'IT', 'roll_no': '24IT001'}, ...]
    """
    if not input_text or not input_text.strip():
        return [], "Input is empty. Please enter a roll number range."

    # Split on commas to support multiple ranges
    range_parts = [p.strip() for p in input_text.split(',') if p.strip()]
    if not range_parts:
        return [], "No valid range found in input."

    all_students = []
    seen_roll_nos = set()

    for part in range_parts:
        try:
            students = _parse_single_range(part)
        except ValueError as e:
            return [], str(e)

        for s in students:
            rn = s['register_number']
            if rn in seen_roll_nos:
                return [], f"Duplicate roll number detected: '{rn}'. Check your ranges for overlaps."
            seen_roll_nos.add(rn)

            if override_dept:
                s['department'] = override_dept.strip().upper()

            all_students.append(s)

    if not all_students:
        return [], "No students were generated. Please check your input."

    return all_students, None
