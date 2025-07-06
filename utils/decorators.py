"""
Common decorators used across the application
"""
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def permission_required(permission):
    """Decorator to check if user has a specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission):
                flash(f'You do not have permission to {permission.replace("_", " ")}.', 'error')
                return redirect(url_for('core.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator 