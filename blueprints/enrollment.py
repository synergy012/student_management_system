"""
Enrollment management blueprint for student enrollment communications
"""
from flask import Blueprint, request, jsonify, render_template, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Student, AcademicYear, SecureFormToken, db
from utils.decorators import permission_required
from datetime import datetime

enrollment = Blueprint('enrollment', __name__)

@enrollment.route('/enrollment-test')
@login_required
def enrollment_test():
    """Test route"""
    return "Enrollment test route works!"

@enrollment.route('/enrollment')
@login_required
@permission_required('view_students')
def enrollment_dashboard():
    """Main enrollment management dashboard"""
    try:
        # Get current academic year for default selections
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        # Get all academic years for selection
        all_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('enrollment/dashboard.html',
                             current_year=current_year,
                             all_years=all_years)
    except Exception as e:
        import traceback
        current_app.logger.error(f"Error loading enrollment dashboard: {str(e)}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return f"Error loading enrollment dashboard: {str(e)}<br><pre>{traceback.format_exc()}</pre>"

@enrollment.route('/api/enrollment-emails/statistics')
@login_required  
@permission_required('view_students')
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
@permission_required('view_students') 
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

@enrollment.route('/api/enrollment/students-by-year')
@login_required
@permission_required('view_students')
def get_students_by_academic_year():
    """Get students for a specific academic year with enrollment status"""
    try:
        academic_year_id = request.args.get('academic_year_id', type=int)
        division_filter = request.args.get('division')
        status_filter = request.args.get('status')
        
        if not academic_year_id:
            return jsonify({'success': False, 'error': 'Academic year ID is required'}), 400
        
        # Build query
        query = Student.query.filter_by(last_enrollment_year_id=academic_year_id)
        
        if division_filter:
            query = query.filter_by(division=division_filter)
        
        if status_filter:
            query = query.filter_by(enrollment_status_current_year=status_filter)
        
        students = query.all()
        
        student_list = []
        for student in students:
            # Check if student has active enrollment token
            active_token = SecureFormToken.query.filter_by(
                form_type='enrollment_response',
                is_used=False
            ).filter(
                SecureFormToken.token_metadata.op('->>')('student_id') == str(student.id),
                SecureFormToken.expires_at > datetime.utcnow()
            ).first()
            
            student_list.append({
                'id': student.id,
                'student_name': student.student_name,
                'division': student.division,
                'email': student.email,
                'enrollment_status': student.enrollment_status_current_year,
                'has_active_token': active_token is not None,
                'token_expires': active_token.expires_at.isoformat() if active_token else None
            })
        
        return jsonify({
            'success': True,
            'students': student_list,
            'total_count': len(student_list)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting students by academic year: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment/manual-update', methods=['POST'])
@login_required
@permission_required('edit_students')
def manual_enrollment_update():
    """Manually update student enrollment status"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        new_status = data.get('enrollment_status')
        academic_year_id = data.get('academic_year_id')
        
        if not student_id or not new_status:
            return jsonify({'success': False, 'error': 'Student ID and enrollment status are required'}), 400
        
        if new_status not in ['Pending', 'Enrolled', 'Withdrawn']:
            return jsonify({'success': False, 'error': 'Invalid enrollment status'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Update enrollment status
        old_status = student.enrollment_status_current_year
        student.enrollment_status_current_year = new_status
        
        # If academic year is provided, update that too
        if academic_year_id:
            student.last_enrollment_year_id = academic_year_id
        
        # Log the change in enrollment history
        from models import StudentEnrollmentHistory
        history = StudentEnrollmentHistory(
            student_id=student_id,
            academic_year_id=academic_year_id or student.last_enrollment_year_id,
            enrollment_status=new_status,
            change_reason=f'Manual update by {current_user.username}',
            changed_by=current_user.id,
            changed_at=datetime.utcnow()
        )
        db.session.add(history)
        db.session.commit()
        
        current_app.logger.info(f"Manual enrollment update: Student {student.student_name} ({student_id}) changed from {old_status} to {new_status} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'student_name': student.student_name,
            'old_status': old_status,
            'new_status': new_status,
            'message': f'Student {student.student_name} status updated to {new_status}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating enrollment status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@enrollment.route('/api/enrollment/bulk-update', methods=['POST'])
@login_required
@permission_required('edit_students')
def bulk_enrollment_update():
    """Bulk update enrollment status for multiple students"""
    try:
        data = request.get_json()
        student_ids = data.get('student_ids', [])
        new_status = data.get('enrollment_status')
        academic_year_id = data.get('academic_year_id')
        
        if not student_ids or not new_status:
            return jsonify({'success': False, 'error': 'Student IDs and enrollment status are required'}), 400
        
        if new_status not in ['Pending', 'Enrolled', 'Withdrawn']:
            return jsonify({'success': False, 'error': 'Invalid enrollment status'}), 400
        
        # Process each student
        updated_students = []
        failed_students = []
        
        for student_id in student_ids:
            try:
                student = Student.query.get(student_id)
                if not student:
                    failed_students.append({'id': student_id, 'error': 'Student not found'})
                    continue
                
                old_status = student.enrollment_status_current_year
                student.enrollment_status_current_year = new_status
                
                if academic_year_id:
                    student.last_enrollment_year_id = academic_year_id
                
                # Log the change
                from models import StudentEnrollmentHistory
                history = StudentEnrollmentHistory(
                    student_id=student_id,
                    academic_year_id=academic_year_id or student.last_enrollment_year_id,
                    enrollment_status=new_status,
                    change_reason=f'Bulk update by {current_user.username}',
                    changed_by=current_user.id,
                    changed_at=datetime.utcnow()
                )
                db.session.add(history)
                
                updated_students.append({
                    'id': student_id,
                    'name': student.student_name,
                    'old_status': old_status,
                    'new_status': new_status
                })
                
            except Exception as e:
                failed_students.append({'id': student_id, 'error': str(e)})
        
        db.session.commit()
        
        current_app.logger.info(f"Bulk enrollment update: {len(updated_students)} students updated to {new_status} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'updated_count': len(updated_students),
            'failed_count': len(failed_students),
            'updated_students': updated_students,
            'failed_students': failed_students,
            'message': f'Successfully updated {len(updated_students)} students to {new_status}'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in bulk enrollment update: {str(e)}")
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