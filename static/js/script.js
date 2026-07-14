// script.js - Frontend JavaScript for AI Exam Seating System

'use strict';

// -----------------------------------------------------------------------
// Auto-dismiss alerts after 5 seconds
// -----------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    const alerts = document.querySelectorAll('.alert.fade.show');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});

// -----------------------------------------------------------------------
// Active nav link highlight (fallback)
// -----------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar-nav .nav-link');
    navLinks.forEach(function (link) {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
});

// -----------------------------------------------------------------------
// Department color assignment for dynamic dept names
// (used when dept isn't CSE/IT/ECE/EEE/MECH/CIVIL)
// -----------------------------------------------------------------------
const DEPT_COLORS = [
    { bg: '#dbeafe', text: '#1e40af' },
    { bg: '#dcfce7', text: '#166534' },
    { bg: '#fce7f3', text: '#9d174d' },
    { bg: '#ede9fe', text: '#5b21b6' },
    { bg: '#ffedd5', text: '#9a3412' },
    { bg: '#ecfdf5', text: '#047857' },
    { bg: '#fef9c3', text: '#854d0e' },
    { bg: '#f0fdf4', text: '#14532d' },
];

document.addEventListener('DOMContentLoaded', function () {
    const knownDepts = ['cse', 'it', 'ece', 'eee', 'mech', 'civil'];
    const seatCells = document.querySelectorAll('.seat-cell');
    const deptColorMap = {};
    let colorIdx = 0;

    seatCells.forEach(function (cell) {
        // Find dept from classes
        const classes = Array.from(cell.classList);
        const deptClass = classes.find(c => c.startsWith('dept-') && c !== 'seat-empty');

        if (deptClass) {
            const dept = deptClass.replace('dept-', '');
            if (!knownDepts.includes(dept)) {
                if (!deptColorMap[dept]) {
                    deptColorMap[dept] = DEPT_COLORS[colorIdx % DEPT_COLORS.length];
                    colorIdx++;
                }
                const color = deptColorMap[dept];
                cell.style.background = color.bg;
                cell.style.color = color.text;
            }
        }
    });
});

// -----------------------------------------------------------------------
// Table search / filter (for large seating tables)
// -----------------------------------------------------------------------
function filterSeatingTable(searchTerm) {
    const rows = document.querySelectorAll('.seating-table tbody tr');
    const term = searchTerm.toLowerCase().trim();

    rows.forEach(function (row) {
        const text = row.textContent.toLowerCase();
        row.style.display = (!term || text.includes(term)) ? '' : 'none';
    });
}

// -----------------------------------------------------------------------
// Print current hall
// -----------------------------------------------------------------------
function printCurrentHall() {
    window.print();
}

// -----------------------------------------------------------------------
// Toast notification utility
// -----------------------------------------------------------------------
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    const id = 'toast-' + Date.now();
    const iconMap = {
        success: 'fa-check-circle text-success',
        danger: 'fa-exclamation-circle text-danger',
        warning: 'fa-exclamation-triangle text-warning',
        info: 'fa-info-circle text-info',
    };

    const html = `
        <div id="${id}" class="toast align-items-center" role="alert" data-bs-autohide="true" data-bs-delay="4000">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas ${iconMap[type] || iconMap.info} me-2"></i>${message}
                </div>
                <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>`;

    toastContainer.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(id);
    const toast = new bootstrap.Toast(el);
    toast.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

// -----------------------------------------------------------------------
// Animate stat counters on dashboard load
// -----------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    const counters = document.querySelectorAll('.stat-info h3');
    counters.forEach(function (counter) {
        const target = parseInt(counter.textContent.replace(/\D/g, ''));
        if (isNaN(target) || target === 0) return;

        let current = 0;
        const step = Math.max(1, Math.floor(target / 30));
        const suffix = counter.textContent.includes('%') ? '%' : '';

        const timer = setInterval(function () {
            current = Math.min(current + step, target);
            counter.textContent = current + suffix;
            if (current >= target) clearInterval(timer);
        }, 30);
    });
});


// ── v5: Image Export via html2canvas ──
function downloadAsImage(targetId, filename) {
    filename = filename || 'seating_arrangement.png';
    const target = document.getElementById(targetId || 'seatingContainer');
    if (!target) { alert('Nothing to export.'); return; }
    if (typeof html2canvas === 'undefined') {
        alert('html2canvas not loaded. Please refresh and try again.');
        return;
    }
    html2canvas(target, {
        backgroundColor: '#f8fafc',
        scale: 2,
        useCORS: true,
        logging: false
    }).then(canvas => {
        const link = document.createElement('a');
        link.download = filename;
        link.href = canvas.toDataURL('image/png');
        link.click();
    }).catch(err => {
        console.error('Image export failed:', err);
        alert('Image export failed. Please try again.');
    });
}


// ── v5: Filter helper for exam name filter ──
function applyExamFilter() {
    const exam = (document.getElementById('filterExam') || {}).value || '';
    const dept = (document.getElementById('filterDept') || {}).value || '';
    const hall = (document.getElementById('filterHall') || {}).value || '';
    const reg  = (document.getElementById('filterReg') || {}).value || '';
    let url = '/api/filter?';
    if (dept) url += `department=${encodeURIComponent(dept)}&`;
    if (hall) url += `hall=${encodeURIComponent(hall)}&`;
    if (exam) url += `exam=${encodeURIComponent(exam)}&`;
    if (reg)  url += `reg=${encodeURIComponent(reg)}&`;
    return fetch(url).then(r => r.json());
}
