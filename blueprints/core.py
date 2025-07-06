"""
Core routes for the application
"""
from flask import Blueprint, jsonify, current_app, render_template, redirect, url_for
from flask_login import login_required
from flask_mail import Message
from extensions import mail
from models import Application, AcademicYear
from utils.decorators import permission_required

core = Blueprint('core', __name__)

# Store last received webhook data (will be moved to proper storage)
last_webhook_data = None


@core.route('/')
@login_required
def index():
    """Display the dashboard."""
    # Get stats from database
    stats = {
        'pending': Application.query.filter_by(status='Pending').count(),
        'accepted': Application.query.filter_by(status='Accepted').count(),
        'rejected': Application.query.filter_by(status='Rejected').count()
    }
    
    # Get recent applications
    recent_applications = Application.query.order_by(Application.submitted_date.desc()).limit(5).all()
    
    # Get all available academic years for the global selector
    all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    available_academic_years = []
    active_year = AcademicYear.get_active_year()
    
    for ay in all_academic_years:
        available_academic_years.append({
            'id': ay.id,
            'name': ay.year_label,
            'is_selected': ay.is_active
        })
    
    return render_template('index.html', 
                         stats=stats,
                         recent_applications=recent_applications,
                         available_academic_years=available_academic_years,
                         last_webhook_data=last_webhook_data)


@core.route('/test_email')
@login_required
@permission_required('manage_users')
def test_email():
    """Test email configuration by sending a test email."""
    try:
        msg = Message(
            'Test Email from Student Management System',
            recipients=[current_app.config['MAIL_USERNAME']],  # Sending to ourselves for testing
            body='This is a test email to verify the email configuration is working correctly.'
        )
        mail.send(msg)
        return jsonify({
            'success': True,
            'message': 'Test email sent successfully! Check your inbox.',
            'email_config': {
                'MAIL_SERVER': current_app.config['MAIL_SERVER'],
                'MAIL_PORT': current_app.config['MAIL_PORT'],
                'MAIL_USE_TLS': current_app.config['MAIL_USE_TLS'],
                'MAIL_USERNAME': current_app.config['MAIL_USERNAME'],
                'MAIL_DEFAULT_SENDER': current_app.config['MAIL_DEFAULT_SENDER']
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'email_config': {
                'MAIL_SERVER': current_app.config['MAIL_SERVER'],
                'MAIL_PORT': current_app.config['MAIL_PORT'],
                'MAIL_USE_TLS': current_app.config['MAIL_USE_TLS'],
                'MAIL_USERNAME': current_app.config['MAIL_USERNAME'],
                'MAIL_DEFAULT_SENDER': current_app.config['MAIL_DEFAULT_SENDER']
            }
        }), 500


@core.route('/test')
def test():
    """Simple test route"""
    return jsonify({'message': 'Test route working!'}) 