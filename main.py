from flask import Blueprint, jsonify, current_app, request, render_template, flash, redirect, url_for, send_file
from flask_mail import Message
from extensions import mail, db
from datetime import datetime
import json
from flask_login import login_required, current_user
from functools import wraps
import uuid
import hmac
import hashlib
from sqlalchemy import func
from models import Application, FileAttachment, Student
import phpserialize
import requests
import os
import mimetypes
from urllib.parse import urlparse, unquote
from sqlalchemy.sql import text

main = Blueprint('main', __name__)

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission):
                flash(f'You do not have permission to {permission.replace("_", " ")}.', 'error')
                return redirect(url_for('main.view_students'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Store last received webhook data
last_webhook_data = None
last_webhook_error = None

# Store students data (in a real app, this would be in a database)
students = {}
applications_list = []

@main.route('/')
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
    
    return render_template('index.html', 
                         stats=stats,
                         recent_applications=recent_applications,
                         last_webhook_data=last_webhook_data)

@main.route('/test_email')
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

@main.route('/test')
def test():
    return jsonify({'message': 'Test route working!'})

@main.route('/applications')
@login_required
@permission_required('view_applications')
def applications():
    """Display the applications page."""
    # Get filter parameters
    status_filter = request.args.get('status', '').lower()
    division_filter = request.args.get('division', '').upper()
    search_query = request.args.get('search', '').strip()
    
    # Query applications based on filters
    query = Application.query
    
    # Apply division filter
    if division_filter and division_filter in ['YZA', 'YOH']:
        query = query.filter(Application.division == division_filter)
    
    # Apply status filter
    if status_filter:
        query = query.filter(func.lower(Application.status) == status_filter)
    
    # Apply search filter
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Application.student_name.ilike(search_filter),
                Application.student_first_name.ilike(search_filter),
                Application.student_last_name.ilike(search_filter),
                Application.email.ilike(search_filter),
                Application.phone_number.ilike(search_filter),
                Application.hebrew_name.ilike(search_filter),
                Application.informal_name.ilike(search_filter),
                Application.id.ilike(search_filter)
            )
        )
    
    # Order by submission date, newest first
    applications_list = query.order_by(Application.submitted_date.desc()).all()
    
    # Get statistics for the filter badges (based on current division filter if any)
    base_query = Application.query
    if division_filter and division_filter in ['YZA', 'YOH']:
        base_query = base_query.filter(Application.division == division_filter)
    
    stats = {
        'all': base_query.count(),
        'pending': base_query.filter_by(status='Pending').count(),
        'accepted': base_query.filter_by(status='Accepted').count(),
        'rejected': base_query.filter_by(status='Rejected').count()
    }
    
    # Get division statistics for division filter badges
    division_stats = {
        'all': Application.query.count(),
        'yza': Application.query.filter_by(division='YZA').count(),
        'yoh': Application.query.filter_by(division='YOH').count()
    }
    
    return render_template('applications.html', 
                         applications=applications_list, 
                         stats=stats,
                         division_stats=division_stats,
                         search_query=search_query,
                         division_filter=division_filter)

@main.route('/students')
@login_required
@permission_required('view_students')
def view_students():
    """Display the students page."""
    try:
        # Query students from the database using the Student model
        students_from_db = Student.query.order_by(Student.accepted_date.desc()).all()
        
        # Convert database students to list format for the template
        student_list = []
        for student in students_from_db:
            student_data = {
                'id': student.id,
                'full_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
                'phone_number': student.phone_number or '',
                'hebrew_name': student.hebrew_name or '',
                'division': student.division or 'YZA',
                'status': student.status or 'Active',
                'status_color': 'success' if student.status == 'Active' else 'secondary',
                'accepted_date': student.accepted_date,
                'email': student.email or '',
                'citizenship': student.citizenship or '',
                'marital_status': student.marital_status or ''
            }
            student_list.append(student_data)
        
        return render_template('students.html', students=student_list)
        
    except Exception as e:
        current_app.logger.error(f"Error loading students page: {e}")
        # Return empty list if there's an error
        return render_template('students.html', students=[])

