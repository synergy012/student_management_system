from flask import Blueprint, request, jsonify, render_template, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Student, AcademicYear, StudentEnrollmentHistory, db
from services.academic_year_service import AcademicYearTransitionService
from utils.decorators import permission_required
from datetime import datetime

academic_year_transition = Blueprint('academic_year_transition', __name__)

@academic_year_transition.route('/academic-year-transition')
@login_required
@permission_required('manage_users')
def transition_dashboard():
    """Main academic year transition dashboard"""
    try:
        # Get current and next academic years
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        # Get all academic years for selection
        all_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('academic_year_transition/dashboard.html',
                             current_year=current_year,
                             all_years=all_years)
    except Exception as e:
        current_app.logger.error(f"Error loading transition dashboard: {str(e)}")
        flash(f'Error loading transition dashboard: {str(e)}', 'error')
        return redirect(url_for('core.index'))

@academic_year_transition.route('/api/academic-year-transition/summary')
@login_required
@permission_required('manage_users')
def get_transition_summary():
    """Get transition summary between two academic years"""
    try:
        current_year_id = request.args.get('current_year_id', type=int)
        next_year_id = request.args.get('next_year_id', type=int)
        
        if not current_year_id or not next_year_id:
            return jsonify({'error': 'Both current_year_id and next_year_id are required'}), 400
        
        service = AcademicYearTransitionService()
        summary = service.get_transition_summary(current_year_id, next_year_id)
        
        return jsonify(summary)
    except Exception as e:
        current_app.logger.error(f"Error getting transition summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/initialize', methods=['POST'])
@login_required
@permission_required('manage_users')
def initialize_next_year():
    """Initialize all current students as 'Pending' for next academic year"""
    try:
        data = request.get_json()
        current_year_id = data.get('current_year_id')
        next_year_id = data.get('next_year_id')
        
        if not current_year_id or not next_year_id:
            return jsonify({'error': 'Both current_year_id and next_year_id are required'}), 400
        
        service = AcademicYearTransitionService()
        result = service.initialize_next_year_enrollment(current_year_id, next_year_id)
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error initializing next year: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/students')
@login_required
@permission_required('manage_users')
def get_students_by_status():
    """Get students filtered by enrollment status and division"""
    try:
        academic_year_id = request.args.get('academic_year_id', type=int)
        enrollment_status = request.args.get('enrollment_status')
        division = request.args.get('division')
        
        if not academic_year_id:
            return jsonify({'error': 'academic_year_id is required'}), 400
        
        service = AcademicYearTransitionService()
        students = service.get_students_by_status(academic_year_id, enrollment_status, division)
        
        return jsonify(students)
    except Exception as e:
        current_app.logger.error(f"Error getting students by status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/bulk-enroll', methods=['POST'])
@login_required
@permission_required('manage_users')
def bulk_enroll_students():
    """Bulk update enrollment status for multiple students"""
    try:
        data = request.get_json()
        student_ids = data.get('student_ids', [])
        academic_year_id = data.get('academic_year_id')
        enrollment_status = data.get('enrollment_status')
        decision_reason = data.get('decision_reason', '')
        
        if not student_ids:
            return jsonify({'error': 'student_ids is required'}), 400
        if not academic_year_id:
            return jsonify({'error': 'academic_year_id is required'}), 400
        if not enrollment_status:
            return jsonify({'error': 'enrollment_status is required'}), 400
        
        service = AcademicYearTransitionService()
        result = service.bulk_enroll_students(
            student_ids=student_ids,
            academic_year_id=academic_year_id,
            enrollment_status=enrollment_status,
            decision_by=current_user.username,
            decision_reason=decision_reason
        )
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in bulk enrollment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/student/<student_id>/enroll', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_student_enrollment(student_id):
    """Update individual student enrollment status"""
    try:
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        enrollment_status = data.get('enrollment_status')
        decision_reason = data.get('decision_reason', '')
        college_program_status = data.get('college_program_status')
        
        if not academic_year_id:
            return jsonify({'error': 'academic_year_id is required'}), 400
        if not enrollment_status:
            return jsonify({'error': 'enrollment_status is required'}), 400
        
        service = AcademicYearTransitionService()
        result = service.update_student_enrollment(
            student_id=student_id,
            academic_year_id=academic_year_id,
            enrollment_status=enrollment_status,
            decision_by=current_user.username,
            decision_reason=decision_reason,
            college_program_status=college_program_status
        )
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error updating student enrollment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/student/<student_id>/history')
@login_required
@permission_required('view_students')
def get_student_enrollment_history(student_id):
    """Get complete enrollment history for a student"""
    try:
        service = AcademicYearTransitionService()
        history = service.get_student_enrollment_history(student_id)
        
        return jsonify(history)
    except Exception as e:
        current_app.logger.error(f"Error getting student enrollment history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic_year_transition.route('/api/academic-year-transition/finalize', methods=['POST'])
@login_required
@permission_required('manage_users')
def finalize_transition():
    """Finalize the academic year transition"""
    try:
        data = request.get_json()
        current_year_id = data.get('current_year_id')
        next_year_id = data.get('next_year_id')
        
        if not current_year_id or not next_year_id:
            return jsonify({'error': 'Both current_year_id and next_year_id are required'}), 400
        
        service = AcademicYearTransitionService()
        result = service.finalize_academic_year_transition(current_year_id, next_year_id)
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error finalizing transition: {str(e)}")
        return jsonify({'error': str(e)}), 500 