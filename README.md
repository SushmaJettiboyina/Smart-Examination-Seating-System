# AI Exam Seating Arrangement System  v4

A complete Flask-based web application for generating, previewing, and editing
exam seating arrangements with per-hall row × column layout support.

---

## Features

| Feature | Description |
|---|---|
| Admin login | Secure session-based login (admin / admin123) |
| Excel upload | Upload student list (RollNo + Department columns) |
| Per-hall layouts | Each hall can have its own rows × cols grid |
| 5 seating algorithms | Zig-Zag, Column-wise, Reverse, Progressive, Mixed Anti-Cheating |
| Seating preview | Visual grid view of every hall's arrangement |
| Drag & Drop editor | Swap seats by dragging one card onto another |
| Inline seat editing | Click any seat to edit Roll No, Name, and Department |
| Undo / Redo | Full undo/redo stack (Ctrl+Z / Ctrl+Y) |
| PDF generation | Professional ReportLab PDF per hall with logo support |
| Bulk PDF download | Download all halls as a single ZIP |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the server

```bash
python app.py
```

### 3. Open in browser

```
http://127.0.0.1:5000
```

### 4. Login

| Field    | Value    |
|----------|----------|
| Username | admin    |
| Password | admin123 |

---

## Workflow

```
Upload Excel  →  Generate Seating  →  View Results  →  Edit Seats  →  Download PDF
```

1. **Upload** — go to *Upload Students* and upload `static/sample_students.xlsx`
   (or your own file with `RollNo` and `Department` columns).

2. **Generate** — fill in college info, set the number of halls, then configure
   each hall's rows × columns individually. Choose a seating algorithm and click
   *Generate Seating Arrangement*.

3. **View Results** — browse the seating table hall by hall. Download per-hall
   PDFs or all PDFs at once.

4. **Seat Editor** — drag seat cards to swap students, or switch to *Click to Edit*
   mode to change a student's Roll No, Name, or Department inline. Hit *Save Seating*
   — the session and PDFs update automatically.

---

## Excel File Format

| RollNo | Department |
|--------|------------|
| 101    | CSE        |
| 102    | CSE        |
| 201    | IT         |
| 301    | ECE        |

- Column headers must be exactly `RollNo` and `Department` (case-insensitive).
- No duplicate Roll Numbers.
- No blank cells in either column.

A ready-to-use sample file is at `static/sample_students.xlsx` (100 students,
5 departments: CSE, IT, ECE, EEE, MECH).

---

## Per-Hall Layout Example

On the Generate page, after setting the number of halls you can give each hall
its own rows × columns:

| Hall | Rows | Cols | Capacity |
|------|------|------|----------|
| 1    | 5    | 6    | 30       |
| 2    | 4    | 5    | 20       |
| 3    | 6    | 6    | 36       |

Total capacity must be ≥ number of students. The live capacity calculator on
the page shows you whether you have enough seats before submitting.

---

## Project Structure

```
exam_seating_ai_system/
├── app.py                  # Flask routes & application logic
├── seating_algorithm.py    # 5 seating algorithms + per-hall distribution
├── excel_loader.py         # Excel validation & student loading
├── pdf_generator.py        # ReportLab PDF generation
├── config.py               # App configuration
├── auth.py                 # Login / session helpers
├── requirements.txt
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── generate.html       # Per-hall rows × cols configuration UI
│   ├── seating_result.html
│   └── seating_preview.html  # Drag-drop + inline seat editor
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── sample_students.xlsx
├── uploads/                # Auto-created at runtime
└── generated_pdf/          # Auto-created at runtime
```

---

## Seating Algorithms

| Key | Name | Description |
|-----|------|-------------|
| `zigzag` | Zig-Zag | Alternates front/back halves across rows |
| `column` | Column-Wise | Fills column by column for dept mixing |
| `reverse` | Reverse | Fills from last seat backwards |
| `progressive` | Progressive | Rotates dept starting position per row |
| `mixed` | Mixed Anti-Cheating | Strict adjacent-seat dept separation |

---

## Default Credentials

Change these in `config.py` before deploying:

```python
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'
```

---

## Dependencies

```
flask
pandas
openpyxl
reportlab
pillow
```
