from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import db, User, Permission
from functools import wraps
import secrets
from datetime import datetime, timedelta
from flask_mail import Mail, Message

auth = Blueprint('auth', __name__)
mail = Mail()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need administrator privileges to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(permission):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            # Check if account is locked
            if user.is_account_locked():
                flash('Account is temporarily locked due to too many failed attempts. Please try again later.', 'error')
                return render_template('auth/login.html')
            
            if user.verify_password(password):
                # Reset failed login attempts on successful login
                user.reset_failed_login()
                
                # Log successful login
                user.log_activity(
                    'login',
                    'Successful login',
                    request.remote_addr,
                    request.user_agent.string
                )
                
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                if not next_page or urlparse(next_page).netloc != '':
                    next_page = url_for('core.index')
                return redirect(next_page)
            else:
                # Increment failed login attempts
                user.increment_failed_login()
                
                # Log failed login attempt
                user.log_activity(
                    'failed_login',
                    'Failed login attempt',
                    request.remote_addr,
                    request.user_agent.string
                )
        
        flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    # Log logout activity
    current_user.log_activity(
        'logout',
        'User logged out',
        request.remote_addr,
        request.user_agent.string
    )
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/users')
@login_required
@admin_required
def users_list():
    users = User.query.all()
    return render_template('auth/users.html', users=users)

@auth.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        is_admin = request.form.get('is_admin') == 'true'
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('auth.create_user'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('auth.create_user'))
        
        user = User(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_admin=is_admin
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('User created successfully!', 'success')
        return redirect(url_for('auth.users_list'))
    
    return render_template('auth/create_user.html')

@auth.route('/users/<int:user_id>/permissions', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_permissions(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Cannot modify admin permissions', 'error')
        return redirect(url_for('auth.users_list'))
    
    if request.method == 'POST':
        # Clear existing permissions
        user.permissions = []
        
        # Add selected permissions
        for permission in Permission.get_all_permissions():
            if request.form.get(permission):
                user.add_permission(permission)
        
        db.session.commit()
        flash(f'Permissions updated for {user.username}', 'success')
        return redirect(url_for('auth.users_list'))
    
    return render_template('auth/manage_permissions.html', user=user, all_permissions=Permission.get_all_permissions())

@auth.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        return jsonify({'error': 'Cannot deactivate admin account'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} has been {status}', 'success')
    return jsonify({'success': True, 'is_active': user.is_active})

@auth.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password')
    
    if not new_password:
        return jsonify({'error': 'New password is required'}), 400
    
    user.password = new_password
    db.session.commit()
    
    flash(f'Password reset for user {user.username}', 'success')
    return jsonify({'success': True})

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate token
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()
            
            # Send email
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg = Message('Password Reset Request',
                        sender='noreply@yourdomain.com',
                        recipients=[user.email])
            msg.body = f'''To reset your password, visit the following link:
{reset_url}

If you did not make this request, simply ignore this email and no changes will be made.

This link will expire in 24 hours.
'''
            mail.send(msg)
            
            flash('An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('auth.login'))
        else:
            # Don't reveal if email exists or not for security
            flash('If an account exists with that email, a password reset link will be sent.', 'info')
            return redirect(url_for('auth.forgot_password'))
    
    return render_template('auth/forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    user = User.query.filter_by(reset_token=token).first()
    
    if user is None or user.reset_token_expiry < datetime.utcnow():
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_password', token=token))
        
        user.password = password
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        
        flash('Your password has been updated! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html')

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Update profile information
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.email = request.form.get('email')
        
        # Handle password change if provided
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if current_password and new_password:
            if not current_user.verify_password(current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('auth.profile'))
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('auth.profile'))
            
            # Validate password complexity
            if not validate_password_complexity(new_password):
                flash('Password must be at least 8 characters long and contain uppercase, lowercase, numbers, and special characters', 'error')
                return redirect(url_for('auth.profile'))
            
            current_user.password = new_password
        
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html')

def validate_password_complexity(password):
    """
    Validate password complexity requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    """
    if len(password) < 8:
        return False
    if not any(c.isupper() for c in password):
        return False
    if not any(c.islower() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        return False
    return True 