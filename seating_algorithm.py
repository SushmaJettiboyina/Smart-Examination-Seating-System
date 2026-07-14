# seating_algorithm.py - Core Seating Arrangement Algorithms
#
# KEY CHANGE: per-hall rows × columns layouts are now supported.
#
# Old API (uniform halls):
#   generate_multiple_hall_distribution(students, num_halls,
#                                       benches_per_hall, seats_per_bench,
#                                       flow_type)
#
# New API (per-hall layouts):
#   generate_multiple_hall_distribution(students, num_halls,
#                                       benches_per_hall, seats_per_bench,
#                                       flow_type,
#                                       hall_layouts=None)
#
#   hall_layouts is an optional list of dicts, one per hall:
#       [
#           {'rows': 5, 'cols': 6},   # Hall 1 → 30 seats
#           {'rows': 4, 'cols': 5},   # Hall 2 → 20 seats
#           {'rows': 6, 'cols': 6},   # Hall 3 → 36 seats
#       ]
#
#   When hall_layouts is supplied:
#     - rows  = number of benches in that hall
#     - cols  = number of seats per bench (row)
#     - capacity per hall = rows × cols
#
#   When hall_layouts is None the old uniform behaviour is preserved
#   (benches_per_hall / seats_per_bench used for every hall).

from itertools import cycle


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def mix_departments(students):
    """
    Interleave students so no two consecutive students share a department.
    Uses a round-robin approach across departments.
    Returns a new list of students in mixed order.
    """
    dept_groups = {}
    for student in students:
        dept_groups.setdefault(student['department'], []).append(student)

    # Largest department first → best interleaving
    sorted_depts = sorted(dept_groups.keys(), key=lambda d: -len(dept_groups[d]))
    queues = [dept_groups[d][:] for d in sorted_depts]

    mixed = []
    while any(queues):
        for q in queues:
            if q:
                mixed.append(q.pop(0))
    return mixed


def _chunk_into_rows(students, cols):
    """Split a flat student list into rows of `cols` seats each."""
    rows = []
    for i in range(0, len(students), cols):
        rows.append(students[i:i + cols])
    return rows


def _pad_row(row, cols):
    """Right-pad a row with None to reach `cols` seats."""
    return row + [None] * (cols - len(row))


def _build_grid(students, num_rows, cols):
    """
    Place `students` into a rows × cols grid.
    Returns a list of `num_rows` rows; each row has exactly `cols` cells
    (trailing cells are None when students run out).
    """
    grid = []
    idx = 0
    for _ in range(num_rows):
        row = []
        for _ in range(cols):
            row.append(students[idx] if idx < len(students) else None)
            idx += 1
        grid.append(row)
    return grid


# ---------------------------------------------------------------------------
# Seating Flow Algorithms
# Each returns a list of rows; each row is a list of student dicts (or None).
# ---------------------------------------------------------------------------

def zigzag_seating(students, num_rows, cols):
    """
    Zig-Zag: alternates students from the front and back of the mixed list
    so adjacent rows contain students from different departments.
    """
    mixed = mix_departments(students)
    mid   = len(mixed) // 2
    front = mixed[:mid]
    back  = mixed[mid:][::-1]

    zigzag = []
    for i in range(max(len(front), len(back))):
        if i < len(front):
            zigzag.append(front[i])
        if i < len(back):
            zigzag.append(back[i])

    return _build_grid(zigzag, num_rows, cols)


def column_wise_seating(students, num_rows, cols):
    """
    Column-wise: fills the grid column by column rather than row by row,
    so each column contains students from a mix of departments.
    """
    mixed = mix_departments(students)
    # Build empty grid then fill column by column
    grid = [[None] * cols for _ in range(num_rows)]
    idx  = 0
    for col in range(cols):
        for row in range(num_rows):
            if idx < len(mixed):
                grid[row][col] = mixed[idx]
                idx += 1
    return grid


def reverse_seating(students, num_rows, cols):
    """
    Reverse: assigns seats starting from the last position, so the
    last student in the sorted list ends up in seat (0, 0).
    """
    mixed    = mix_departments(students)
    reversed_students = mixed[::-1]
    grid     = _build_grid(reversed_students, num_rows, cols)
    return grid[::-1]   # flip row order back to front→back


