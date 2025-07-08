from flask import current_app
from extensions import db
from models import (Student, AcademicYear, StudentEnrollmentHistory, 
                   StudentYearlyTracking, TuitionRecord)
from datetime import datetime, date
from sqlalchemy import and_, or_
from typing import List, Dict, Optional, Tuple
from services.student_progression_service import StudentProgressionService

class AcademicYearTransitionService:
    """Service class for managing academic year transitions and enrollment workflow"""
    
    def __init__(self):
        self.logger = current_app.logger
    
    def get_transition_summary(self, current_year_id: int, next_year_id: int) -> Dict:
        """Get summary of students and their transition status"""
        try:
            # Get current year students
            current_students = Student.query.filter(
                Student.last_enrollment_year_id == current_year_id,
                Student.student_type == 'Current'
            ).all()
            
            # Count students by enrollment status
            status_counts = {
                'pending': 0,
                'enrolled': 0,
                'withdrawn': 0,
                'total': len(current_students)
            }
            
            for student in current_students:
                status = student.enrollment_status_current_year or 'pending'
                status_counts[status.lower()] += 1
            
            # Get next year info
            next_year = AcademicYear.query.get(next_year_id)
            current_year = AcademicYear.query.get(current_year_id)
            
            return {
                'current_year': {
                    'id': current_year.id,
                    'label': current_year.year_label,
                    'start_date': current_year.start_date,
                    'end_date': current_year.end_date
                },
                'next_year': {
                    'id': next_year.id,
                    'label': next_year.year_label,
                    'start_date': next_year.start_date,
                    'end_date': next_year.end_date
                },
                'student_counts': status_counts,
                'transition_ready': status_counts['pending'] == 0
            }
        except Exception as e:
            self.logger.error(f"Error getting transition summary: {str(e)}")
            raise
    
    def initialize_next_year_enrollment(self, current_year_id: int, next_year_id: int) -> Dict:
        """Initialize all current students as 'Pending' for next academic year"""
        try:
            # Get all current students from the current year
            current_students = Student.query.filter(
                Student.last_enrollment_year_id == current_year_id,
                Student.student_type == 'Current'
            ).all()
            
            initialized_count = 0
            skipped_count = 0
            
            for student in current_students:
                # Check if student already has enrollment history for next year
                existing_history = StudentEnrollmentHistory.query.filter_by(
                    student_id=student.id,
                    academic_year_id=next_year_id
                ).first()
                
                if existing_history:
                    skipped_count += 1
                    continue
                
                # Set student's enrollment status to pending for next year
                student.enrollment_status_current_year = 'Pending'
                student.last_enrollment_year_id = next_year_id
                
                # Create enrollment history record
                enrollment_history = StudentEnrollmentHistory(
                    student_id=student.id,
                    academic_year_id=next_year_id,
                    enrollment_status='Pending',
                    previous_status=student.enrollment_status_current_year,
                    decision_date=datetime.utcnow(),
                    decision_by=current_app.config.get('SYSTEM_USER', 'System'),
                    decision_reason='Automatic transition to next academic year',
                    college_program_status_at_time=student.college_program_status,
                    student_type_at_time=student.student_type
                )
                db.session.add(enrollment_history)
                initialized_count += 1
            
            db.session.commit()
            
            return {
                'success': True,
                'initialized_count': initialized_count,
                'skipped_count': skipped_count,
                'total_students': len(current_students)
            }
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error initializing next year enrollment: {str(e)}")
            raise
    
    def bulk_enroll_students(self, student_ids: List[str], academic_year_id: int, 
                           enrollment_status: str, decision_by: str, 
                           decision_reason: str = None) -> Dict:
        """Bulk update enrollment status for multiple students"""
        try:
            updated_count = 0
            errors = []
            
            for student_id in student_ids:
                try:
                    result = self.update_student_enrollment(
                        student_id=student_id,
                        academic_year_id=academic_year_id,
                        enrollment_status=enrollment_status,
                        decision_by=decision_by,
                        decision_reason=decision_reason
                    )
                    if result['success']:
                        updated_count += 1
                    else:
                        errors.append(f"Student {student_id}: {result['error']}")
                except Exception as e:
                    errors.append(f"Student {student_id}: {str(e)}")
            
            return {
                'success': True,
                'updated_count': updated_count,
                'errors': errors,
                'total_students': len(student_ids)
            }
            
        except Exception as e:
            self.logger.error(f"Error in bulk enrollment: {str(e)}")
            raise
    
    def update_student_enrollment(self, student_id: str, academic_year_id: int,
                                enrollment_status: str, decision_by: str,
                                decision_reason: str = None, 
                                college_program_status: str = None,
                                apply_progression: bool = True) -> Dict:
        """Update individual student enrollment status with optional automatic progression"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'error': 'Student not found'}
            
            # Validate enrollment status
            valid_statuses = ['Pending', 'Enrolled', 'Withdrawn']
            if enrollment_status not in valid_statuses:
                return {'success': False, 'error': f'Invalid enrollment status: {enrollment_status}'}
            
            # Store previous status
            previous_status = student.enrollment_status_current_year
            
            # Update student enrollment status
            student.enrollment_status_current_year = enrollment_status
            student.last_enrollment_year_id = academic_year_id
            
            # Update student type based on enrollment status
            if enrollment_status == 'Withdrawn':
                student.student_type = 'Alumnus'
            elif enrollment_status == 'Enrolled':
                student.student_type = 'Current'
            
            # Update college program status if provided
            if college_program_status:
                student.college_program_status = college_program_status
            
            # Apply automatic progression if enrolling and progression is enabled
            progression_results = {}
            if enrollment_status == 'Enrolled' and apply_progression:
                progression_service = StudentProgressionService()
                progression_result = progression_service.process_student_enrollment_with_progression(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    enrollment_status=enrollment_status,
                    decision_by=decision_by,
                    decision_reason=decision_reason
                )
                if progression_result.get('success'):
                    progression_results = progression_result.get('progression_results', {})
                else:
                    progression_results = {'error': progression_result.get('reason', 'Unknown error')}
            elif enrollment_status == 'Enrolled':
                # If enrolling but progression is disabled, still advance college level automatically
                if student.college_program_status == 'Enrolled':
                    # Automatically advance college program levels based on previous year completion
                    self._advance_college_program_levels_for_new_year(student, academic_year_id)
            
            # Create enrollment history record
            enrollment_history = StudentEnrollmentHistory(
                student_id=student_id,
                academic_year_id=academic_year_id,
                enrollment_status=enrollment_status,
                previous_status=previous_status,
                decision_date=datetime.utcnow(),
                decision_by=decision_by,
                decision_reason=decision_reason or f'Enrollment decision: {enrollment_status}',
                college_program_status_at_time=student.college_program_status,
                student_type_at_time=student.student_type
            )
            db.session.add(enrollment_history)
            
            # Update or create StudentYearlyTracking record
            yearly_tracking = StudentYearlyTracking.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
            if not yearly_tracking:
                yearly_tracking = StudentYearlyTracking(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    enrollment_status=enrollment_status,
                    updated_by=decision_by
                )
                db.session.add(yearly_tracking)
            else:
                yearly_tracking.enrollment_status = enrollment_status
                yearly_tracking.updated_by = decision_by
                yearly_tracking.updated_at = datetime.utcnow()
                
                # Set withdrawal information if withdrawing
                if enrollment_status == 'Withdrawn':
                    yearly_tracking.withdrawal_date = date.today()
                    yearly_tracking.withdrawal_reason = decision_reason
            
            # Create or update TuitionRecord if enrolling
            if enrollment_status == 'Enrolled':
                tuition_record = TuitionRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=academic_year_id
                ).first()
                
                if not tuition_record:
                    tuition_record = TuitionRecord(
                        student_id=student_id,
                        academic_year_id=academic_year_id,
                        matriculation_status_for_year=student.computed_matriculation_status
                    )
                    db.session.add(tuition_record)
            
            db.session.commit()
            
            result = {
                'success': True,
                'student_name': student.student_name,
                'previous_status': previous_status,
                'new_status': enrollment_status,
                'college_program_status': student.college_program_status,
                'college_program_level': student.computed_college_program_level,
                'college_program_fall_level': student.college_program_fall_level,
                'college_program_spring_level': student.college_program_spring_level,
                'current_semester': student.current_semester
            }
            
            if progression_results:
                result['progression_results'] = progression_results
                
            return result
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error updating student enrollment: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_students_by_status(self, academic_year_id: int, 
                              enrollment_status: str = None,
                              division: str = None) -> List[Dict]:
        """Get students filtered by enrollment status and division"""
        try:
            query = Student.query.filter(
                Student.last_enrollment_year_id == academic_year_id
            )
            
            if enrollment_status:
                query = query.filter(Student.enrollment_status_current_year == enrollment_status)
            
            if division:
                query = query.filter(Student.division == division)
            
            students = query.all()
            
            result = []
            for student in students:
                # Get latest enrollment history
                latest_history = StudentEnrollmentHistory.query.filter_by(
                    student_id=student.id,
                    academic_year_id=academic_year_id
                ).order_by(StudentEnrollmentHistory.decision_date.desc()).first()
                
                result.append({
                    'id': student.id,
                    'student_name': student.student_name,
                    'division': student.division,
                    'enrollment_status': student.enrollment_status_current_year,
                    'college_program_status': student.college_program_status,
                    'student_type': student.student_type,
                    'last_decision_date': latest_history.decision_date if latest_history else None,
                    'last_decision_by': latest_history.decision_by if latest_history else None
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting students by status: {str(e)}")
            raise
    
    def get_student_enrollment_history(self, student_id: str) -> List[Dict]:
        """Get complete enrollment history for a student"""
        try:
            history = StudentEnrollmentHistory.query.filter_by(
                student_id=student_id
            ).order_by(StudentEnrollmentHistory.decision_date.desc()).all()
            
            result = []
            for record in history:
                academic_year = AcademicYear.query.get(record.academic_year_id)
                result.append({
                    'id': record.id,
                    'academic_year': academic_year.year_label if academic_year else 'Unknown',
                    'enrollment_status': record.enrollment_status,
                    'previous_status': record.previous_status,
                    'decision_date': record.decision_date,
                    'decision_by': record.decision_by,
                    'decision_reason': record.decision_reason,
                    'college_program_status': record.college_program_status_at_time,
                    'student_type': record.student_type_at_time
                })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting student enrollment history: {str(e)}")
            raise
    
    def finalize_academic_year_transition(self, current_year_id: int, next_year_id: int) -> Dict:
        """Finalize the transition by setting next year as active"""
        try:
            # Validate that all students have been processed
            pending_students = Student.query.filter(
                Student.last_enrollment_year_id == next_year_id,
                Student.enrollment_status_current_year == 'Pending'
            ).count()
            
            if pending_students > 0:
                return {
                    'success': False,
                    'error': f'Cannot finalize transition: {pending_students} students still have pending enrollment status'
                }
            
            # Update academic year flags
            current_year = AcademicYear.query.get(current_year_id)
            next_year = AcademicYear.query.get(next_year_id)
            
            if current_year:
                current_year.is_active = False
                current_year.is_current = False
            
            if next_year:
                next_year.is_active = True
                next_year.is_current = True
            
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Academic year transition finalized. {next_year.year_label} is now active.'
            }
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error finalizing academic year transition: {str(e)}")
            raise
    
    def _advance_college_program_levels_for_new_year(self, student: Student, academic_year_id: int) -> None:
        """Advance college program levels automatically based on previous year completion"""
        try:
            # Get previous academic year
            current_year = AcademicYear.query.get(academic_year_id)
            previous_year = AcademicYear.query.filter(
                AcademicYear.start_date < current_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            if not previous_year:
                # First year - start at Fall Level 1, Spring Level 1
                student.college_program_fall_level = 1
                student.college_program_spring_level = 1
                student.current_semester = 'Fall'
                return
            
            # Get the student's levels from previous year
            prev_fall_level = student.college_program_fall_level or 0
            prev_spring_level = student.college_program_spring_level or 0
            
            # Logic based on user's requirements:
            # If student started in Fall of previous year at Level 1, they should be Fall Level 2, Spring Level 2
            # If student started in Spring of previous year at Level 1, they should be Fall Level 1, Spring Level 2
            
            if prev_fall_level > 0 and prev_spring_level > 0:
                # Student completed both semesters - advance both by 1
                student.college_program_fall_level = min(prev_fall_level + 1, 5)
                student.college_program_spring_level = min(prev_spring_level + 1, 5)
            elif prev_fall_level > 0 and prev_spring_level == 0:
                # Student only did Fall semester - advance Fall by 1, start Spring at 1
                student.college_program_fall_level = min(prev_fall_level + 1, 5)
                student.college_program_spring_level = 1
            elif prev_fall_level == 0 and prev_spring_level > 0:
                # Student only did Spring semester (started in spring) - keep Fall at 1, advance Spring
                student.college_program_fall_level = 1
                student.college_program_spring_level = min(prev_spring_level + 1, 5)
            else:
                # No previous levels - start at Level 1 for both
                student.college_program_fall_level = 1
                student.college_program_spring_level = 1
            
            # Set current semester to Fall (start of new academic year)
            student.current_semester = 'Fall'
            
            # Update computed level
            student.college_program_level = student.computed_college_program_level
            
            # Check if student should graduate
            if student.should_graduate_college:
                student.college_program_status = 'Graduated'
                self.logger.info(f"Student {student.student_name} graduated from college program")
            
        except Exception as e:
            self.logger.error(f"Error advancing college program levels: {str(e)}")
            # Don't fail the enrollment if college advancement fails
            pass 