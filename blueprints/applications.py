from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import Application, Student, DivisionConfig, FileAttachment
from extensions import db
from utils.decorators import permission_required
from utils.helpers import parse_date, parse_decimal
from email_service import EmailService
from datetime import datetime
import uuid
import os

applications = Blueprint('applications', __name__)

@applications.route('/applications')
@login_required
@permission_required('view_applications')
def applications_list():
    """Display the applications page."""
    # Get filter parameters
    status_filter = request.args.get('status', '').lower()
    division_filter = request.args.get('division', '').upper()
    search_query = request.args.get('search', '').strip()
    
    # Query applications based on filters
    query = Application.query
    
    # Apply division filter
    if division_filter and division_filter in ['YZA', 'YOH', 'KOLLEL']:
        query = query.filter(Application.division == division_filter)
    
    # Apply status filter
    if status_filter:
        query = query.filter(db.func.lower(Application.status) == status_filter)
    
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
    if division_filter and division_filter in ['YZA', 'YOH', 'KOLLEL']:
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
        'yoh': Application.query.filter_by(division='YOH').count(),
        'kollel': Application.query.filter_by(division='KOLLEL').count()
    }
    
    return render_template('applications.html', 
                         applications=applications_list, 
                         stats=stats,
                         division_stats=division_stats,
                         search_query=search_query,
                         division_filter=division_filter)

@applications.route('/api/applications/<application_id>/status', methods=['POST'])
@login_required
@permission_required('process_applications')
def update_application_status(application_id):
    """Update application status and handle acceptance/rejection."""
    try:
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['Accepted', 'Rejected', 'Pending']:
            return jsonify({'error': 'Invalid status'}), 400
        
        # If accepting, check if student already exists
        if new_status == 'Accepted':
            existing_student = Student.query.filter_by(application_id=application_id).first()
            if existing_student:
                return jsonify({'error': 'Student already exists for this application'}), 400
        
        # Update the status
        old_status = application.status
        application.status = new_status
        
        # If accepting, create the student record
        if new_status == 'Accepted':
            student = Student()
            
            # Copy all application fields to student
            field_mappings = {
                'student_name': 'student_name',
                'student_first_name': 'student_first_name',
                'student_middle_name': 'student_middle_name',
                'student_last_name': 'student_last_name',
                'phone_number': 'phone_number',
                'email': 'email',
                'division': 'division',
                'hebrew_name': 'hebrew_name',
                'informal_name': 'informal_name',
                'social_security_number': 'social_security_number',
                'date_of_birth': 'date_of_birth',
                'citizenship': 'citizenship',
                'high_school_graduate': 'high_school_graduate',
                'marital_status': 'marital_status',
                'spouse_name': 'spouse_name',
                # Address fields
                'address_line1': 'address_line1',
                'address_line2': 'address_line2',
                'address_city': 'address_city',
                'address_state': 'address_state',
                'address_zip': 'address_zip',
                'address_country': 'address_country',
                # Alternate address
                'alt_address_line1': 'alt_address_line1',
                'alt_address_line2': 'alt_address_line2',
                'alt_address_city': 'alt_address_city',
                'alt_address_state': 'alt_address_state',
                'alt_address_zip': 'alt_address_zip',
                'alt_address_country': 'alt_address_country',
                # Parent info
                'father_title': 'father_title',
                'father_first_name': 'father_first_name',
                'father_last_name': 'father_last_name',
                'father_phone': 'father_phone',
                'father_email': 'father_email',
                'father_occupation': 'father_occupation',
                'mother_title': 'mother_title',
                'mother_first_name': 'mother_first_name',
                'mother_last_name': 'mother_last_name',
                'mother_phone': 'mother_phone',
                'mother_email': 'mother_email',
                'mother_occupation': 'mother_occupation',
                # Financial aid
                'tuition_payment_status': 'tuition_payment_status',
                'amount_can_pay': 'amount_can_pay',
                'scholarship_amount_requested': 'scholarship_amount_requested',
                # Additional fields
                'dormitory_meals_option': 'dormitory_meals_option',
                'high_school_info': 'high_school_info',
                'seminary_info': 'seminary_info',
                'college_attending': 'college_attending',
                'college_name': 'college_name',
                'college_major': 'college_major',
                'medical_conditions': 'medical_conditions',
                'insurance_company': 'insurance_company',
                'blood_type': 'blood_type',
                'past_jobs': 'past_jobs',
                'summer_activities': 'summer_activities',
                'additional_info': 'additional_info'
            }
            
            # Copy all fields
            for app_field, student_field in field_mappings.items():
                if hasattr(application, app_field):
                    setattr(student, student_field, getattr(application, app_field))
            
            # Set additional student fields
            student.id = str(uuid.uuid4())
            student.status = 'Active'
            student.application_id = application_id
            student.accepted_date = datetime.utcnow()
            
            db.session.add(student)
            
            # Copy file attachments
            for attachment in application.attachments:
                # Create a copy of the attachment for the student
                student_attachment = FileAttachment(
                    student_id=student.id,
                    application_id=None,
                    filename=attachment.filename,
                    file_path=attachment.file_path,
                    file_type=attachment.file_type,
                    uploaded_date=datetime.utcnow()
                )
                db.session.add(student_attachment)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Application {new_status.lower()}',
            'redirect': url_for('students.student_details', student_id=student.id) if new_status == 'Accepted' else None
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating application status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@applications.route('/api/applications/<application_id>/preview-acceptance-email', methods=['GET'])
@login_required
@permission_required('view_applications')
def preview_acceptance_email_for_application(application_id):
    """Preview acceptance email for an application."""
    try:
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        # Get the division config
        division_config = DivisionConfig.query.filter_by(division=application.division).first()
        
        # Generate email preview
        email_service = EmailService()
        email_content = email_service.generate_acceptance_email(
            student_name=application.student_name,
            division=application.division,
            email_template=division_config.acceptance_email_template if division_config else None
        )
        
        return jsonify({
            'subject': email_content['subject'],
            'body': email_content['body']
        })
    except Exception as e:
        current_app.logger.error(f"Error previewing acceptance email: {str(e)}")
        return jsonify({'error': str(e)}), 500

