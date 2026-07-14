# excel_loader.py - Excel File Handler  v5
# UPDATED: register_number mapping, graceful fallback, broad column name support

import pandas as pd
import os


# All accepted aliases for the register number column
_REGISTER_ALIASES = {
    'registerno', 'register no', 'register_no', 'register number',
    'register_number', 'rollno', 'roll no', 'roll_no', 'roll number',
    'roll_number', 'regno', 'reg no', 'reg_no',
}

# All accepted aliases for the name column
_NAME_ALIASES = {
    'name', 'student name', 'student_name', 'fullname', 'full name', 'full_name',
}

# All accepted aliases for the department column
_DEPT_ALIASES = {
    'department', 'dept', 'branch',
}


def _find_column(df_cols, aliases):
    """Return the first df column that matches any alias (case-insensitive), or None."""
    normalized = {col: col.strip().lower().replace(' ', '').replace('_', '') for col in df_cols}
    alias_flat = {a.replace(' ', '').replace('_', '') for a in aliases}
    for orig, norm in normalized.items():
        if norm in alias_flat:
            return orig
    return None


def validate_excel_format(filepath):
    """
    Validate the uploaded Excel file.
    Accepts RegisterNo / Register Number / rollno / roll_no etc. -> register_number
    Returns (is_valid: bool, message: str)
    """
    try:
        df = pd.read_excel(filepath)

        if len(df.columns) == 0 or len(df) == 0:
            return False, "Excel file is empty. Please upload a file with student data."

        reg_col  = _find_column(df.columns.tolist(), _REGISTER_ALIASES)
        dept_col = _find_column(df.columns.tolist(), _DEPT_ALIASES)

        if reg_col is None:
            return False, (
                "Missing Register Number column. Accepted names: "
                "RegisterNo, Register Number, roll_no, RollNo, RegNo"
            )

        if dept_col is None:
            return False, "Missing Department column. Accepted names: Department, Dept, Branch"

        if df[reg_col].isnull().any():
            return False, "Register Number column contains empty values. Please fix and re-upload."

        if df[dept_col].isnull().any():
            return False, "Department column contains empty values. Please fix and re-upload."

        if df[reg_col].astype(str).duplicated().any():
            dupes = df[df[reg_col].astype(str).duplicated()][reg_col].tolist()
            return False, f"Duplicate Register Numbers found: {dupes[:5]}. Please fix and re-upload."

        return True, f"File validated successfully. {len(df)} students found."

    except Exception as e:
        return False, f"Error reading Excel file: {str(e)}"


def load_students_from_excel(filepath):
    """
    Load student data from Excel file.
    Returns list of dicts:
        [{'register_number': '2021CSE001', 'name': 'Alice', 'department': 'CSE'}, ...]
    Falls back gracefully if name column is absent.
    """
    try:
        df = pd.read_excel(filepath)

        reg_col  = _find_column(df.columns.tolist(), _REGISTER_ALIASES)
        dept_col = _find_column(df.columns.tolist(), _DEPT_ALIASES)
        name_col = _find_column(df.columns.tolist(), _NAME_ALIASES)

        if reg_col is None or dept_col is None:
            return None, "Required columns not found. Please check column headers."

        students = []
        for _, row in df.iterrows():
            reg_no = str(row[reg_col]).strip()
            dept   = str(row[dept_col]).strip().upper()
            name   = str(row[name_col]).strip() if name_col else reg_no

            if reg_no and reg_no.lower() not in ('nan', 'none', ''):
                students.append({
                    'register_number': reg_no,
                    'name':            name,
                    'department':      dept,
                    'roll_no':         reg_no,   # backward-compat alias
                })

        return students, None

    except Exception as e:
        return None, f"Error loading students: {str(e)}"


def get_department_summary(students):
    summary = {}
    for s in students:
        dept = s.get('department', 'UNKNOWN')
        summary[dept] = summary.get(dept, 0) + 1
    return summary