@main.route('/students/<student_id>')
@login_required
@permission_required('view_students')
def student_details(student_id):
    """Display student details."""
    try:
        from models import Student
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return render_template('404.html', message="Student not found"), 404
        
        # Convert the student model to the format expected by the template
        # Use getattr() with default values to handle missing attributes gracefully
        student_data = {
            'id': student.id,
            'first_name': getattr(student, 'student_first_name', '') or '',
            'middle_name': getattr(student, 'student_middle_name', '') or '',
            'last_name': getattr(student, 'student_last_name', '') or '',
            'full_name': getattr(student, 'student_name', '') or f"{getattr(student, 'student_first_name', '') or ''} {getattr(student, 'student_last_name', '') or ''}".strip(),
            'phone_number': getattr(student, 'phone_number', '') or '',
            'ssn': getattr(student, 'social_security_number', '') or '',
            'date_of_birth': getattr(student, 'date_of_birth', '') or '',
            'citizenship': getattr(student, 'citizenship', '') or '',
            'high_school_graduate': getattr(student, 'high_school_graduate', '') or '',
            'status': getattr(student, 'status', 'Active') or 'Active',
            'status_color': 'success' if getattr(student, 'status', 'Active') == 'Active' else 'secondary',
            'marital_status': getattr(student, 'marital_status', '') or '',
            'address': {
                'line1': getattr(student, 'address_line1', '') or '',
                'line2': getattr(student, 'address_line2', '') or '',
                'city': getattr(student, 'address_city', '') or '',
                'state': getattr(student, 'address_state', '') or '',
                'zip': getattr(student, 'address_zip', '') or '',
                'country': getattr(student, 'address_country', '') or ''
            },
            'alt_address': {
                'line1': getattr(student, 'alt_address_line1', '') or '',
                'line2': getattr(student, 'alt_address_line2', '') or '',
                'city': getattr(student, 'alt_address_city', '') or '',
                'state': getattr(student, 'alt_address_state', '') or '',
                'zip': getattr(student, 'alt_address_zip', '') or '',
                'country': getattr(student, 'alt_address_country', '') or ''
            },
            'hebrew_name': getattr(student, 'hebrew_name', '') or '',
            'informal_name': getattr(student, 'informal_name', '') or '',
            'email': getattr(student, 'email', '') or '',
            'financial_aid': {
                'status': getattr(student, 'tuition_payment_status', '') or '',
                'amount_can_pay': str(getattr(student, 'amount_can_pay', 0)) if getattr(student, 'amount_can_pay', None) else '0',
                'scholarship_amount': str(getattr(student, 'scholarship_amount_requested', 0)) if getattr(student, 'scholarship_amount_requested', None) else '0'
            },
            'parents': {
                'father': {
                    'title': getattr(student, 'father_title', '') or '',
                    'first_name': getattr(student, 'father_first_name', '') or '',
                    'last_name': getattr(student, 'father_last_name', '') or '',
                    'phone': getattr(student, 'father_phone', '') or '',
                    'email': getattr(student, 'father_email', '') or '',
                    'occupation': getattr(student, 'father_occupation', '') or '',
                    'address_same': False  # Default value
                },
                'mother': {
                    'title': getattr(student, 'mother_title', '') or '',
                    'first_name': getattr(student, 'mother_first_name', '') or '',
                    'last_name': getattr(student, 'mother_last_name', '') or '',
                    'phone': getattr(student, 'mother_phone', '') or '',
                    'email': getattr(student, 'mother_email', '') or '',
                    'occupation': getattr(student, 'mother_occupation', '') or '',
                    'address_same': False  # Default value
                }
            },
            'spouse': {
                'first_name': '',
                'last_name': '',
                'phone': '',
                'email': '',
                'occupation': ''
            } if getattr(student, 'marital_status', '') == 'Married' and getattr(student, 'spouse_name', '') else None,
            'grandparents': {
                'paternal': {
                    'name': f"{getattr(student, 'paternal_grandfather_first_name', '') or ''} {getattr(student, 'paternal_grandfather_last_name', '') or ''}".strip(),
                    'first_name': getattr(student, 'paternal_grandfather_first_name', '') or '',
                    'last_name': getattr(student, 'paternal_grandfather_last_name', '') or '',
                    'phone': getattr(student, 'paternal_grandfather_phone', '') or '',
                    'email': getattr(student, 'paternal_grandfather_email', '') or '',
                    'address': {
                        'line1': getattr(student, 'paternal_grandfather_address_line1', '') or '',
                        'city': getattr(student, 'paternal_grandfather_address_city', '') or '',
                        'state': getattr(student, 'paternal_grandfather_address_state', '') or '',
                        'zip': getattr(student, 'paternal_grandfather_address_zip', '') or ''
                    }
                },
                'maternal': {
                    'name': f"{getattr(student, 'maternal_grandfather_first_name', '') or ''} {getattr(student, 'maternal_grandfather_last_name', '') or ''}".strip(),
                    'first_name': getattr(student, 'maternal_grandfather_first_name', '') or '',
                    'last_name': getattr(student, 'maternal_grandfather_last_name', '') or '',
                    'phone': getattr(student, 'maternal_grandfather_phone', '') or '',
                    'email': getattr(student, 'maternal_grandfather_email', '') or '',
                    'address': {
                        'line1': getattr(student, 'maternal_grandfather_address_line1', '') or '',
                        'city': getattr(student, 'maternal_grandfather_address_city', '') or '',
                        'state': getattr(student, 'maternal_grandfather_address_state', '') or '',
                        'zip': getattr(student, 'maternal_grandfather_address_zip', '') or ''
                    }
                }
            },
            'in_laws': {
                'first_name': getattr(student, 'inlaws_first_name', '') or '',
                'last_name': getattr(student, 'inlaws_last_name', '') or '',
                'phone': getattr(student, 'inlaws_phone', '') or '',
                'email': getattr(student, 'inlaws_email', '') or '',
                'address': {
                    'line1': getattr(student, 'inlaws_address_line1', '') or '',
                    'city': getattr(student, 'inlaws_address_city', '') or '',
                    'state': getattr(student, 'inlaws_address_state', '') or '',
                    'zip': getattr(student, 'inlaws_address_zip', '') or ''
                }
            },
            'education': {
                'high_school_info': getattr(student, 'high_school_info', '') or '',
                'seminary_info': getattr(student, 'seminary_info', '') or '',
                'college_attending': getattr(student, 'college_attending', '') or '',
                'college_name': getattr(student, 'college_name', '') or '',
                'college_major': getattr(student, 'college_major', '') or '',
                'college_expected_graduation': getattr(student, 'college_expected_graduation', '') or ''
            },
            'learning': {
                'last_rebbe_name': getattr(student, 'last_rebbe_name', '') or '',
                'last_rebbe_phone': getattr(student, 'last_rebbe_phone', '') or '',
                'gemora_sedorim_daily_count': getattr(student, 'gemora_sedorim_daily_count', '') or '',
                'gemora_sedorim_length': getattr(student, 'gemora_sedorim_length', '') or '',
                'learning_evaluation': getattr(student, 'learning_evaluation', '') or ''
            },
            'medical': {
                'conditions': getattr(student, 'medical_conditions', '') or '',
                'insurance_company': getattr(student, 'insurance_company', '') or '',
                'blood_type': getattr(student, 'blood_type', '') or ''
            },
            'activities': {
                'past_jobs': getattr(student, 'past_jobs', '') or '',
                'summer_activities': getattr(student, 'summer_activities', '') or ''
            },
            'dormitory_meals_option': getattr(student, 'dormitory_meals_option', '') or '',
            'additional_info': getattr(student, 'additional_info', '') or '',
            'division': getattr(student, 'division', '') or '',
            'accepted_date': getattr(student, 'accepted_date', '') or '',
            'application_id': getattr(student, 'application_id', '') or ''
        }
        
        # Parse spouse name if married
        if getattr(student, 'marital_status', '') == 'Married' and getattr(student, 'spouse_name', ''):
            spouse_parts = getattr(student, 'spouse_name', '').split(' ', 1)
            student_data['spouse'] = {
                'first_name': spouse_parts[0] if spouse_parts else '',
                'last_name': spouse_parts[1] if len(spouse_parts) > 1 else '',
                'phone': '',
                'email': '',
                'occupation': ''
            }
        
        # Get student's file attachments
        attachments = student.attachments.all() if hasattr(student, 'attachments') else []
        
        return render_template('student_details.html', student=student_data, attachments=attachments)
        
    except Exception as e:
        current_app.logger.error(f"Error loading student {student_id}: {str(e)}")
        return render_template('404.html', message="Error loading student details"), 500

@main.route('/students/<student_id>/edit')
@login_required
@permission_required('edit_students')
def edit_student(student_id):
    """Display the student edit form."""
    try:
        from models import Student
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return render_template('404.html', message="Student not found"), 404
        
        student_data = {
            'id': student.id,
            'first_name': student.student_name.split()[0] if student.student_name else '',
            'last_name': ' '.join(student.student_name.split()[1:]) if student.student_name and len(student.student_name.split()) > 1 else '',
            'full_name': student.student_name or '',
            'phone_number': student.phone_number or '',
            'hebrew_name': '',  # Add if needed from student model
            'status': student.status or 'Active',
            'financial_aid': {}  # Add financial aid info if needed
        }
        
        return render_template('student_edit.html', student=student_data)
        
    except Exception as e:
        current_app.logger.error(f"Error loading student for edit {student_id}: {str(e)}")
        return render_template('404.html', message="Error loading student for editing"), 500