@applications.route('/api/applications/<application_id>/email-template', methods=['GET'])
@login_required
@permission_required('view_applications')
def get_email_template_for_application(application_id):
    """Get email template for an application's division."""
    try:
        application = Application.query.filter_by(id=application_id).first()
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        # Get the division config
        division_config = DivisionConfig.query.filter_by(division=application.division).first()
        
        if division_config and division_config.acceptance_email_template:
            return jsonify({
                'template': division_config.acceptance_email_template,
                'division': application.division
            })
        else:
            # Return default template
            default_template = '''Dear {student_name},

We are pleased to inform you that your application to our {division} program has been accepted!

Please contact us at your earliest convenience to complete the enrollment process.

Best regards,
Yeshiva Administration'''
            
            return jsonify({
                'template': default_template,
                'division': application.division,
                'is_default': True
            })
    except Exception as e:
        current_app.logger.error(f"Error getting email template: {str(e)}")
        return jsonify({'error': str(e)}), 500

@applications.route('/applications/create', methods=['GET', 'POST'])
@login_required
@permission_required('process_applications')
def create_manual_application():
    """Create a manual application."""
    if request.method == 'GET':
        return render_template('application_create.html')
    
    try:
        # Create new application
        application = Application()
        
        # Set basic fields
        application.id = str(uuid.uuid4())
        application.submitted_date = datetime.utcnow()
        application.status = 'Pending'
        application.created_manually = True
        application.created_by = current_user.id
        
        # Get form data
        data = request.form
        
        # Set all fields from form
        field_mappings = {
            'division': 'division',
            'student_first_name': 'student_first_name',
            'student_middle_name': 'student_middle_name',
            'student_last_name': 'student_last_name',
            'hebrew_name': 'hebrew_name',
            'informal_name': 'informal_name',
            'phone_number': 'phone_number',
            'email': 'email',
            'social_security_number': 'social_security_number',
            'date_of_birth': 'date_of_birth',
            'citizenship': 'citizenship',
            'high_school_graduate': 'high_school_graduate',
            'marital_status': 'marital_status',
            'spouse_name': 'spouse_name',
            # Address fields
            'address_line1': 'address_line1',
            'address_line2': 'address_line2',
            'address_city': 'address_city',
            'address_state': 'address_state',
            'address_zip': 'address_zip',
            'address_country': 'address_country',
            # Alternate address
            'alt_address_line1': 'alt_address_line1',
            'alt_address_line2': 'alt_address_line2',
            'alt_address_city': 'alt_address_city',
            'alt_address_state': 'alt_address_state',
            'alt_address_zip': 'alt_address_zip',
            'alt_address_country': 'alt_address_country',
            # Parent info
            'father_title': 'father_title',
            'father_first_name': 'father_first_name',
            'father_last_name': 'father_last_name',
            'father_phone': 'father_phone',
            'father_email': 'father_email',
            'father_occupation': 'father_occupation',
            'mother_title': 'mother_title',
            'mother_first_name': 'mother_first_name',
            'mother_last_name': 'mother_last_name',
            'mother_phone': 'mother_phone',
            'mother_email': 'mother_email',
            'mother_occupation': 'mother_occupation',
            # Grandparents
            'paternal_grandfather_first_name': 'paternal_grandfather_first_name',
            'paternal_grandfather_last_name': 'paternal_grandfather_last_name',
            'paternal_grandfather_phone': 'paternal_grandfather_phone',
            'paternal_grandfather_email': 'paternal_grandfather_email',
            'maternal_grandfather_first_name': 'maternal_grandfather_first_name',
            'maternal_grandfather_last_name': 'maternal_grandfather_last_name',
            'maternal_grandfather_phone': 'maternal_grandfather_phone',
            'maternal_grandfather_email': 'maternal_grandfather_email',
            # In-laws
            'inlaws_first_name': 'inlaws_first_name',
            'inlaws_last_name': 'inlaws_last_name',
            'inlaws_phone': 'inlaws_phone',
            'inlaws_email': 'inlaws_email',
            # Educational info
            'high_school_info': 'high_school_info',
            'seminary_info': 'seminary_info',
            'college_attending': 'college_attending',
            'college_name': 'college_name',
            'college_major': 'college_major',
            'college_expected_graduation': 'college_expected_graduation',
            # Learning info
            'last_rebbe_name': 'last_rebbe_name',
            'last_rebbe_phone': 'last_rebbe_phone',
            'gemora_sedorim_daily_count': 'gemora_sedorim_daily_count',
            'gemora_sedorim_length': 'gemora_sedorim_length',
            'learning_evaluation': 'learning_evaluation',
            # Medical info
            'medical_conditions': 'medical_conditions',
            'insurance_company': 'insurance_company',
            'blood_type': 'blood_type',
            # Activities
            'past_jobs': 'past_jobs',
            'summer_activities': 'summer_activities',
            # Financial
            'tuition_payment_status': 'tuition_payment_status',
            'amount_can_pay': 'amount_can_pay',
            'scholarship_amount_requested': 'scholarship_amount_requested',
            # Other
            'dormitory_meals_option': 'dormitory_meals_option',
            'additional_info': 'additional_info'
        }
        
        # Process each field
        for form_field, app_field in field_mappings.items():
            value = data.get(form_field, '').strip()
            
            # Handle date fields
            if 'date' in form_field and value:
                value = parse_date(value)
            
            # Handle numeric fields
            if form_field in ['amount_can_pay', 'scholarship_amount_requested'] and value:
                value = parse_decimal(value)
            
            setattr(application, app_field, value if value else None)
        
        # Set student_name as combination of first, middle, last
        name_parts = [
            application.student_first_name,
            application.student_middle_name,
            application.student_last_name
        ]
        application.student_name = ' '.join(part for part in name_parts if part)
        
        db.session.add(application)
        db.session.commit()
        
        flash('Application created successfully!', 'success')
        return redirect(url_for('applications.applications_list'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating manual application: {str(e)}")
        flash(f'Error creating application: {str(e)}', 'error')
        return redirect(url_for('applications.create_manual_application'))