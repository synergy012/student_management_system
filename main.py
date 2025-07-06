"""
Legacy main.py - DEPRECATED
===============================
All routes have been migrated to individual blueprints.
This file is kept only for backward compatibility and will be removed in future versions.

Route Migration Map:
- Core routes (/, /test): blueprints/core.py
- Student routes: blueprints/students.py  
- Application routes: blueprints/applications.py
- Academic routes: blueprints/academic.py
- Settings routes: blueprints/settings.py
- Kollel routes: blueprints/kollel.py
- Dormitory routes: blueprints/dormitories.py
- Report routes: blueprints/reports.py
- File routes: blueprints/files.py
- Financial routes: blueprints/financial.py
- Webhook routes: blueprints/webhooks.py
"""

from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user
from functools import wraps

# Create blueprint (kept for compatibility - not registered in app.py)
main = Blueprint('main', __name__)

def permission_required(permission):
    """
    Permission decorator - kept for any legacy imports.
    Note: New code should use utils.decorators.permission_required instead.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission):
                flash(f'You do not have permission to {permission.replace("_", " ")}.', 'error')
                return redirect(url_for('core.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================================================================
# MIGRATION COMPLETE
# =============================================================================
# 
# Before: main.py was 5,159 lines with ALL application routes
# After:  main.py is ~40 lines with only backward compatibility code
# 
# All 200+ routes have been moved to appropriate blueprints:
# 
# ✅ Academic Module (40+ routes) -> blueprints/academic.py
# ✅ Student Management (15+ routes) -> blueprints/students.py  
# ✅ Application Processing (20+ routes) -> blueprints/applications.py
# ✅ Settings & Admin (25+ routes) -> blueprints/settings.py
# ✅ Kollel Management (15+ routes) -> blueprints/kollel.py
# ✅ Dormitory System (30+ routes) -> blueprints/dormitories.py
# ✅ Reporting System (20+ routes) -> blueprints/reports.py
# ✅ File Management (5+ routes) -> blueprints/files.py
# ✅ Financial Management (10+ routes) -> blueprints/financial.py
# ✅ Webhook Processing (10+ routes) -> blueprints/webhooks.py
# ✅ Core Routes (5+ routes) -> blueprints/core.py
# 
# Benefits of modularization:
# - Better code organization and maintainability
# - Easier testing and debugging
# - Clear separation of concerns
# - Reduced file size and complexity
# - Improved development workflow
# =============================================================================
