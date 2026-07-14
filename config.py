# config.py - Application Configuration

import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'exam-seating-secret-key-2024')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    PDF_FOLDER = os.path.join(os.path.dirname(__file__), 'generated_pdf')
    LOGO_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'logos')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

    # Default admin credentials
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'admin123'

    # Seating flow types
    SEATING_FLOWS = {
        'zigzag': 'Zig-Zag Seating',
        'column': 'Column Wise Seating',
        'reverse': 'Reverse Seating',
        'progressive': 'Progressive Bench Seating',
        'mixed': 'Mixed Department Anti-Cheating Seating'
    }