@main.route('/api/students/<student_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def update_student(student_id):
    """Update student information."""
    try:
        from models import Student
        from extensions import db
        
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.json
        
        # Update student data in the database
        if 'first_name' in data or 'last_name' in data:
            first_name = data.get('first_name', student.student_name.split()[0] if student.student_name else '')
            last_name = data.get('last_name', ' '.join(student.student_name.split()[1:]) if student.student_name and len(student.student_name.split()) > 1 else '')
            student.student_name = f"{first_name} {last_name}".strip()
        
        if 'phone_number' in data:
            student.phone_number = data.get('phone_number')
        
        # Add other fields as needed
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Student {student_id} updated successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating student {student_id}: {str(e)}")
        return jsonify({'error': 'Error updating student'}), 500

@main.route('/api/students/<student_id>', methods=['DELETE'])
@login_required
@permission_required('edit_students')
def delete_student(student_id):
    """Delete a student."""
    try:
        from models import Student
        from extensions import db
        
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        student_name = student.student_name
        db.session.delete(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Student {student_name} deleted successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error deleting student {student_id}: {str(e)}")
        return jsonify({'error': 'Error deleting student'}), 500

@main.route('/students/new', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def create_student():
    """Create a new student."""
    if request.method == 'POST':
        student_id = str(uuid.uuid4())
        data = request.form
        
        # Create new student data
        student_data = {
            'first_name': data.get('first_name'),
            'middle_name': data.get('middle_name'),
            'last_name': data.get('last_name'),
            'phone_number': data.get('phone_number'),
            'ssn': data.get('ssn'),
            'date_of_birth': data.get('date_of_birth'),
            'citizenship': data.get('citizenship'),
            'high_school_graduate': data.get('high_school_graduate'),
            'status': data.get('status', 'Active'),
            'marital_status': data.get('marital_status'),
            'address': {
                'line1': data.get('address_line1'),
                'city': data.get('city'),
                'state': data.get('state'),
                'zip': data.get('zip')
            },
            'custom_fields': {
                'hebrew_name': data.get('hebrew_name'),
                'informal_name': data.get('informal_name')
            },
            'parents': {
                'father': {
                    'title': data.get('father_title'),
                    'first_name': data.get('father_first_name'),
                    'last_name': data.get('father_last_name'),
                    'phone': data.get('father_phone'),
                    'occupation': data.get('father_occupation')
                },
                'mother': {
                    'title': data.get('mother_title'),
                    'first_name': data.get('mother_first_name'),
                    'last_name': data.get('mother_last_name'),
                    'phone': data.get('mother_phone'),
                    'occupation': data.get('mother_occupation')
                }
            },
            'grandparents': {
                'paternal': {
                    'name': data.get('paternal_grandparents_name'),
                    'phone': data.get('paternal_grandparents_phone')
                },
                'maternal': {
                    'name': data.get('maternal_grandparents_name'),
                    'phone': data.get('maternal_grandparents_phone')
                }
            }
        }
        
        # Add spouse information if married
        if data.get('marital_status') == 'married':
            student_data['spouse'] = {
                'first_name': data.get('spouse_first_name'),
                'last_name': data.get('spouse_last_name'),
                'phone': data.get('spouse_phone'),
                'occupation': data.get('spouse_occupation')
            }
        
        # Store the new student
        students[student_id] = student_data
        
        flash('Student created successfully!', 'success')
        return redirect(url_for('main.student_details', student_id=student_id))
    
    return render_template('student_create.html')

def process_form_submission(data):
    """Process form submission data and create application/student records."""
    global last_webhook_data, last_webhook_error
    
    try:
        # Store the webhook data for debugging
        last_webhook_data = data
        last_webhook_error = None
        
        current_app.logger.info("=== Processing Form Submission ===")
        current_app.logger.info(f"Raw webhook data keys: {list(data.keys())}")
        current_app.logger.info(f"Raw webhook data: {data}")
        
        # Import required modules
        from models import Application
        from extensions import db
        import uuid
        
        # Check if this is actual Gravity Forms data - either has form_id or field IDs
        has_form_id = data.get('form_id') is not None
        has_field_ids = any(k for k in data.keys() if '.' in str(k) or k.isdigit())
        
        if not (has_form_id or has_field_ids):
            current_app.logger.warning("⚠️ No Gravity Forms field IDs detected in data")
        
        # Helper function to get field values
        def get_field(field_id, default=''):
            """Get field value with fallback support for both input_X and X formats"""
            # Try with input_ prefix first (real Gravity Forms format)
            prefixed_key = f"input_{field_id}"
            if prefixed_key in data:
                value = data[prefixed_key]
                if value is None or value == '':
                    return default
                return str(value).strip()
            
            # Try without prefix (test format)
            if field_id in data:
                value = data[field_id]
                if value is None or value == '':
                    return default
                return str(value).strip()
            
            return default
        
        # Helper function to handle numeric fields
        def get_numeric_field(field_id, default=None):
            """Get a numeric field value, parsing it as a float if possible."""
            value = get_field(field_id, '')
            if value:
                try:
                    return float(value)
                except ValueError:
                    return default
            return default
        
        def get_tuition_payment_status():
            """Get tuition payment status from one of three possible field IDs based on dormitory option."""
            # Check field 83 first (if dorm is selected)
            status_83 = get_field('83', '')
            if status_83:
                current_app.logger.info(f"Found tuition status in field 83 (dorm selected): {status_83}")
                return status_83
                
            # Check field 168 (if meals but no dorm)
            status_168 = get_field('168', '')
            if status_168:
                current_app.logger.info(f"Found tuition status in field 168 (meals only): {status_168}")
                return status_168
                
            # Check field 167 (if no dorm and no meals)
            status_167 = get_field('167', '')
            if status_167:
                current_app.logger.info(f"Found tuition status in field 167 (no dorm/meals): {status_167}")
                return status_167
                
            # No tuition status found in any field
            current_app.logger.info("No tuition payment status found in fields 83, 168, or 167")
            return ''
        
        # Helper function to parse dates
        def parse_date(date_str):
            """Parse date string in various formats"""
            if not date_str or date_str.strip() == '':
                return None
            try:
                from datetime import datetime
                # Try different date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(date_str.strip(), fmt).date()
                    except ValueError:
                        continue
                return None
            except Exception:
                return None
        
        # Helper function to parse date from separate fields (real Gravity Forms format)
        def parse_date_fields(field_prefix):
            """Parse date from separate month/day/year fields like 16.1, 16.2, 16.3"""
            month = get_field(f'{field_prefix}.1', '')
            day = get_field(f'{field_prefix}.2', '')
            year = get_field(f'{field_prefix}.3', '')
            
            if month and day and year:
                try:
                    from datetime import datetime
                    # Convert to integers and create date
                    return datetime(int(year), int(month), int(day)).date()
                except (ValueError, TypeError):
                    current_app.logger.warning(f"Invalid date components: {month}/{day}/{year}")
                    return None
            return None

        # Enhanced helper function to parse school info (handles PHP serialized data)
        def parse_school_info_simple(school_text):
            """Enhanced parser for Gravity Forms list fields - handles PHP serialized data"""
            if not school_text or school_text.strip() == '':
                return None
            
            schools = []
            
            # Handle different data formats that Gravity Forms might send
            if isinstance(school_text, list):
                # If it's already a list (from test data)
                for school_entry in school_text:
                    if isinstance(school_entry, dict):
                        # Structured data - reconstruct the full information
                        name_parts = []
                        if 'Name of school' in school_entry:
                            name_parts.append(school_entry['Name of school'])
                        if 'Location' in school_entry:
                            name_parts.append(school_entry['Location'])
                        if 'Dates of Attendance' in school_entry:
                            name_parts.append(school_entry['Dates of Attendance'])
                        if 'Graduation Date' in school_entry:
                            grad_date = school_entry['Graduation Date']
                            name_parts.append(grad_date if grad_date else 'None')
                        
                        schools.append(' | '.join(name_parts))
                    else:
                        # Simple string entry
                        schools.append(str(school_entry))
                
                return schools if schools else None
            
            elif isinstance(school_text, str) and school_text.startswith(('a:', 's:')):
                # PHP serialized data - parse it
                try:
                    parsed_data = phpserialize.loads(school_text.encode('utf-8'))
                    
                    if isinstance(parsed_data, dict):
                        # Handle complex school objects (like high school/seminary data)
                        if any(key in str(parsed_data) for key in ['Name of school', 'Location', 'Dates of Attendance']):
                            # This is school data with structured fields
                            for key, school_entry in parsed_data.items():
                                if isinstance(school_entry, dict):
                                    name_parts = []
                                    for field_key, field_value in school_entry.items():
                                        if isinstance(field_value, bytes):
                                            field_value = field_value.decode('utf-8')
                                        name_parts.append(str(field_value))
                                    schools.append(' | '.join(name_parts))
                                else:
                                    # Simple entry
                                    if isinstance(school_entry, bytes):
                                        school_entry = school_entry.decode('utf-8')
                                    schools.append(str(school_entry))
                        else:
                            # This is simple list data (like summer activities)
                            for key, value in parsed_data.items():
                                if isinstance(value, bytes):
                                    value = value.decode('utf-8')
                                schools.append(str(value))
                    
                    return schools if schools else None
                    
                except Exception as e:
                    current_app.logger.error(f"Failed to parse PHP serialized data: {e}")
                    return [school_text]  # Return original as fallback
            
            else:
                # Plain text or other format
                return [school_text] if school_text else None

        # Map the form data to our application model
        mapped_data = {
            # Required fields
            'id': str(uuid.uuid4()),
            
            # CORRECTED FIELD MAPPINGS BASED ON ACTUAL GRAVITY FORMS JSON
            
            # Basic applicant information - CORRECTED
            'student_first_name': get_field('95.3', ''),    # Name (First) - Field 95.3
            'student_middle_name': get_field('95.4', ''),   # Name (Middle) - Field 95.4
            'student_last_name': get_field('95.6', ''),     # Name (Last) - Field 95.6
            'student_name': f"{get_field('95.3', '')} {get_field('95.6', '')}".strip(),
            'informal_name': get_field('97', ''),           # Informal Name - Field 97
            'hebrew_name': get_field('96', ''),             # Hebrew Name - Field 96
            'date_of_birth': parse_date_fields('16') or parse_date(get_field('16', '')), # Date of Birth - Field 16
            'email': get_field('161', ''),                  # Student's Email - Field 161 (CORRECTED!)
            'phone_number': get_field('98', ''),            # Phone - Field 98
            'social_security_number': get_field('104', ''), # Social Security # - Field 104
            
            # Address information - CORRECTED 
            'address_line1': get_field('99.1', ''),         # Student Address (Street) - Field 99.1
            'address_line2': get_field('99.2', ''),         # Student Address (Line 2) - Field 99.2
            'address_city': get_field('99.3', ''),          # Student Address (City) - Field 99.3
            'address_state': get_field('99.4', ''),         # Student Address (State) - Field 99.4
            'address_zip': get_field('99.5', ''),           # Student Address (ZIP) - Field 99.5
            'address_country': get_field('99.6', ''),       # Student Address (Country) - Field 99.6
            
            # Mailing address - CORRECTED
            'alt_address_line1': get_field('100.1', ''),    # Mailing Address (Street) - Field 100.1
            'alt_address_line2': get_field('100.2', ''),    # Mailing Address (Line 2) - Field 100.2
            'alt_address_city': get_field('100.3', ''),     # Mailing Address (City) - Field 100.3
            'alt_address_state': get_field('100.4', ''),    # Mailing Address (State) - Field 100.4
            'alt_address_zip': get_field('100.5', ''),      # Mailing Address (ZIP) - Field 100.5
            'alt_address_country': get_field('100.6', ''),  # Mailing Address (Country) - Field 100.6
            
            # Citizenship and status - CORRECTED
            'citizenship': get_field('102', ''),            # I am a: (US Citizen/etc) - Field 102 
            'high_school_graduate': get_field('106', ''),   # High School Graduate? - Field 106
            
            # Father information - CORRECTED to field 111
            'father_title': get_field('111.2', ''),         # Father's Name (Prefix) - Field 111.2
            'father_first_name': get_field('111.3', ''),    # Father's Name (First) - Field 111.3
            'father_last_name': get_field('111.6', ''),     # Father's Name (Last) - Field 111.6
            'father_occupation': get_field('113', ''),      # Father's Occupation - Field 113
            'father_phone': get_field('115', ''),           # Father's Cell - Field 115
            'father_email': get_field('117', ''),           # Father's Email - Field 117
            
            # Mother information - CORRECTED to field 112
            'mother_title': get_field('112.2', ''),         # Mother's Name (Prefix) - Field 112.2
            'mother_first_name': get_field('112.3', ''),    # Mother's Name (First) - Field 112.3
            'mother_last_name': get_field('112.6', ''),     # Mother's Name (Last) - Field 112.6
            'mother_occupation': get_field('114', ''),      # Mother's Occupation - Field 114
            'mother_phone': get_field('116', ''),           # Mother's Cell - Field 116
            'mother_email': get_field('118', ''),           # Mother's Email - Field 118
            
            # Marital Status and Spouse - CORRECTED
            'marital_status': get_field('119', ''),         # Student's Marital Status - Field 119
            'spouse_name': get_field('120', ''),            # Wife's Name - Field 120
            
            # In-laws information - UNIFIED FIELDS (CORRECTED)
            'inlaws_first_name': get_field('122.3', ''),    # In-laws' Name (First) - Field 122.3
            'inlaws_last_name': get_field('122.6', ''),     # In-laws' Name (Last) - Field 122.6
            'inlaws_phone': get_field('123', ''),           # In-laws' Telephone - Field 123
            'inlaws_email': get_field('159', ''),           # In-laws' Email - Field 159
            'inlaws_address_line1': get_field('160.1', ''), # In-laws' Address (Street) - Field 160.1
            'inlaws_address_city': get_field('160.3', ''),  # In-laws' Address (City) - Field 160.3
            'inlaws_address_state': get_field('160.4', ''), # In-laws' Address (State) - Field 160.4
            'inlaws_address_zip': get_field('160.5', ''),   # In-laws' Address (ZIP) - Field 160.5
            
            # Paternal Grandparents - CORRECTED field numbers
            'paternal_grandfather_first_name': get_field('157.3', ''), # Paternal Grandparents Name (First) - Field 157.3
            'paternal_grandfather_last_name': get_field('157.6', ''),  # Paternal Grandparents Name (Last) - Field 157.6
            'paternal_grandfather_phone': get_field('158', ''),        # Paternal Grandparents Telephone - Field 158
            'paternal_grandfather_email': get_field('124', ''),        # Paternal Grandparents Email - Field 124 (CORRECTED!)
            'paternal_grandfather_address_line1': get_field('125.1', ''), # Paternal Grandparents Address (Street) - Field 125.1
            'paternal_grandfather_address_city': get_field('125.3', ''),  # Paternal Grandparents Address (City) - Field 125.3
            'paternal_grandfather_address_state': get_field('125.4', ''), # Paternal Grandparents Address (State) - Field 125.4
            'paternal_grandfather_address_zip': get_field('125.5', ''),   # Paternal Grandparents Address (ZIP) - Field 125.5
            
            # Maternal Grandparents - CORRECTED field numbers
            'maternal_grandfather_first_name': get_field('126.3', ''), # Maternal Grandparents Name (First) - Field 126.3
            'maternal_grandfather_last_name': get_field('126.6', ''),  # Maternal Grandparents Name (Last) - Field 126.6
            'maternal_grandfather_phone': get_field('127', ''),        # Maternal Grandparents Telephone - Field 127
            'maternal_grandfather_email': get_field('128', ''),        # Maternal Grandparents Email - Field 128 (CORRECTED!)
            'maternal_grandfather_address_line1': get_field('129.1', ''), # Maternal Grandparents Address (Street) - Field 129.1
            'maternal_grandfather_address_city': get_field('129.3', ''),  # Maternal Grandparents Address (City) - Field 129.3
            'maternal_grandfather_address_state': get_field('129.4', ''), # Maternal Grandparents Address (State) - Field 129.4
            'maternal_grandfather_address_zip': get_field('129.5', ''),   # Maternal Grandparents Address (ZIP) - Field 129.5
            
            # Medical information - CORRECTED field numbers
            'medical_conditions': get_field('133', ''),     # Medical conditions - Field 133
            'insurance_company': get_field('134', ''),      # Medical Insurance company - Field 134
            'blood_type': get_field('135', ''),             # Blood type - Field 135
            
            # Learning information - CORRECTED field numbers
            'last_rebbe_name': get_field('136', ''),        # Name of your last Rebbe - Field 136
            'last_rebbe_phone': get_field('137', ''),       # Last Rebbe Phone - Field 137
            'gemora_sedorim_daily_count': get_field('138', ''), # How many daily Gemora Sedorim - Field 138
            'gemora_sedorim_length': get_field('139', ''),  # How long was each one? - Field 139
            'learning_evaluation': get_field('140', ''),    # Evaluate your past year's learning - Field 140
            
            # College information - CORRECTED field numbers
            'college_attending': get_field('141', ''),      # Will you be attending college? - Field 141
            'college_name': get_field('79', ''),            # Which one? - Field 79
            'college_major': get_field('142', ''),          # What is your major? - Field 142
            'college_expected_graduation': get_field('143', ''), # Expected date of graduation - Field 143
            
            # Work and activities - CORRECTED field numbers
            'past_jobs': get_field('144', ''),              # Past jobs in last two years - Field 144
            'summer_activities': ' | '.join(parse_school_info_simple(get_field('146', '')) or []),      # How applicant spent last three summers - Field 146
            
            # Financial information - CORRECTED field numbers
            'tuition_payment_status': get_tuition_payment_status(),  # Full tuition or scholarship request - Field 83
            'scholarship_amount_requested': get_numeric_field('85', None), # Scholarship amount - Field 85
            'amount_can_pay': get_numeric_field('84', None), # Amount they can pay - Field 84
            
            # Dormitory and Meals Option - NEW FIELD
            'dormitory_meals_option': get_field('164', ''),  # Dormitory and Meals selection - Field 164
            
            # Education information - HIGH SCHOOL AND SEMINARY FIELDS
            'high_school_info': parse_school_info_simple(get_field('107', '')),  # High Schools/Mesiftos - Field 107
            'seminary_info': parse_school_info_simple(get_field('109', '')),     # Post-secondary institutions - Field 109
            
            # Additional information - CORRECTED field numbers  
            'additional_info': f"Application factors: {get_field('147', '')} | Referral source: {get_field('148', '')}",
            
            # Store additional fields in custom_fields
            'custom_fields': json.dumps({
                'citizenship_other': get_field('154', ''),   # Other citizenship details - Field 154
                'post_secondary_attended': get_field('108', ''), # Post-secondary attended? - Field 108
                'mailing_address_same': get_field('101', ''), # Is mailing address same as home? - Field 101
                'file_uploads': {
                    'high_school_graduation_proof': get_field('151', ''), # Proof of High School Graduation - Field 151
                    'insurance_card': get_field('152', ''),               # Insurance Card - Field 152
                    'immunization_proof': get_field('153', ''),           # Proof of Immunization - Field 153
                },
                'raw_data': data
            }),
            
            # Metadata
            'submitted_date': datetime.now(),
            'status': 'pending',
            'division': 'YZA'  # All applications from this webhook are YZA
        }
        
        current_app.logger.info(f"Mapped {len([k for k, v in mapped_data.items() if v and k != 'custom_fields'])} fields with data")
        
        # DEBUG: Log all financial fields to see which ones have data
        current_app.logger.info("💰 FINANCIAL FIELD DEBUG:")
        current_app.logger.info(f"   Field 83 (dorm selected): '{get_field('83', '')}'")
        current_app.logger.info(f"   Field 167 (no dorm/meals): '{get_field('167', '')}'")
        current_app.logger.info(f"   Field 168 (meals only): '{get_field('168', '')}'")
        current_app.logger.info(f"   Field 84 (amount can pay): '{get_field('84', '')}'")
        current_app.logger.info(f"   Field 85 (scholarship amount): '{get_field('85', '')}'")
        current_app.logger.info(f"   Selected tuition status: '{mapped_data['tuition_payment_status']}'")
        
        # DEBUG: Log the specific school fields
        current_app.logger.info(f"High School Info (field 107): '{get_field('107', '')}'")
        current_app.logger.info(f"Seminary Info (field 109): '{get_field('109', '')}'")
        current_app.logger.info(f"Summer Activities (field 146): '{get_field('146', '')}'")
        current_app.logger.info(f"Parsed High School: {mapped_data['high_school_info']}")
        current_app.logger.info(f"Parsed Seminary: {mapped_data['seminary_info']}")
        current_app.logger.info(f"Parsed Summer Activities: {mapped_data['summer_activities']}")
        
        # Create the application record
        application = Application(**mapped_data)
        
        # Set default status and division
        application.status = 'pending'
        application.division = 'YZA'  # All applications from this webhook are YZA
        
        # Save to database
        db.session.add(application)
        db.session.commit()
        
        current_app.logger.info(f"Created application: {application.id}")
        
        # Process file attachments after the application is saved
        try:
            # Pass the original data (which contains fields 151, 152, 153) to file processing
            attachments = process_file_uploads(application.id, data)
            if attachments:
                current_app.logger.info(f"Processed {len(attachments)} file attachments for application {application.id}")
        except Exception as e:
            current_app.logger.error(f"Error processing file attachments: {str(e)}")
            # Don't fail the entire submission if file processing fails
        
        return {
            'status': 'success',
            'message': 'Application submitted successfully',
            'application_id': application.id
        }
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"❌ CRITICAL ERROR in process_form_submission")
        current_app.logger.error(f"Error type: {type(e).__name__}")
        current_app.logger.error(f"Error message: {str(e)}")
        current_app.logger.error(f"Full traceback:")
        current_app.logger.error(traceback.format_exc())
        current_app.logger.info(f"=== PROCESS FORM SUBMISSION END - FAILURE ===")
        
        # Store the error for debugging
        last_webhook_error = str(e)
        
        # Try to save a minimal error record to the database
        try:
            from models import Application
            from extensions import db
            import uuid
            application = Application(
                id=str(uuid.uuid4()),
                student_name="Form Submission - Mapping Error",
                custom_fields={
                    'raw_data': data,
                    'mapping_error': str(e)
                }
            )
            db.session.add(application)
            db.session.commit()
            current_app.logger.info(f"Created error record: {application.id}")
        except Exception as save_error:
            current_app.logger.error(f"Failed to save error record: {save_error}")
        
        return {'status': 'error', 'message': str(e)}

@main.route('/api/gravity-forms/webhook', methods=['POST'])
def gravity_forms_webhook():
    """Handle webhook requests from Gravity Forms."""
    # Debug logging for request details
    current_app.logger.info("=== Webhook Request Details ===")
    current_app.logger.info(f"Method: {request.method}")
    current_app.logger.info(f"Content-Type: {request.content_type}")
    current_app.logger.info(f"Headers: {dict(request.headers)}")
    current_app.logger.info(f"Raw Data: {request.get_data().decode('utf-8')}")
    current_app.logger.info(f"Form Data: {request.form.to_dict()}")
    current_app.logger.info("============================")

    # Get request data
    try:
        # Try to get JSON data first
        data = request.get_json(silent=True)
        if data is None:
            # If not JSON, try form data
            data = request.form.to_dict()
        if not data:
            error_msg = "Empty request body"
            current_app.logger.error(error_msg)
            return jsonify({'status': 'error', 'message': error_msg}), 400
    except Exception as e:
        error_msg = f"Invalid request data: {str(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 400

    # Process the form submission without signature validation
    # (Signature validation disabled - Gravity Forms version does not support it)
    current_app.logger.info("Processing webhook data without signature validation")
    current_app.logger.info(f"Processing data: {data}")
    
    try:
        result = process_form_submission(data)
        if result['status'] == 'success':
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        error_msg = f"Error processing form submission: {str(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@main.route('/webhook-debug')
@login_required
@permission_required('view_applications')
def webhook_debug():
    """View the last webhook data and any mapping errors."""
    return render_template(
        'webhook_debug.html',
        webhook_data=last_webhook_data,
        webhook_error=last_webhook_error
    )

@main.route('/api/gravity-forms/webhook-debug', methods=['POST'])
def gravity_forms_webhook_debug():
    """Debug webhook endpoint that bypasses signature validation."""
    current_app.logger.info("=== DEBUG Webhook Request Details ===")
    current_app.logger.info(f"Method: {request.method}")
    current_app.logger.info(f"Content-Type: {request.content_type}")
    current_app.logger.info(f"Headers: {dict(request.headers)}")
    current_app.logger.info(f"Raw Data: {request.get_data().decode('utf-8')}")
    current_app.logger.info(f"Form Data: {request.form.to_dict()}")
    current_app.logger.info(f"JSON Data: {request.get_json(silent=True)}")
    current_app.logger.info("============================")

    # Try to get data in different formats
    try:
        # Get request data
        data = request.get_json(silent=True)
        if data is None:
            data = request.form.to_dict()
        
        if data:
            current_app.logger.info(f"Successfully parsed data: {data}")
            # Try to process the form submission without signature validation
            process_form_submission(data)
            return jsonify({'status': 'success', 'message': 'Debug webhook processed successfully'}), 200
        else:
            current_app.logger.error("No data found in request")
            return jsonify({'status': 'error', 'message': 'No data found'}), 400
            
    except Exception as e:
        error_msg = f"Error processing debug webhook: {str(e)}"
        current_app.logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@main.route('/api/applications/<application_id>/status', methods=['POST'])
@login_required
@permission_required('process_applications')
def update_application_status(application_id):
    """Update application status and create student record if accepted"""
    # Enhanced logging for debugging
    current_app.logger.info(f"=== ACCEPT FUNCTION DEBUG START ===")
    current_app.logger.info(f"Processing status update for application ID: {application_id}")
    current_app.logger.info(f"User: {current_user.username}")
    current_app.logger.info(f"Request method: {request.method}")
    current_app.logger.info(f"Request content type: {request.content_type}")
    
    try:
        # Step 1: Parse request data
        current_app.logger.info("Step 1: Parsing request data...")
        data = request.get_json()
        current_app.logger.info(f"Request data: {data}")
        
        status = data.get('status')
        current_app.logger.info(f"Requested status: {status}")
        
        if status not in ['accepted', 'rejected', 'pending']:
            current_app.logger.error(f"Invalid status provided: {status}")
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        # Step 2: Find application
        current_app.logger.info("Step 2: Looking up application...")
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            current_app.logger.error(f"Application not found: {application_id}")
            return jsonify({'success': False, 'message': 'Application not found'}), 404
        
        current_app.logger.info(f"Found application: {application.id} - {application.student_name}")
        old_status = application.status
        current_app.logger.info(f"Current status: {old_status} -> New status: {status}")
        
        # Step 3: Update application status
        current_app.logger.info("Step 3: Updating application status...")
        application.status = status.capitalize()
        current_app.logger.info(f"Application status set to: {application.status}")
        
        # Step 4: Handle acceptance logic
        if status.lower() == 'accepted' and old_status.lower() != 'accepted':
            current_app.logger.info("Step 4: Processing acceptance - creating student record...")
            
            try:
                # Step 4a: Import Student model
                current_app.logger.info("Step 4a: Importing Student model...")
                from models import Student
                current_app.logger.info("✅ Student model imported successfully")
                
                # Step 4b: Check for existing student
                current_app.logger.info("Step 4b: Checking for existing student...")
                existing_student = Student.query.filter_by(application_id=application_id).first()
                if existing_student:
                    current_app.logger.warning(f"Student already exists for application {application_id}: {existing_student.id}")
                else:
                    current_app.logger.info("No existing student found - proceeding with creation")
                    
                    # Step 4c: Create student record
                    current_app.logger.info("Step 4c: Creating student from application...")
                    current_app.logger.info(f"Calling Student.create_from_application with application: {application.id}")
                    
                    # Check if method exists
                    if hasattr(Student, 'create_from_application'):
                        current_app.logger.info("✅ Student.create_from_application method exists")
                        
                        # Test database connection before creating student
                        current_app.logger.info("Testing database connection...")
                        try:
                            # Try a simple query first
                            test_query = db.session.execute(text("SELECT 1")).fetchone()
                            current_app.logger.info("✅ Database connection test successful")
                        except Exception as db_test_error:
                            current_app.logger.error(f"❌ Database connection test failed: {db_test_error}")
                            raise db_test_error
                        
                        # Now try to create the student
                        student = Student.create_from_application(application)
                        
                        if student:
                            current_app.logger.info(f"✅ Student created successfully: {student.id}")
                            db.session.add(student)
                            current_app.logger.info("Student added to session")
                            
                            # Copy file attachments from application to student
                            try:
                                current_app.logger.info("Copying file attachments from application to student...")
                                db.session.flush()  # Ensure student is persisted before copying attachments
                                student.copy_attachments_from_application()
                                current_app.logger.info("✅ File attachments copied successfully")
                            except Exception as attachment_error:
                                current_app.logger.error(f"⚠️ Error copying attachments: {attachment_error}")
                                # Don't fail the entire operation if attachment copying fails
                        else:
                            current_app.logger.error("❌ Student.create_from_application returned None")
                            
                    else:
                        current_app.logger.error("❌ Student.create_from_application method not found!")
                        current_app.logger.error(f"Available Student methods: {[method for method in dir(Student) if not method.startswith('_')]}")
                    
            except Exception as student_creation_error:
                current_app.logger.error(f"❌ Error creating student record for application {application_id}")
                current_app.logger.error(f"Error type: {type(student_creation_error).__name__}")
                current_app.logger.error(f"Error message: {str(student_creation_error)}")
                current_app.logger.error(f"Full traceback:")
                import traceback
                current_app.logger.error(traceback.format_exc())
                
                # Analyze the error
                error_str = str(student_creation_error).lower()
                if "no such table" in error_str:
                    current_app.logger.error("🔍 DIAGNOSIS: Missing database table")
                    if "file_attachments" in error_str:
                        current_app.logger.error("🔍 SPECIFIC ISSUE: file_attachments table missing")
                elif "no such column" in error_str:
                    current_app.logger.error("🔍 DIAGNOSIS: Missing database column")
                    if "dormitory_meals_option" in error_str:
                        current_app.logger.error("🔍 SPECIFIC ISSUE: dormitory_meals_option column missing")
                elif "integrity" in error_str:
                    current_app.logger.error("🔍 DIAGNOSIS: Database integrity constraint violation")
                
                # Don't fail the entire operation if student creation fails
                current_app.logger.info("Continuing with status update despite student creation failure")
        
        # Step 5: Commit changes
        current_app.logger.info("Step 5: Committing database changes...")
        try:
            db.session.commit()
            current_app.logger.info("✅ Database commit successful")
        except Exception as commit_error:
            import traceback
            current_app.logger.error(f"❌ Database commit failed: {commit_error}")
            current_app.logger.error(traceback.format_exc())
            db.session.rollback()
            current_app.logger.info("Database rolled back")
            raise commit_error
        
        current_app.logger.info(f"✅ Application {application_id} status updated to {status} by user {current_user.username}")
        
        response_message = f'Application status updated to {status}'
        if status.lower() == 'accepted':
            response_message += ' and student record created'
        
        current_app.logger.info(f"=== ACCEPT FUNCTION DEBUG END - SUCCESS ===")
        return jsonify({'success': True, 'message': response_message})
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"❌ CRITICAL ERROR in update_application_status")
        current_app.logger.error(f"Error type: {type(e).__name__}")
        current_app.logger.error(f"Error message: {str(e)}")
        current_app.logger.error(f"Full traceback:")
        current_app.logger.error(traceback.format_exc())
        current_app.logger.info(f"=== ACCEPT FUNCTION DEBUG END - FAILURE ===")
        return jsonify({'success': False, 'message': 'Error updating application status'}), 500

@main.route('/download/<path:filename>')
def download_file(filename):
    """Download a file from the server."""
    # Construct the full path to the file
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    
    # Check if the file exists
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    # Get the file's MIME type
    mime_type, _ = mimetypes.guess_type(file_path)
    
    # Return the file as a response
    return send_file(file_path, mimetype=mime_type)

@main.route('/attachments/<path:filename>')
@login_required
@permission_required('view_applications')
def serve_attachment(filename):
    """Serve a file attachment from the attachments directory for download."""
    try:
        file_path = os.path.join('attachments', filename)
        
        # Security check: ensure the file path is within the attachments directory
        abs_file_path = os.path.abspath(file_path)
        abs_attachments_dir = os.path.abspath('attachments')
        
        if not abs_file_path.startswith(abs_attachments_dir):
            current_app.logger.warning(f"Attempted path traversal attack: {filename}")
            return jsonify({'error': 'Invalid file path'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Get the file's MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return send_file(file_path, mimetype=mime_type, as_attachment=True)
        
    except Exception as e:
        current_app.logger.error(f"Error serving attachment {filename}: {str(e)}")
        return jsonify({'error': 'Error serving file'}), 500

@main.route('/attachments/<path:filename>/view')
@login_required
@permission_required('view_applications')
def view_attachment(filename):
    """View a file attachment inline in the browser."""
    try:
        file_path = os.path.join('attachments', filename)
        
        # Security check: ensure the file path is within the attachments directory
        abs_file_path = os.path.abspath(file_path)
        abs_attachments_dir = os.path.abspath('attachments')
        
        if not abs_file_path.startswith(abs_attachments_dir):
            current_app.logger.warning(f"Attempted path traversal attack: {filename}")
            return jsonify({'error': 'Invalid file path'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Get the file's MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        
        # For images and PDFs, view inline. For other files, download
        if mime_type and (mime_type.startswith('image/') or mime_type == 'application/pdf'):
            return send_file(file_path, mimetype=mime_type, as_attachment=False)
        else:
            # For non-viewable files, still download
            return send_file(file_path, mimetype=mime_type, as_attachment=True)
        
    except Exception as e:
        current_app.logger.error(f"Error viewing attachment {filename}: {str(e)}")
        return jsonify({'error': 'Error viewing file'}), 500

def download_file_from_url(url, local_filename):
    """Download a file from URL and save it locally."""
    try:
        current_app.logger.info(f"Downloading file from: {url}")
        
        # Create headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # Get file size from headers
        file_size = int(response.headers.get('content-length', 0))
        
        # Create the local file path
        local_path = os.path.join('attachments', local_filename)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # Download the file
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Get actual file size
        actual_size = os.path.getsize(local_path)
        
        current_app.logger.info(f"File downloaded successfully: {local_filename} ({actual_size} bytes)")
        
        return {
            'success': True,
            'file_size': actual_size,
            'mime_type': response.headers.get('content-type', 'application/octet-stream')
        }
        
    except requests.RequestException as e:
        current_app.logger.error(f"Error downloading file from {url}: {str(e)}")
        return {'success': False, 'error': str(e)}
    except Exception as e:
        current_app.logger.error(f"Unexpected error downloading file: {str(e)}")
        return {'success': False, 'error': str(e)}

def process_file_uploads(application_id, file_data):
    """Process file uploads from Gravity Forms webhook data."""
    current_app.logger.info(f"Processing file uploads for application {application_id}")
    
    # Field mappings for file uploads
    file_fields = {
        '151': 'High School Graduation Proof',
        '152': 'Insurance Card',
        '153': 'Proof of Immunization'
    }
    
    attachments_created = []
    
    for field_id, field_name in file_fields.items():
        if field_id in file_data and file_data[field_id]:
            file_value = file_data[field_id]
            
            # Skip empty arrays
            if file_value in ['[]', '', None]:
                current_app.logger.info(f"Field {field_id} is empty, skipping")
                continue
            
            current_app.logger.info(f"Processing field {field_id}: {file_value}")
            
            try:
                # Parse the JSON array of files
                if isinstance(file_value, str):
                    # Handle escaped JSON strings from Gravity Forms
                    file_value = file_value.replace('\\\/', '/')
                    files_list = json.loads(file_value)
                else:
                    files_list = file_value
                
                if not isinstance(files_list, list):
                    files_list = [files_list]
                
                current_app.logger.info(f"Parsed files list for field {field_id}: {files_list}")
                
                for idx, file_url in enumerate(files_list):
                    if not file_url or file_url.strip() == '':
                        continue
                    
                    # If it's a simple URL string, use it directly
                    if isinstance(file_url, str):
                        url = file_url
                        # Extract filename from URL
                        parsed_url = urlparse(url)
                        original_filename = os.path.basename(unquote(parsed_url.path))
                    elif isinstance(file_url, dict) and 'url' in file_url:
                        url = file_url['url']
                        original_filename = file_url.get('title', '')
                    else:
                        current_app.logger.warning(f"Unknown file format in field {field_id}: {file_url}")
                        continue
                    
                    if not original_filename:
                        original_filename = f"attachment_{field_id}_{idx}"
                    
                    # Create a unique local filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    name, ext = os.path.splitext(original_filename)
                    local_filename = f"{application_id}_{field_id}_{timestamp}_{idx}_{name}{ext}"
                    
                    current_app.logger.info(f"Creating attachment record: {original_filename} -> {local_filename}")
                    
                    # Create the attachment record
                    attachment = FileAttachment(
                        application_id=application_id,
                        field_id=field_id,
                        field_name=field_name,
                        original_url=url,
                        original_filename=original_filename,
                        local_filename=local_filename,
                        download_status='pending'
                    )
                    
                    db.session.add(attachment)
                    db.session.flush()  # Get the ID
                    
                    # Download the file
                    download_result = download_file_from_url(url, local_filename)
                    
                    if download_result['success']:
                        attachment.download_status = 'downloaded'
                        attachment.downloaded_at = datetime.now()
                        attachment.file_size = download_result['file_size']
                        attachment.mime_type = download_result['mime_type']
                        current_app.logger.info(f"Successfully downloaded {original_filename}")
                    else:
                        attachment.download_status = 'failed'
                        current_app.logger.error(f"Failed to download {original_filename}: {download_result['error']}")
                    
                    attachments_created.append(attachment)
                        
            except json.JSONDecodeError as e:
                current_app.logger.error(f"Error parsing file data for field {field_id}: {str(e)}")
            except Exception as e:
                current_app.logger.error(f"Error processing file upload for field {field_id}: {str(e)}")
    
    # Commit all changes
    try:
        db.session.commit()
        current_app.logger.info(f"Created {len(attachments_created)} attachment records")
    except Exception as e:
        current_app.logger.error(f"Error saving attachment records: {str(e)}")
        db.session.rollback()
    
    return attachments_created 

@main.route('/api/students/<student_id>/unaccept', methods=['POST'])
@login_required
@permission_required('process_applications')
def unaccept_student(student_id):
    """Unaccept a student by reversing the acceptance process"""
    current_app.logger.info(f"=== UNACCEPT FUNCTION DEBUG START ===")
    current_app.logger.info(f"Processing unaccept for student ID: {student_id}")
    current_app.logger.info(f"User: {current_user.username}")
    
    try:
        # Step 1: Find the student
        from models import Student, Application
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            current_app.logger.error(f"Student not found: {student_id}")
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        
        current_app.logger.info(f"Found student: {student.student_name}")
        
        # Step 2: Find the associated application
        application = None
        if student.application_id:
            application = Application.query.filter_by(id=student.application_id).first()
            if application:
                current_app.logger.info(f"Found associated application: {application.id}")
            else:
                current_app.logger.warning(f"Application not found for student: {student.application_id}")
        else:
            current_app.logger.warning("Student has no associated application_id")
        
        # Step 3: Change application status back to pending (if application exists)
        if application:
            old_status = application.status
            application.status = 'Pending'
            current_app.logger.info(f"Application status changed: {old_status} -> Pending")
        
        # Step 4: Delete the student record
        current_app.logger.info(f"Deleting student record: {student.id}")
        db.session.delete(student)
        
        # Step 5: Commit changes
        db.session.commit()
        current_app.logger.info("✅ Database commit successful")
        
        current_app.logger.info(f"✅ Student {student_id} unaccepted by user {current_user.username}")
        current_app.logger.info(f"=== UNACCEPT FUNCTION DEBUG END - SUCCESS ===")
        
        return jsonify({
            'success': True, 
            'message': 'Student unaccepted successfully',
            'application_id': application.id if application else None
        })
        
    except Exception as e:
        import traceback
        current_app.logger.error(f"❌ CRITICAL ERROR in unaccept_student")
        current_app.logger.error(f"Error type: {type(e).__name__}")
        current_app.logger.error(f"Error message: {str(e)}")
        current_app.logger.error(f"Full traceback:")
        current_app.logger.error(traceback.format_exc())
        current_app.logger.info(f"=== UNACCEPT FUNCTION DEBUG END - FAILURE ===")
        
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error unaccepting student'}), 500 