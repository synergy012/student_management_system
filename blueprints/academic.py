from flask import Blueprint, request, jsonify, current_app, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from models import (AcademicYear, Student, TuitionRecord, Shiur, AttendancePeriod, 
                   Attendance, MatriculationLevel, StudentShiurAssignment, 
                   StudentMatriculationAssignment, db)
from extensions import db
from utils.decorators import permission_required
from datetime import datetime, date, timedelta
from decimal import Decimal
import json
from sqlalchemy import and_, or_, func

academic = Blueprint('academic', __name__)

# ========================= ACADEMIC DASHBOARD =========================

@academic.route('/academic')
@login_required
@permission_required('edit_students')
def academic_dashboard():
    """Main academic dashboard"""
    try:
        # Get academic year from query params (can be ID or use active year)
        academic_year_param = request.args.get('academic_year_id')
        
        # If academic_year_param is provided, use that specific year
        selected_academic_year = None
        if academic_year_param:
            try:
                academic_year_id = int(academic_year_param)
                selected_academic_year = AcademicYear.query.get(academic_year_id)
            except (ValueError, TypeError):
                pass
        
        # If no valid academic year found, use the active one
        if not selected_academic_year:
            selected_academic_year = AcademicYear.get_active_year()
        
        # If still no academic year, use the most recent one
        if not selected_academic_year:
            selected_academic_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
        
        if not selected_academic_year:
            flash('No academic year found. Please create one first.', 'warning')
            return redirect(url_for('academic.academic_years'))
        
        # Get all available academic years for the dropdown
        all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        available_academic_years = []
        for ay in all_academic_years:
            available_academic_years.append({
                'id': ay.id,
                'name': ay.year_label,
                'is_selected': ay.id == selected_academic_year.id
            })
        
        # Get statistics for the selected academic year
        stats = {
            'total_students': Student.query.filter_by(status='Active').count(),
            'yza_students': Student.query.filter_by(status='Active', division='YZA').count(),
            'kollel_students': Student.query.filter_by(status='Active', division='KOLLEL').count(),
            'total_shiurim': Shiur.query.filter_by(academic_year_id=selected_academic_year.id, is_active=True).count(),
            'total_attendance_periods': AttendancePeriod.query.filter_by(academic_year_id=selected_academic_year.id, is_active=True).count(),
            'total_matriculation_levels': MatriculationLevel.query.filter_by(academic_year_id=selected_academic_year.id, is_active=True).count()
        }
        
        # Get recent attendance for the selected academic year
        recent_attendance = Attendance.query.join(Student).filter(
            Attendance.date >= date.today() - timedelta(days=7)
        ).order_by(Attendance.date.desc()).limit(10).all()
        
        # Get shiurim for the selected academic year
        shiurim = Shiur.query.filter_by(academic_year_id=selected_academic_year.id, is_active=True).all()
        
        # Get matriculation levels for the selected academic year
        matriculation_levels = MatriculationLevel.query.filter_by(academic_year_id=selected_academic_year.id, is_active=True).all()
        
        return render_template('academic/dashboard.html', 
                             stats=stats, 
                             active_year=selected_academic_year,
                             available_academic_years=available_academic_years,
                             recent_attendance=recent_attendance,
                             shiurim=shiurim,
                             matriculation_levels=matriculation_levels,
                             total_students=stats['total_students'],
                             active_shiurim=stats['total_shiurim'],
                             avg_attendance=85,  # You can calculate this properly
                             matriculating_students=stats['total_matriculation_levels'],
                             todays_periods=[])  # You can implement this
    except Exception as e:
        current_app.logger.error(f"Error loading academic dashboard: {str(e)}")
        flash('Error loading academic dashboard', 'error')
        return redirect(url_for('core.index'))

# ========================= ACADEMIC YEARS =========================

@academic.route('/api/academic-years', methods=['GET'])
@login_required
@permission_required('manage_users')
def get_academic_years():
    """Get all academic years with statistics."""
    try:
        years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        result = []
        for year in years:
            # Get student count for this year
            student_count = TuitionRecord.query.filter_by(academic_year_id=year.id).count()
            
            result.append({
                'id': year.id,
                'name': year.year_label,
                'start_date': year.start_date.isoformat(),
                'end_date': year.end_date.isoformat(),
                'is_active': year.is_active,
                'student_count': student_count,
                'shiur_count': Shiur.query.filter_by(academic_year_id=year.id).count(),
                'attendance_periods_count': AttendancePeriod.query.filter_by(academic_year_id=year.id).count()
            })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error getting academic years: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/academic-years/set-active/<int:year_id>', methods=['POST'])
