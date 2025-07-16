from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import Student, AcademicYear, SecureFormToken, db
from services.enrollment_email_service import EnrollmentDecisionEmailService
from utils.decorators import permission_required
from datetime import datetime, timedelta

enrollment_email = Blueprint('enrollment_email', __name__)

@enrollment_email.route('/enrollment-emails')
@login_required
@permission_required('manage_users')
def email_dashboard():
    """Dashboard for managing enrollment decision emails"""
    try:
        # Get all academic years for selection
        academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        # Get current/active academic year
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        return render_template('enrollment_email/dashboard.html',
                             academic_years=academic_years,
                             current_year=current_year)
    except Exception as e:
        current_app.logger.error(f"Error loading enrollment email dashboard: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('core.index'))

@enrollment_email.route('/api/enrollment-emails/send-bulk', methods=['POST'])
@login_required
@permission_required('manage_users')
def send_bulk_enrollment_emails():
    """Send enrollment decision emails to multiple students"""
    try:
        data = request.get_json()
        student_ids = data.get('student_ids', [])
        academic_year_id = data.get('academic_year_id')
        response_deadline = data.get('response_deadline')
        
        if not student_ids:
            return jsonify({'error': 'No students selected'}), 400
        if not academic_year_id:
            return jsonify({'error': 'Academic year is required'}), 400
        
        # Parse response deadline if provided
        deadline = None
        if response_deadline:
            try:
                deadline = datetime.strptime(response_deadline, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid response deadline format'}), 400
        
        # Send emails
        service = EnrollmentDecisionEmailService()
        result = service.send_bulk_enrollment_decision_emails(student_ids, academic_year_id, deadline)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error sending bulk enrollment emails: {str(e)}")
        return jsonify({'error': str(e)}), 500

@enrollment_email.route('/api/enrollment-emails/send-single', methods=['POST'])
@login_required
@permission_required('manage_users')
def send_single_enrollment_email():
    """Send enrollment decision email to a single student"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        academic_year_id = data.get('academic_year_id')
        response_deadline = data.get('response_deadline')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        if not academic_year_id:
            return jsonify({'error': 'Academic year is required'}), 400
        
        # Parse response deadline if provided
        deadline = None
        if response_deadline:
            try:
                deadline = datetime.strptime(response_deadline, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid response deadline format'}), 400
        
        # Send email
        service = EnrollmentDecisionEmailService()
        result = service.send_enrollment_decision_email(student_id, academic_year_id, deadline)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error sending enrollment email: {str(e)}")
        return jsonify({'error': str(e)}), 500

@enrollment_email.route('/api/enrollment-emails/statistics')
@login_required
@permission_required('view_students')
def get_enrollment_email_statistics():
    """Get statistics for enrollment decision emails"""
    try:
        academic_year_id = request.args.get('academic_year_id', type=int)
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        service = EnrollmentDecisionEmailService()
        stats = service.get_enrollment_email_statistics(academic_year_id)
        
        return jsonify(stats)
        
    except Exception as e:
        current_app.logger.error(f"Error getting enrollment email statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@enrollment_email.route('/api/enrollment-emails/students-pending')
@login_required
@permission_required('view_students')
def get_students_pending_emails():
    """Get students who haven't received enrollment decision emails yet"""
    try:
        academic_year_id = request.args.get('academic_year_id', type=int)
        division = request.args.get('division')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        # Get students with pending enrollment status
        query = Student.query.filter(
            Student.last_enrollment_year_id == academic_year_id,
            Student.enrollment_status_current_year == 'Pending'
        )
        
        if division:
            query = query.filter(Student.division == division)
        
        students = query.all()
        
        # Check which students already have active email tokens
        student_data = []
        for student in students:
            # Check if student has an active enrollment decision token
            active_token = SecureFormToken.query.filter(
                SecureFormToken.form_type == 'enrollment_decision',
                SecureFormToken.is_used == False,
                SecureFormToken.expires_at > datetime.utcnow(),
                SecureFormToken.token_metadata.op('->>')('student_id') == str(student.id)
            ).first()
            
            student_data.append({
                'id': student.id,
                'student_name': student.student_name,
                'division': student.division,
                'email': student.email,
                'enrollment_status': student.enrollment_status_current_year,
                'has_active_email': active_token is not None,
                'token_expires': active_token.expires_at.isoformat() if active_token else None
            })
        
        return jsonify(student_data)
        
    except Exception as e:
        current_app.logger.error(f"Error getting students pending emails: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Student Response Routes (Public - No Login Required)

@enrollment_email.route('/enrollment-response/<token>')
def student_response_form(token):
    """Show enrollment decision response form to students"""
    try:
        # Validate token
        token_data = SecureFormToken.query.filter_by(
            token=token, 
            form_type='enrollment_decision',
            is_used=False
        ).first()
        
        if not token_data:
            return render_template('enrollment_email/invalid_link.html',
                                 error='Invalid or expired response link')
        
        if token_data.expires_at < datetime.utcnow():
            return render_template('enrollment_email/invalid_link.html',
                                 error='This response link has expired')
        
        # Get student and academic year info
        token_metadata = token_data.token_metadata or {}
        student_id = token_metadata.get('student_id')
        academic_year_id = token_metadata.get('academic_year_id')
        
        if not student_id or not academic_year_id:
            return render_template('enrollment_email/invalid_link.html',
                                 error='Invalid link data')
        
        student = Student.query.get(student_id)
        academic_year = AcademicYear.query.get(academic_year_id)
        
        if not student or not academic_year:
            return render_template('enrollment_email/invalid_link.html',
                                 error='Student or academic year not found')
        
        return render_template('enrollment_email/response_form.html',
                             student=student,
                             academic_year=academic_year,
                             token=token,
                             expires_at=token_data.expires_at)
        
    except Exception as e:
        current_app.logger.error(f"Error showing enrollment response form: {str(e)}")
        return render_template('enrollment_email/invalid_link.html',
                             error='An error occurred while loading the response form')

@enrollment_email.route('/api/enrollment-response/<token>', methods=['POST'])
def process_student_response(token):
    """Process student's enrollment decision response"""
    try:
        data = request.get_json() if request.is_json else request.form
        decision = data.get('decision')
        
        if not decision:
            return jsonify({'error': 'Enrollment decision is required'}), 400
        
        # Process the response
        service = EnrollmentDecisionEmailService()
        result = service.process_student_enrollment_response(token, decision)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Thank you! Your enrollment decision has been recorded: {result['enrollment_status']}",
                'student_name': result['student_name'],
                'enrollment_status': result['enrollment_status']
            })
        else:
            return jsonify({'error': result['error']}), 400
        
    except Exception as e:
        current_app.logger.error(f"Error processing student enrollment response: {str(e)}")
        return jsonify({'error': 'An error occurred while processing your response'}), 500

@enrollment_email.route('/enrollment-response/<token>/success')
def response_success(token):
    """Show success page after student responds"""
    try:
        # Get token info to show success message
        token_data = SecureFormToken.query.filter_by(token=token).first()
        
        if not token_data or not token_data.is_used:
            return redirect(url_for('enrollment_email.student_response_form', token=token))
        
        token_metadata = token_data.token_metadata or {}
        student_id = token_metadata.get('student_id')
        
        student = Student.query.get(student_id) if student_id else None
        
        return render_template('enrollment_email/response_success.html',
                             student=student,
                             used_at=token_data.used_at)
        
    except Exception as e:
        current_app.logger.error(f"Error showing response success page: {str(e)}")
        return render_template('enrollment_email/response_success.html')

# Admin Management Routes

@enrollment_email.route('/api/enrollment-emails/create-templates', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_email_templates():
    """Create default enrollment decision email templates for all divisions"""
    try:
        service = EnrollmentDecisionEmailService()
        results = []
        
        divisions = ['YZA', 'YOH', 'KOLLEL']
        
        for division in divisions:
            result = service.create_enrollment_decision_template(division)
            results.append({
                'division': division,
                'success': result['success'],
                'template_id': result.get('template_id'),
                'message': result.get('message')
            })
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        current_app.logger.error(f"Error creating email templates: {str(e)}")
        return jsonify({'error': str(e)}), 500

@enrollment_email.route('/api/enrollment-emails/preview', methods=['POST'])
@login_required
@permission_required('view_students')
def preview_enrollment_email():
    """Preview enrollment decision email for a student"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        academic_year_id = data.get('academic_year_id')
        
        if not student_id or not academic_year_id:
            return jsonify({'error': 'Student ID and Academic Year ID are required'}), 400
        
        student = Student.query.get(student_id)
        academic_year = AcademicYear.query.get(academic_year_id)
        
        if not student or not academic_year:
            return jsonify({'error': 'Student or academic year not found'}), 400
        
        # Get email template
        service = EnrollmentDecisionEmailService()
        template_result = service.create_enrollment_decision_template(student.division)
        
        from models import EmailTemplate
        template = EmailTemplate.query.get(template_result['template_id'])
        
        # Create preview variables (with dummy token for preview)
        preview_vars = {
            'student_name': student.student_name,
            'academic_year': academic_year.year_label,
            'response_deadline': (datetime.utcnow() + timedelta(days=30)).strftime('%B %d, %Y'),
            'link_expiry_date': (datetime.utcnow() + timedelta(days=30)).strftime('%B %d, %Y'),
            'enrollment_response_url': '[SECURE RESPONSE LINK WILL BE HERE]',
            'current_date': datetime.utcnow().strftime('%B %d, %Y'),
            'office_email': current_app.config.get('OFFICE_EMAIL', 'office@school.edu'),
            'office_phone': current_app.config.get('OFFICE_PHONE', '(555) 123-4567'),
            'office_hours': current_app.config.get('OFFICE_HOURS', 'Monday-Friday 9:00 AM - 5:00 PM')
        }
        
        # Render preview
        preview_subject = service._render_template_content(template.subject, preview_vars)
        preview_html = service._render_template_content(template.html_content, preview_vars)
        
        return jsonify({
            'success': True,
            'subject': preview_subject,
            'html_content': preview_html,
            'student_name': student.student_name,
            'recipients': service._get_email_recipients(student)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error previewing enrollment email: {str(e)}")
        return jsonify({'error': str(e)}), 500 