def progressive_bench_seating(students, num_rows, cols):
    """
    Progressive: each row starts with a different department so the
    dominant department is never concentrated in consecutive rows.
    """
    dept_groups = {}
    for s in students:
        dept_groups.setdefault(s['department'], []).append(s)

    depts      = list(dept_groups.keys())
    dept_pools = {d: dept_groups[d][:] for d in depts}
    total      = len(students)
    assigned   = 0
    flat       = []

    for row_idx in range(num_rows):
        offset        = row_idx % len(depts)
        rotated_depts = depts[offset:] + depts[:offset]

        for seat_idx in range(cols):
            if assigned >= total:
                flat.append(None)
                continue
            placed = False
            for dept in rotated_depts[seat_idx % len(rotated_depts):] + \
                        rotated_depts[:seat_idx % len(rotated_depts)]:
                if dept_pools.get(dept):
                    flat.append(dept_pools[dept].pop(0))
                    assigned += 1
                    placed = True
                    break
            if not placed:
                # Fallback: take any remaining student
                for d in depts:
                    if dept_pools.get(d):
                        flat.append(dept_pools[d].pop(0))
                        assigned += 1
                        break
                else:
                    flat.append(None)

    return _build_grid(flat, num_rows, cols)


def mixed_department_seating(students, num_rows, cols):
    """
    Mixed Anti-Cheating: strictly prevents the same department from
    occupying adjacent seats within a row (and across rows where possible).
    """
    dept_groups = {}
    for s in students:
        dept_groups.setdefault(s['department'], []).append(dict(s))

    depts = sorted(dept_groups.keys(), key=lambda d: -len(dept_groups[d]))

    def get_next(exclude_dept, pools):
        for d in depts:
            if d != exclude_dept and pools.get(d):
                return pools[d].pop(0), d
        for d in depts:             # fallback – same dept if no choice
            if pools.get(d):
                return pools[d].pop(0), d
        return None, None

    dept_pools = {d: dept_groups[d][:] for d in depts}
    total      = len(students)
    assigned   = 0
    last_dept  = None
    flat       = []

    for _ in range(num_rows * cols):
        if assigned < total:
            student, dept = get_next(last_dept, dept_pools)
            if student:
                flat.append(student)
                last_dept = dept
                assigned += 1
                continue
        flat.append(None)

    return _build_grid(flat, num_rows, cols)


# ---------------------------------------------------------------------------
# Algorithm Dispatcher
# ---------------------------------------------------------------------------

def _apply_algorithm(students, num_rows, cols, flow_type):
    """Run the chosen algorithm and return a rows × cols grid."""
    if   flow_type == 'zigzag':      return zigzag_seating(students, num_rows, cols)
    elif flow_type == 'column':      return column_wise_seating(students, num_rows, cols)
    elif flow_type == 'reverse':     return reverse_seating(students, num_rows, cols)
    elif flow_type == 'progressive': return progressive_bench_seating(students, num_rows, cols)
    else:                            return mixed_department_seating(students, num_rows, cols)


# ---------------------------------------------------------------------------
# Per-Hall Distribution  ← main public API
# ---------------------------------------------------------------------------