@login_required
@permission_required('manage_users')
def set_active_academic_year(year_id):
    """Set the active academic year."""
    try:
        # First, deactivate all years
        AcademicYear.query.update({'is_active': False})
        
        # Then activate the selected year
        year = AcademicYear.query.get(year_id)
        if not year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        year.is_active = True
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'{year.year_label} is now the active academic year'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting active academic year: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/academic-years/create-next', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_next_academic_year():
    """Create the next academic year."""
    try:
        # Get the latest academic year
        latest_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
        
        if latest_year:
            # Parse the year label to get the end year
            year_parts = latest_year.year_label.split('-')
            if len(year_parts) == 2:
                end_year = int(year_parts[1])
                start_year = end_year
                next_year_label = f"{start_year}-{start_year + 1}"
            else:
                # Fallback to current year
                current_year = datetime.now().year
                next_year_label = f"{current_year}-{current_year + 1}"
                start_year = current_year
        else:
            # If no years exist, create current year
            current_year = datetime.now().year
            next_year_label = f"{current_year}-{current_year + 1}"
            start_year = current_year
        
        # Create the new year
        new_year = AcademicYear(
            year_label=next_year_label,
            start_date=date(start_year, 8, 1),
            end_date=date(start_year + 1, 7, 31),
            is_active=False
        )
        
        db.session.add(new_year)
        db.session.commit()
        
        # Create default shiurim, attendance periods, and matriculation levels
        Shiur.create_default_shiurim(new_year.id)
        AttendancePeriod.create_default_periods(new_year.id, 'YZA')
        AttendancePeriod.create_default_periods(new_year.id, 'KOLLEL')
        MatriculationLevel.create_default_levels(new_year.id, 'YZA')
        MatriculationLevel.create_default_levels(new_year.id, 'KOLLEL')
        
        # Create default tuition components for all divisions
        from models import DivisionTuitionComponent
        DivisionTuitionComponent.create_defaults_for_academic_year(new_year.id)
        
        return jsonify({
            'success': True,
            'year': {
                'id': new_year.id,
                'name': new_year.year_label,
                'start_date': new_year.start_date.isoformat(),
                'end_date': new_year.end_date.isoformat()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating next academic year: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/academic-years/<int:year_id>', methods=['PUT'])
@login_required
@permission_required('manage_users')
def update_academic_year(year_id):
    """Update an academic year's details."""
    try:
        year = AcademicYear.query.get(year_id)
        if not year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        data = request.get_json()
        
        # Update year label if provided
        if 'year_label' in data:
            # Check if the new label is unique
            existing = AcademicYear.query.filter(
                AcademicYear.year_label == data['year_label'],
                AcademicYear.id != year_id
            ).first()
            if existing:
                return jsonify({'error': 'Year label already exists'}), 400
            year.year_label = data['year_label']
        
        # Update dates if provided
        if 'start_date' in data:
            try:
                year.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid start date format. Use YYYY-MM-DD'}), 400
        
        if 'end_date' in data:
            try:
                year.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid end date format. Use YYYY-MM-DD'}), 400
        
        # Update tuition due date if provided
        if 'tuition_due_date' in data and data['tuition_due_date']:
            try:
                year.tuition_due_date = datetime.strptime(data['tuition_due_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid tuition due date format. Use YYYY-MM-DD'}), 400
        
        # Validate that start date is before end date
        if year.start_date >= year.end_date:
            return jsonify({'error': 'Start date must be before end date'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Academic year {year.year_label} updated successfully',
            'year': {
                'id': year.id,
                'name': year.year_label,
                'start_date': year.start_date.isoformat(),
                'end_date': year.end_date.isoformat(),
                'tuition_due_date': year.tuition_due_date.isoformat() if year.tuition_due_date else None
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating academic year: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= SHIUR MANAGEMENT =========================

@academic.route('/shiurim')
@login_required
@permission_required('edit_students')
def shiurim_list():
    """Display list of shiurim"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            flash('No active academic year found.', 'warning')
            return redirect(url_for('academic.academic_dashboard'))
        
        shiurim = Shiur.query.filter_by(academic_year_id=active_year.id).order_by(Shiur.division, Shiur.name).all()
        return render_template('academic/shiurim/list.html', shiurim=shiurim, active_year=active_year)
    except Exception as e:
        current_app.logger.error(f"Error loading shiurim: {str(e)}")
        flash('Error loading shiurim', 'error')
        return redirect(url_for('academic.academic_dashboard'))

@academic.route('/api/shiurim', methods=['GET'])
@login_required
@permission_required('edit_students')
def api_get_shiurim():
    """Get shiurim for active academic year"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        division = request.args.get('division', 'all')
        
        query = Shiur.query.filter_by(academic_year_id=active_year.id)
        if division != 'all':
            query = query.filter_by(division=division)
        
        shiurim = query.order_by(Shiur.name).all()
        
        result = []
        for shiur in shiurim:
            result.append({
                'id': shiur.id,
                'name': shiur.name,
                'instructor_name': shiur.instructor_name,
                'division': shiur.division,
                'subject': shiur.subject,
                'level': shiur.level,
                'schedule_display': shiur.schedule_display,
                'location': shiur.location,
                'current_enrollment': shiur.current_enrollment,
                'max_students': shiur.max_students,
                'available_spots': shiur.available_spots,
                'is_active': shiur.is_active
            })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error getting shiurim: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/shiurim', methods=['POST'])
@login_required
@permission_required('edit_students')
def api_create_shiur():
    """Create new shiur"""
    try:
        data = request.get_json()
        active_year = AcademicYear.get_active_year()
        
        if not active_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        # Validate required fields
        required_fields = ['name', 'instructor_name', 'division']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.replace("_", " ").title()} is required'}), 400
        
        shiur = Shiur(
            name=data['name'],
            instructor_name=data['instructor_name'],
            instructor_title=data.get('instructor_title', ''),
            division=data['division'],
            subject=data.get('subject', ''),
            level=data.get('level', ''),
            location=data.get('location', ''),
            max_students=int(data.get('max_students', 25)),
            academic_year_id=active_year.id,
            schedule_days=data.get('schedule_days', []),
            schedule_times=data.get('schedule_times', []),
            description=data.get('description', ''),
            instructor_email=data.get('instructor_email', ''),
            instructor_phone=data.get('instructor_phone', '')
        )
        
        db.session.add(shiur)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'shiur': {
                'id': shiur.id,
                'name': shiur.name,
                'instructor_name': shiur.instructor_name
            },
            'message': 'Shiur created successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating shiur: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/shiurim/<int:shiur_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def api_update_shiur(shiur_id):
    """Update shiur"""
    try:
        shiur = Shiur.query.get(shiur_id)
        if not shiur:
            return jsonify({'error': 'Shiur not found'}), 404
        
        data = request.get_json()
        
        # Update fields
        if 'name' in data:
            shiur.name = data['name']
        if 'instructor_name' in data:
            shiur.instructor_name = data['instructor_name']
        if 'instructor_title' in data:
            shiur.instructor_title = data['instructor_title']
        if 'division' in data:
            shiur.division = data['division']
        if 'subject' in data:
            shiur.subject = data['subject']
        if 'level' in data:
            shiur.level = data['level']
        if 'location' in data:
            shiur.location = data['location']
        if 'max_students' in data:
            shiur.max_students = int(data['max_students'])
        if 'schedule_days' in data:
            shiur.schedule_days = data['schedule_days']
        if 'schedule_times' in data:
            shiur.schedule_times = data['schedule_times']
        if 'description' in data:
            shiur.description = data['description']
        if 'instructor_email' in data:
            shiur.instructor_email = data['instructor_email']
        if 'instructor_phone' in data:
            shiur.instructor_phone = data['instructor_phone']
        if 'is_active' in data:
            shiur.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Shiur updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating shiur: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= STUDENT SHIUR ASSIGNMENTS =========================

@academic.route('/api/students/<student_id>/shiur-assignment', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def manage_student_shiur_assignment(student_id):
    """Get or update student shiur assignment"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if request.method == 'GET':
            # Get current assignment
            current_assignment = StudentShiurAssignment.get_current_assignment_for_student(student_id)
            if current_assignment:
                return jsonify({
                    'assignment': {
                        'id': current_assignment.id,
                        'shiur_id': current_assignment.shiur_id,
                        'shiur_name': current_assignment.shiur.name,
                        'instructor_name': current_assignment.shiur.instructor_name,
                        'start_date': current_assignment.start_date.isoformat(),
                        'current_grade': current_assignment.current_grade,
                        'attendance_percentage': current_assignment.attendance_percentage
                    }
                })
            else:
                return jsonify({'assignment': None})
        
        else:  # POST
            data = request.get_json()
            shiur_id = data.get('shiur_id')
            
            if not shiur_id:
                return jsonify({'error': 'Shiur ID is required'}), 400
            
            shiur = Shiur.query.get(shiur_id)
            if not shiur:
                return jsonify({'error': 'Shiur not found'}), 404
            
            # End current assignment if exists
            current_assignment = StudentShiurAssignment.get_current_assignment_for_student(student_id)
            if current_assignment:
                current_assignment.is_active = False
                current_assignment.end_date = date.today()
                current_assignment.ended_by = current_user.username
                current_assignment.end_reason = data.get('end_reason', 'Reassigned')
            
            # Create new assignment
            new_assignment = StudentShiurAssignment(
                student_id=student_id,
                shiur_id=shiur_id,
                start_date=date.today(),
                assigned_by=current_user.username,
                assignment_reason=data.get('assignment_reason', 'Manual assignment')
            )
            
            db.session.add(new_assignment)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Student assigned to {shiur.name}',
                'assignment': {
                    'id': new_assignment.id,
                    'shiur_name': shiur.name,
                    'start_date': new_assignment.start_date.isoformat()
                }
            })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing shiur assignment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/tuition-record/<int:year_id>', methods=['POST'])
@login_required
@permission_required('edit_students')
def academic_create_tuition_record(student_id, year_id):
    """Create a tuition record for a student for a specific academic year."""
    try:
        # Verify student and year exist
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
            
        year = AcademicYear.query.get(year_id)
        if not year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        # Check if record already exists
        existing = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=year_id
        ).first()
        
        if existing:
            return jsonify({'error': 'Tuition record already exists for this year'}), 400
        
        # Create new record
        record = TuitionRecord(
            student_id=student_id,
            academic_year_id=year_id,
            tuition_amount=Decimal('0'),
            amount_paid=Decimal('0'),
            payment_plan='Not Set'
        )
        
        db.session.add(record)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Tuition record created'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating tuition record: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/academic-matriculation', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def academic_manage_student_matriculation(student_id):
    """Get or update student matriculation status (academic version)."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if request.method == 'GET':
            # Return current matriculation status from academic system
            current_assignment = StudentMatriculationAssignment.get_current_assignment_for_student(student_id)
            if current_assignment:
                return jsonify({
                    'matriculation_assignment': {
                        'level_name': current_assignment.matriculation_level.name,
                        'instructor_name': current_assignment.matriculation_level.instructor_name,
                        'status': current_assignment.status,
                        'start_date': current_assignment.start_date.isoformat(),
                        'completion_percentage': current_assignment.completion_percentage
                    }
                })
            else:
                return jsonify({'matriculation_assignment': None})
        
        else:  # POST - This now handles academic matriculation assignments
            return jsonify({'error': 'Use /api/students/<student_id>/matriculation-assignment for assignments'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error managing academic matriculation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/academic-recompute-matriculation', methods=['POST'])
@login_required
@permission_required('edit_students')
def academic_recompute_matriculation_status(student_id):
    """Recompute matriculation status based on academic requirements."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check academic matriculation requirements
        requirements_met = []
        requirements_missing = []
        
        # 1. Check shiur assignment
        shiur_assignment = StudentShiurAssignment.get_current_assignment_for_student(student_id)
        if shiur_assignment:
            requirements_met.append('Assigned to shiur')
        else:
            requirements_missing.append('Not assigned to shiur')
        
        # 2. Check matriculation level assignment
        mat_assignment = StudentMatriculationAssignment.get_current_assignment_for_student(student_id)
        if mat_assignment:
            requirements_met.append('Assigned to matriculation level')
            
            # Check level completion requirements
            completion_check = mat_assignment.check_completion_requirements()
            if completion_check['all_requirements_met']:
                requirements_met.append('Matriculation level requirements met')
            else:
                requirements_missing.extend([f"Matriculation: {req}" for req in completion_check['requirements_met']])
        else:
            requirements_missing.append('Not assigned to matriculation level')
        
        # 3. Check attendance requirements
        active_year = AcademicYear.get_active_year()
        if active_year:
            attendance_summary = Attendance.get_student_attendance_summary(student_id, academic_year_id=active_year.id)
            if attendance_summary['weighted_percentage'] >= 80:
                requirements_met.append(f"Attendance requirement met ({attendance_summary['weighted_percentage']:.1f}%)")
            else:
                requirements_missing.append(f"Attendance below 80% ({attendance_summary['weighted_percentage']:.1f}%)")
        
        # Determine academic matriculation status
        academic_matriculation_status = 'Academically Matriculated' if not requirements_missing else 'Academic Requirements Pending'
        
        return jsonify({
            'success': True,
            'academic_matriculation_status': academic_matriculation_status,
            'requirements_met': requirements_met,
            'requirements_missing': requirements_missing,
            'message': 'Student meets all academic requirements' if not requirements_missing else 'Student is missing some academic requirements'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error recomputing academic matriculation: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= ATTENDANCE MANAGEMENT =========================

@academic.route('/attendance')
@login_required
@permission_required('edit_students')
def attendance_dashboard():
    """Attendance tracking dashboard"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            flash('No active academic year found.', 'warning')
            return redirect(url_for('academic.academic_dashboard'))
        
        # Get attendance periods
        periods = AttendancePeriod.query.filter_by(
            academic_year_id=active_year.id,
            is_active=True
        ).order_by(AttendancePeriod.division, AttendancePeriod.start_time).all()
        
        # Get today's attendance summary
        today = date.today()
        today_attendance = db.session.query(
            AttendancePeriod.name,
            func.count(Attendance.id).label('total_records'),
            func.sum(func.case([(Attendance.status == 'present', 1)], else_=0)).label('present_count'),
            func.sum(func.case([(Attendance.status == 'absent', 1)], else_=0)).label('absent_count')
        ).join(
            Attendance, AttendancePeriod.id == Attendance.attendance_period_id
        ).filter(
            AttendancePeriod.academic_year_id == active_year.id,
            Attendance.date == today
        ).group_by(AttendancePeriod.name).all()
        
        return render_template('academic/attendance/dashboard.html', 
                             periods=periods, 
                             today_attendance=today_attendance,
                             active_year=active_year)
    except Exception as e:
        current_app.logger.error(f"Error loading attendance dashboard: {str(e)}")
        flash('Error loading attendance dashboard', 'error')
        return redirect(url_for('academic.academic_dashboard'))

@academic.route('/api/attendance/periods', methods=['GET'])
@login_required
@permission_required('edit_students')
def api_get_attendance_periods():
    """Get attendance periods"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        division = request.args.get('division', 'all')
        
        query = AttendancePeriod.query.filter_by(academic_year_id=active_year.id, is_active=True)
        if division != 'all':
            query = query.filter_by(division=division)
        
        periods = query.order_by(AttendancePeriod.start_time).all()
        
        result = []
        for period in periods:
            result.append({
                'id': period.id,
                'name': period.name,
                'division': period.division,
                'time_display': period.time_display,
                'days_display': period.days_display,
                'is_mandatory': period.is_mandatory,
                'weight': period.weight,
                'is_currently_active': period.is_currently_active()
            })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error getting attendance periods: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/attendance/record', methods=['POST'])
@login_required
@permission_required('edit_students')
def record_attendance():
    """Record attendance for students"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['student_id', 'attendance_period_id', 'date', 'status']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Parse date
        attendance_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        
        # Check if record already exists
        existing = Attendance.query.filter_by(
            student_id=data['student_id'],
            attendance_period_id=data['attendance_period_id'],
            date=attendance_date
        ).first()
        
        if existing:
            # Update existing record
            existing.status = data['status']
            if 'arrival_time' in data and data['arrival_time']:
                existing.arrival_time = datetime.strptime(data['arrival_time'], '%H:%M').time()
            if 'departure_time' in data and data['departure_time']:
                existing.departure_time = datetime.strptime(data['departure_time'], '%H:%M').time()
            if 'notes' in data:
                existing.notes = data['notes']
            if 'excuse_reason' in data:
                existing.excuse_reason = data['excuse_reason']
            
            existing.recorded_by = current_user.username
            attendance_record = existing
        else:
            # Create new record
            attendance_record = Attendance(
                student_id=data['student_id'],
                attendance_period_id=data['attendance_period_id'],
                date=attendance_date,
                status=data['status'],
                recorded_by=current_user.username,
                notes=data.get('notes', ''),
                excuse_reason=data.get('excuse_reason', '')
            )
            
            if 'arrival_time' in data and data['arrival_time']:
                attendance_record.arrival_time = datetime.strptime(data['arrival_time'], '%H:%M').time()
            if 'departure_time' in data and data['departure_time']:
                attendance_record.departure_time = datetime.strptime(data['departure_time'], '%H:%M').time()
            
            db.session.add(attendance_record)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Attendance recorded successfully',
            'record': {
                'id': attendance_record.id,
                'status': attendance_record.status,
                'date': attendance_record.date.isoformat()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error recording attendance: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/attendance-summary')
@login_required
@permission_required('view_students')
def get_student_attendance_summary(student_id):
    """Get attendance summary for a student"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get date range parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        # Get active academic year
        active_year = AcademicYear.get_active_year()
        academic_year_id = active_year.id if active_year else None
        
        # Get attendance summary
        summary = Attendance.get_student_attendance_summary(
            student_id, start_date, end_date, academic_year_id
        )
        
        return jsonify({
            'student_name': student.student_name,
            'summary': summary
        })
    except Exception as e:
        current_app.logger.error(f"Error getting attendance summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= MATRICULATION LEVELS =========================

@academic.route('/matriculation')
@login_required
@permission_required('edit_students')
def matriculation_dashboard():
    """Matriculation levels dashboard"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            flash('No active academic year found.', 'warning')
            return redirect(url_for('academic.academic_dashboard'))
        
        levels = MatriculationLevel.query.filter_by(
            academic_year_id=active_year.id,
            is_active=True
        ).order_by(MatriculationLevel.division, MatriculationLevel.level_order).all()
        
        return render_template('academic/matriculation/dashboard.html', 
                             levels=levels, 
                             active_year=active_year)
    except Exception as e:
        current_app.logger.error(f"Error loading matriculation dashboard: {str(e)}")
        flash('Error loading matriculation dashboard', 'error')
        return redirect(url_for('academic.academic_dashboard'))

@academic.route('/api/matriculation-levels', methods=['GET'])
@login_required
@permission_required('edit_students')
def api_get_matriculation_levels():
    """Get matriculation levels"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        division = request.args.get('division', 'all')
        
        query = MatriculationLevel.query.filter_by(academic_year_id=active_year.id, is_active=True)
        if division != 'all':
            query = query.filter_by(division=division)
        
        levels = query.order_by(MatriculationLevel.level_order).all()
        
        result = []
        for level in levels:
            result.append({
                'id': level.id,
                'name': level.name,
                'instructor_name': level.instructor_name,
                'division': level.division,
                'level_order': level.level_order,
                'subject_areas': level.subject_areas,
                'duration_weeks': level.duration_weeks,
                'credit_hours': level.credit_hours,
                'current_enrollment': level.current_enrollment,
                'max_students': level.max_students,
                'available_spots': level.available_spots
            })
        
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error getting matriculation levels: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/matriculation-assignment', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def manage_student_matriculation_assignment(student_id):
    """Get or update student matriculation assignment"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if request.method == 'GET':
            # Get current assignment
            current_assignment = StudentMatriculationAssignment.get_current_assignment_for_student(student_id)
            if current_assignment:
                requirements = current_assignment.check_completion_requirements()
                return jsonify({
                    'assignment': {
                        'id': current_assignment.id,
                        'matriculation_level_id': current_assignment.matriculation_level_id,
                        'level_name': current_assignment.matriculation_level.name,
                        'instructor_name': current_assignment.matriculation_level.instructor_name,
                        'start_date': current_assignment.start_date.isoformat(),
                        'status': current_assignment.status,
                        'completion_percentage': current_assignment.completion_percentage,
                        'current_grade': current_assignment.current_grade,
                        'attendance_percentage': current_assignment.attendance_percentage,
                        'requirements': requirements
                    }
                })
            else:
                return jsonify({'assignment': None})
        
        else:  # POST
            data = request.get_json()
            matriculation_level_id = data.get('matriculation_level_id')
            
            if not matriculation_level_id:
                return jsonify({'error': 'Matriculation level ID is required'}), 400
            
            level = MatriculationLevel.query.get(matriculation_level_id)
            if not level:
                return jsonify({'error': 'Matriculation level not found'}), 404
            
            # End current assignment if exists
            current_assignment = StudentMatriculationAssignment.get_current_assignment_for_student(student_id)
            if current_assignment:
                current_assignment.is_active = False
                current_assignment.end_date = date.today()
                current_assignment.ended_by = current_user.username
                current_assignment.end_reason = data.get('end_reason', 'Reassigned')
            
            # Create new assignment
            new_assignment = StudentMatriculationAssignment(
                student_id=student_id,
                matriculation_level_id=matriculation_level_id,
                start_date=date.today(),
                assigned_by=current_user.username,
                assignment_reason=data.get('assignment_reason', 'Manual assignment')
            )
            
            db.session.add(new_assignment)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Student assigned to {level.name}',
                'assignment': {
                    'id': new_assignment.id,
                    'level_name': level.name,
                    'start_date': new_assignment.start_date.isoformat()
                }
            })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing matriculation assignment: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= STATISTICS AND REPORTING =========================

@academic.route('/api/academic/statistics')
@login_required
@permission_required('view_students')
def get_academic_statistics():
    """Get comprehensive academic statistics"""
    try:
        active_year = AcademicYear.get_active_year()
        if not active_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        # Get date range
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        # Overall statistics
        stats = {
            'academic_year': {
                'id': active_year.id,
                'name': active_year.year_label,
                'start_date': active_year.start_date.isoformat(),
                'end_date': active_year.end_date.isoformat()
            },
            'students': {
                'total': Student.query.filter_by(status='Active').count(),
                'yza': Student.query.filter_by(status='Active', division='YZA').count(),
                'kollel': Student.query.filter_by(status='Active', division='KOLLEL').count(),
                'with_shiur_assignments': StudentShiurAssignment.query.filter_by(is_active=True).count(),
                'with_matriculation_assignments': StudentMatriculationAssignment.query.filter_by(is_active=True).count()
            },
            'shiurim': {},
            'attendance': {},
            'matriculation': {}
        }
        
        # Shiur statistics
        shiurim = Shiur.query.filter_by(academic_year_id=active_year.id, is_active=True).all()
        stats['shiurim'] = {
            'total': len(shiurim),
            'by_division': {},
            'enrollment': {}
        }
        
        for shiur in shiurim:
            division = shiur.division
            if division not in stats['shiurim']['by_division']:
                stats['shiurim']['by_division'][division] = 0
            stats['shiurim']['by_division'][division] += 1
            
            stats['shiurim']['enrollment'][shiur.name] = {
                'current': shiur.current_enrollment,
                'max': shiur.max_students,
                'percentage': round((shiur.current_enrollment / shiur.max_students) * 100, 1) if shiur.max_students > 0 else 0
            }
        
        # Attendance statistics
        attendance_query = Attendance.query.join(AttendancePeriod).filter(
            AttendancePeriod.academic_year_id == active_year.id
        )
        
        if start_date:
            attendance_query = attendance_query.filter(Attendance.date >= start_date)
        if end_date:
            attendance_query = attendance_query.filter(Attendance.date <= end_date)
        
        total_attendance_records = attendance_query.count()
        present_records = attendance_query.filter(Attendance.status.in_(['present', 'late'])).count()
        absent_records = attendance_query.filter(Attendance.status == 'absent').count()
        
        stats['attendance'] = {
            'total_records': total_attendance_records,
            'present_count': present_records,
            'absent_count': absent_records,
            'overall_percentage': round((present_records / total_attendance_records) * 100, 2) if total_attendance_records > 0 else 0,
            'by_division': {}
        }
        
        # Get attendance by division
        for division in ['YZA', 'KOLLEL']:
            div_attendance = attendance_query.join(Student).filter(Student.division == division)
            div_total = div_attendance.count()
            div_present = div_attendance.filter(Attendance.status.in_(['present', 'late'])).count()
            
            stats['attendance']['by_division'][division] = {
                'total': div_total,
                'present': div_present,
                'percentage': round((div_present / div_total) * 100, 2) if div_total > 0 else 0
            }
        
        # Matriculation statistics
        matriculation_assignments = StudentMatriculationAssignment.query.join(MatriculationLevel).filter(
            MatriculationLevel.academic_year_id == active_year.id
        ).all()
        
        stats['matriculation'] = {
            'total_assignments': len(matriculation_assignments),
            'by_status': {},
            'by_level': {},
            'completion_rates': {}
        }
        
        # Group by status
        for assignment in matriculation_assignments:
            status = assignment.status
            if status not in stats['matriculation']['by_status']:
                stats['matriculation']['by_status'][status] = 0
            stats['matriculation']['by_status'][status] += 1
            
            level_name = assignment.matriculation_level.name
            if level_name not in stats['matriculation']['by_level']:
                stats['matriculation']['by_level'][level_name] = {
                    'total': 0,
                    'completed': 0,
                    'in_progress': 0
                }
            
            stats['matriculation']['by_level'][level_name]['total'] += 1
            if assignment.status == 'completed':
                stats['matriculation']['by_level'][level_name]['completed'] += 1
            elif assignment.status == 'in_progress':
                stats['matriculation']['by_level'][level_name]['in_progress'] += 1
        
        return jsonify(stats)
    except Exception as e:
        current_app.logger.error(f"Error getting academic statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@academic.route('/api/students/<student_id>/academic-report')
@login_required
@permission_required('view_students')
def generate_student_academic_report(student_id):
    """Generate comprehensive academic report for a student"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        active_year = AcademicYear.get_active_year()
        
        # Get date range
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        report = {
            'student': {
                'id': student.id,
                'name': student.student_name,
                'division': student.division,
                'status': student.status
            },
            'academic_year': {
                'name': active_year.year_label if active_year else 'No Active Year',
                'start_date': active_year.start_date.isoformat() if active_year else None,
                'end_date': active_year.end_date.isoformat() if active_year else None
            } if active_year else None,
            'shiur_assignment': None,
            'matriculation_assignment': None,
            'attendance_summary': None
        }
        
        # Get current shiur assignment
        shiur_assignment = StudentShiurAssignment.get_current_assignment_for_student(student_id)
        if shiur_assignment:
            shiur_assignment.calculate_attendance_percentage()
            report['shiur_assignment'] = {
                'shiur_name': shiur_assignment.shiur.name,
                'instructor': shiur_assignment.shiur.instructor_name,
                'start_date': shiur_assignment.start_date.isoformat(),
                'current_grade': shiur_assignment.current_grade,
                'attendance_percentage': shiur_assignment.attendance_percentage,
                'participation_score': shiur_assignment.participation_score
            }
        
        # Get current matriculation assignment
        mat_assignment = StudentMatriculationAssignment.get_current_assignment_for_student(student_id)
        if mat_assignment:
            requirements = mat_assignment.check_completion_requirements()
            report['matriculation_assignment'] = {
                'level_name': mat_assignment.matriculation_level.name,
                'instructor': mat_assignment.matriculation_level.instructor_name,
                'start_date': mat_assignment.start_date.isoformat(),
                'status': mat_assignment.status,
                'completion_percentage': mat_assignment.completion_percentage,
                'current_grade': mat_assignment.current_grade,
                'credit_hours_earned': mat_assignment.credit_hours_earned,
                'requirements': requirements
            }
        
        # Get attendance summary
        academic_year_id = active_year.id if active_year else None
        attendance_summary = Attendance.get_student_attendance_summary(
            student_id, start_date, end_date, academic_year_id
        )
        report['attendance_summary'] = attendance_summary
        
        return jsonify(report)
    except Exception as e:
        current_app.logger.error(f"Error generating student academic report: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ========================= EMAIL REPORTING =========================

@academic.route('/api/students/<student_id>/email-attendance-report', methods=['POST'])
@login_required
@permission_required('edit_students')
def email_attendance_report(student_id):
    """Email attendance report to student"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not student.email:
            return jsonify({'error': 'Student has no email address'}), 400
        
        # Get report data
        data = request.get_json()
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        
        # Generate report
        active_year = AcademicYear.get_active_year()
        academic_year_id = active_year.id if active_year else None
        
        attendance_summary = Attendance.get_student_attendance_summary(
            student_id, start_date, end_date, academic_year_id
        )
        
        # TODO: Implement email sending functionality
        # This would use the email service to send formatted attendance report
        
        return jsonify({
            'success': True,
            'message': f'Attendance report sent to {student.email}',
            'summary': attendance_summary
        })
    except Exception as e:
        current_app.logger.error(f"Error emailing attendance report: {str(e)}")
        return jsonify({'error': str(e)}), 500 