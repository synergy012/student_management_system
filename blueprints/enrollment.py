"""
Enrollment management blueprint for student enrollment communications
"""
from flask import Blueprint, request, jsonify, render_template, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Student, AcademicYear, SecureFormToken, db
from utils.decorators import permission_required
from datetime import datetime

enrollment = Blueprint('enrollment', __name__)

@enrollment.route('/enrollment')
@login_required
@permission_required('manage_users')
def enrollment_dashboard():
    """Main enrollment communications dashboard"""
    try:
        # Get current academic year for default selections
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        # Get all academic years for selection
        all_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('enrollment/dashboard.html',
                             current_year=current_year,
                             all_years=all_years)
    except Exception as e:
        current_app.logger.error(f"Error loading enrollment dashboard: {str(e)}")
        flash(f'Error loading enrollment dashboard: {str(e)}', 'error')
        return redirect(url_for('core.index'))

@enrollment.route('/api/enrollment-emails/statistics')
@login_required  
@permission_required('manage_users')
def get_enrollment_email_statistics():
    """Get enrollment email statistics"""
    try:
        # Get current academic year
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        if not current_year:
            return jsonify({
                'success': True,
                'emails_sent': 0,
                'pending_responses': 0,
                'response_rate': 0
            })
        
        # Count enrollment emails sent
        enrollment_tokens = SecureFormToken.query.filter_by(
            form_type='enrollment_response'
        ).all()
        
        emails_sent = len(enrollment_tokens)
        responded_tokens = len([t for t in enrollment_tokens if t.is_used])
        pending_responses = emails_sent - responded_tokens
        response_rate = (responded_tokens / emails_sent * 100) if emails_sent > 0 else 0
        
        return jsonify({
            'success': True,
            'emails_sent': emails_sent,
            'pending_responses': pending_responses,
            'response_rate': response_rate
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting enrollment email statistics: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment-emails/students-pending')
@login_required
@permission_required('manage_users') 
def get_students_pending_emails():
    """Get students who are pending enrollment emails"""
    try:
        # Get current academic year
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        if not current_year:
            return jsonify({'success': True, 'students': []})
        
        # Get students with pending enrollment status
        students = Student.query.filter_by(
            last_enrollment_year_id=current_year.id,
            enrollment_status_current_year='Pending'
        ).all()
        
        student_list = []
        for student in students:
            student_list.append({
                'id': student.id,
                'student_name': student.student_name,
                'division': student.division,
                'enrollment_status': student.enrollment_status_current_year,
                'last_updated': student.last_enrollment_year_id
            })
        
        return jsonify({
            'success': True,
            'students': student_list
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting students pending emails: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment-emails/send-bulk', methods=['POST'])
@login_required
@permission_required('manage_users')
def send_bulk_enrollment_emails():
    """Send bulk enrollment emails"""
    try:
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        division = data.get('division')
        enrollment_status = data.get('enrollment_status')
        
        if not academic_year_id:
            return jsonify({'success': False, 'error': 'Academic year ID is required'}), 400
        
        # Build query for students
        query = Student.query.filter_by(last_enrollment_year_id=academic_year_id)
        
        if division:
            query = query.filter_by(division=division)
        
        if enrollment_status:
            query = query.filter_by(enrollment_status_current_year=enrollment_status)
        
        students = query.all()
        
        # Import enrollment email service
        from services.enrollment_email_service import EnrollmentDecisionEmailService
        email_service = EnrollmentDecisionEmailService()
        
        emails_sent = 0
        errors = []
        
        for student in students:
            try:
                result = email_service.send_enrollment_decision_email(student.id)
                if result.get('success'):
                    emails_sent += 1
                else:
                    errors.append(f"Student {student.student_name}: {result.get('error', 'Unknown error')}")
            except Exception as e:
                errors.append(f"Student {student.student_name}: {str(e)}")
        
        return jsonify({
            'success': True,
            'emails_sent': emails_sent,
            'errors': errors,
            'total_students': len(students)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending bulk enrollment emails: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment-emails/send-single', methods=['POST'])
@login_required
@permission_required('manage_users')
def send_single_enrollment_email():
    """Send enrollment email to a single student"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'success': False, 'error': 'Student ID is required'}), 400
        
        # Import enrollment email service
        from services.enrollment_email_service import EnrollmentDecisionEmailService
        email_service = EnrollmentDecisionEmailService()
        
        result = email_service.send_enrollment_decision_email(student_id)
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error sending single enrollment email: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment-emails/create-templates', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_enrollment_email_templates():
    """Create default enrollment decision email templates for all divisions"""
    try:
        from services.enrollment_email_service import EnrollmentDecisionEmailService
        service = EnrollmentDecisionEmailService()
        results = []
        
        divisions = ['YZA', 'YOH', 'KOLLEL']
        created_count = 0
        
        for division in divisions:
            try:
                result = service.create_enrollment_decision_template(division)
                results.append({
                    'division': division,
                    'success': result['success'],
                    'template_id': result.get('template_id'),
                    'message': result.get('message')
                })
                if result['success']:
                    created_count += 1
            except Exception as e:
                results.append({
                    'division': division,
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'results': results,
            'created_count': created_count,
            'message': f'Successfully created/verified {created_count} enrollment email templates'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error creating enrollment email templates: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/academic-years')
@login_required
@permission_required('view_students')
def get_academic_years():
    """Get all academic years for enrollment email selection"""
    try:
        years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        academic_years = []
        
        for year in years:
            academic_years.append({
                'id': year.id,
                'year_label': year.year_label,
                'start_date': year.start_date.isoformat() if year.start_date else None,
                'end_date': year.end_date.isoformat() if year.end_date else None,
                'is_active': year.is_active
            })
        
        return jsonify({
            'success': True,
            'academic_years': academic_years
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting academic years: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500 