def generate_multiple_hall_distribution(students,
                                        num_halls,
                                        benches_per_hall,
                                        seats_per_bench,
                                        flow_type='mixed',
                                        hall_layouts=None):
    """
    Distribute students across halls, respecting each hall's own
    rows × columns layout.

    Parameters
    ----------
    students : list of dicts  {'register_number', 'roll_no', 'name', 'department', ...}
    num_halls : int           total number of halls
    benches_per_hall : int    default rows  (used when hall_layouts is None)
    seats_per_bench  : int    default cols  (used when hall_layouts is None)
    flow_type : str           algorithm key
    hall_layouts : list | None
        Optional list of per-hall dicts: [{'rows': R, 'cols': C}, ...]
        Length must equal num_halls when supplied.
        Missing entries fall back to benches_per_hall × seats_per_bench.

    Returns
    -------
    halls : list of dicts
        hall_number   : int
        rows          : int   (number of bench rows)
        cols          : int   (seats per row / bench)
        capacity      : int   (rows × cols)
        benches       : list of rows; each row = list of student dicts | None
        total_students: int   (occupied seats)
        layout_label  : str   e.g. "5 rows × 6 cols"
    """
    # ── 1. Resolve per-hall dimensions ────────────────────────────────────
    layouts = []
    for i in range(num_halls):
        if hall_layouts and i < len(hall_layouts) and hall_layouts[i]:
            r = int(hall_layouts[i].get('rows', benches_per_hall))
            c = int(hall_layouts[i].get('cols', seats_per_bench))
        else:
            r, c = benches_per_hall, seats_per_bench
        layouts.append({'rows': r, 'cols': c})

    total_capacity = sum(L['rows'] * L['cols'] for L in layouts)

    # ── 2. Guard: warn if not enough seats (don't crash) ─────────────────
    if total_capacity < len(students):
        # Distribute as many as will fit; the caller should validate first
        students = students[:total_capacity]

    # ── 3. Proportionally allocate students to halls ──────────────────────
    #   Each hall gets ⌊ capacity / total_capacity × total_students ⌋
    #   with any remainder going to the last non-empty hall.
    total_students = len(students)
    allocations    = []
    allocated_so_far = 0

    for i, L in enumerate(layouts):
        cap = L['rows'] * L['cols']
        if i < num_halls - 1:
            share = round(cap / total_capacity * total_students)
            # Never allocate more than this hall can seat
            share = min(share, cap, total_students - allocated_so_far)
            share = max(share, 0)
        else:
            # Last hall gets whoever remains
            share = total_students - allocated_so_far
            share = min(share, cap)
            share = max(share, 0)
        allocations.append(share)
        allocated_so_far += share

    # ── 4. Build each hall ────────────────────────────────────────────────
    halls   = []
    student_cursor = 0

    for i, (L, share) in enumerate(zip(layouts, allocations)):
        rows = L['rows']
        cols = L['cols']
        cap  = rows * cols

        hall_students = students[student_cursor: student_cursor + share]
        student_cursor += share

        if share > 0:
            grid = _apply_algorithm(hall_students, rows, cols, flow_type)
        else:
            # Empty hall: create a blank grid
            grid = [[None] * cols for _ in range(rows)]

        # Pad every row to exactly `cols` cells
        grid = [_pad_row(row, cols) for row in grid]

        halls.append({
            'hall_number':    i + 1,
            'rows':           rows,
            'cols':           cols,
            'capacity':       cap,
            'benches':        grid,          # grid[row_idx][col_idx]
            'total_students': share,
            'layout_label':   f'{rows} rows × {cols} cols',
        })

    return halls


# ---------------------------------------------------------------------------
# Stats Helper
# ---------------------------------------------------------------------------

def get_seating_stats(halls):
    """
    Aggregate summary statistics across all halls.

    Returns
    -------
    dict with:
        total_students       : int
        total_halls          : int
        total_capacity       : int
        utilization_pct      : float
        department_breakdown : dict  {dept: count}
        hall_summary         : list  [{'hall': N, 'rows': R, 'cols': C,
                                        'students': S, 'capacity': C,
                                        'layout_label': str}, ...]
    """
    total_students = sum(h['total_students'] for h in halls)
    total_capacity = sum(h['capacity']       for h in halls)
    dept_counts    = {}
    hall_summary   = []

    for hall in halls:
        for row in hall['benches']:
            for seat in row:
                if seat:
                    dept = seat['department']
                    dept_counts[dept] = dept_counts.get(dept, 0) + 1

        hall_summary.append({
            'hall':         hall['hall_number'],
            'rows':         hall['rows'],
            'cols':         hall['cols'],
            'students':     hall['total_students'],
            'capacity':     hall['capacity'],
            'layout_label': hall.get('layout_label', ''),
        })

    return {
        'total_students':       total_students,
        'total_halls':          len(halls),
        'total_capacity':       total_capacity,
        'utilization_pct':      round(total_students / total_capacity * 100, 1)
                                if total_capacity else 0,
        'department_breakdown': dept_counts,
        'hall_summary':         hall_summary,
    }


# ---------------------------------------------------------------------------
# Convenience: validate hall layouts before generation
# ---------------------------------------------------------------------------

def validate_hall_layouts(num_halls, hall_layouts, total_students):
    """
    Check that the supplied layouts have enough capacity for all students.

    Returns (is_valid: bool, message: str, total_capacity: int)
    """
    if not hall_layouts:
        return True, 'No per-hall layouts supplied; using uniform defaults.', 0

    if len(hall_layouts) != num_halls:
        return (False,
                f'Expected {num_halls} hall layout entries, got {len(hall_layouts)}.',
                0)

    total_capacity = 0
    for i, L in enumerate(hall_layouts, 1):
        r = int(L.get('rows', 0))
        c = int(L.get('cols', 0))
        if r <= 0 or c <= 0:
            return False, f'Hall {i}: rows and cols must both be > 0.', 0
        total_capacity += r * c

    if total_capacity < total_students:
        shortage = total_students - total_capacity
        return (False,
                f'Total capacity {total_capacity} is {shortage} seats short '
                f'for {total_students} students.',
                total_capacity)

    return (True,
            f'Layouts valid. Total capacity: {total_capacity} seats '
            f'for {total_students} students.',
            total_capacity)
