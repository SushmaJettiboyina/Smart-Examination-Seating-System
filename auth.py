# auth.py - Authentication Handler

from functools import wraps
from flask import session, redirect, url_for, flash
from config import Config


def login_required(f):
    """Decorator to protect routes that require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access the dashboard.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def check_credentials(username, password):
    """Validate admin login credentials."""
    return (username == Config.ADMIN_USERNAME and
            password == Config.ADMIN_PASSWORD)


def login_user():
    """Set session variables for logged-in user."""
    session['logged_in'] = True
    session['username'] = Config.ADMIN_USERNAME


def logout_user():
    """Clear session variables."""
    session.clear()
