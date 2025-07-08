from flask import current_app
from extensions import db
from models import (Student, StudentShiurAssignment, BedAssignment, Shiur, Bed,
                   StudentEnrollmentHistory, AcademicYear)
from datetime import datetime, date
from typing import Dict, List, Optional

class StudentProgressionService:
    """Service for handling automatic student progression during enrollment"""
    
    def __init__(self):
        self.logger = current_app.logger
    
    def process_student_enrollment_with_progression(self, student_id: str, academic_year_id: int,
                                                  enrollment_status: str, decision_by: str,
                                                  decision_reason: str = None) -> Dict:
        """Process student enrollment with automatic progression logic"""
        try:
            if enrollment_status != 'Enrolled':
                # If not enrolling, don't apply progression logic
                return self._basic_enrollment_update(student_id, academic_year_id, enrollment_status, decision_by, decision_reason)
            
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'error': 'Student not found'}
            
            academic_year = AcademicYear.query.get(academic_year_id)
            if not academic_year:
                return {'success': False, 'error': 'Academic year not found'}
            
            # Store previous status
            previous_status = student.enrollment_status_current_year
            
            # Update basic enrollment status
            student.enrollment_status_current_year = enrollment_status
            student.last_enrollment_year_id = academic_year_id
            student.student_type = 'Current'
            
            progression_results = {}
            
            # Apply automatic progression logic
            if enrollment_status == 'Enrolled':
                # 1. Default to prior year shiur
                shiur_result = self._assign_prior_year_shiur(student, academic_year)
                progression_results['shiur'] = shiur_result
                
                # 2. Default to prior year bed  
                bed_result = self._assign_prior_year_bed(student, academic_year)
                progression_results['bed'] = bed_result
                
                # 3. Advance college program level automatically for new academic year
                college_result = self._advance_college_program_level_new_year(student, academic_year)
                progression_results['college_program'] = college_result
            
            # Create enrollment history record
            enrollment_history = StudentEnrollmentHistory(
                student_id=student_id,
                academic_year_id=academic_year_id,
                enrollment_status=enrollment_status,
                previous_status=previous_status,
                decision_date=datetime.utcnow(),
                decision_made_by=decision_by,
                decision_reason=decision_reason or 'Student enrollment with automatic progression',
                college_program_status_at_time=student.college_program_status,
                student_type_at_time=student.student_type,
                is_automatic=True,
                system_generated=True
            )
            
            db.session.add(enrollment_history)
            db.session.commit()
            
            self.logger.info(f"Student {student.student_name} enrolled with automatic progression for {academic_year.year_label}")
            
            return {
                'success': True,
                'student_name': student.student_name,
                'enrollment_status': enrollment_status,
                'college_program_status': student.college_program_status,
                'college_program_level': student.college_program_level,
                'progression_results': progression_results,
                'message': f'Student enrolled successfully with automatic progression applied'
            }
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error processing student enrollment with progression: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _basic_enrollment_update(self, student_id: str, academic_year_id: int,
                               enrollment_status: str, decision_by: str,
                               decision_reason: str = None) -> Dict:
        """Basic enrollment update without progression logic"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'error': 'Student not found'}
            
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
            
            # Create enrollment history record
            enrollment_history = StudentEnrollmentHistory(
                student_id=student_id,
                academic_year_id=academic_year_id,
                enrollment_status=enrollment_status,
                previous_status=previous_status,
                decision_date=datetime.utcnow(),
                decision_made_by=decision_by,
                decision_reason=decision_reason or f'Student status updated to {enrollment_status}',
                college_program_status_at_time=student.college_program_status,
                student_type_at_time=student.student_type
            )
            
            db.session.add(enrollment_history)
            db.session.commit()
            
            return {
                'success': True,
                'student_name': student.student_name,
                'enrollment_status': enrollment_status,
                'college_program_status': student.college_program_status,
                'message': f'Student enrollment status updated to {enrollment_status}'
            }
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error updating student enrollment: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _assign_prior_year_shiur(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Assign student to their prior year shiur if available"""
        try:
            # Get previous academic year
            previous_year = AcademicYear.query.filter(
                AcademicYear.start_date < academic_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            if not previous_year:
                return {'success': False, 'reason': 'No previous academic year found'}
            
            # Find student's previous shiur assignment
            previous_assignment = StudentShiurAssignment.query.filter_by(
                student_id=student.id,
                is_active=True
            ).join(Shiur).filter(
                Shiur.academic_year_id == previous_year.id
            ).first()
            
            if not previous_assignment:
                return {'success': False, 'reason': 'No previous shiur assignment found'}
            
            previous_shiur = previous_assignment.shiur
            
            # Look for equivalent shiur in new academic year
            new_shiur = Shiur.query.filter_by(
                academic_year_id=academic_year.id,
                name=previous_shiur.name,
                instructor_name=previous_shiur.instructor_name,
                division=student.division,
                is_active=True
            ).first()
            
            if not new_shiur:
                # Try to find by instructor name only
                new_shiur = Shiur.query.filter_by(
                    academic_year_id=academic_year.id,
                    instructor_name=previous_shiur.instructor_name,
                    division=student.division,
                    is_active=True
                ).first()
            
            if not new_shiur:
                return {'success': False, 'reason': f'No equivalent shiur found for {previous_shiur.name}'}
            
            # Check if student already has an active assignment for this year
            existing_assignment = StudentShiurAssignment.query.filter_by(
                student_id=student.id,
                is_active=True
            ).join(Shiur).filter(
                Shiur.academic_year_id == academic_year.id
            ).first()
            
            if existing_assignment:
                return {'success': False, 'reason': 'Student already has an active shiur assignment'}
            
            # End previous assignment
            previous_assignment.is_active = False
            previous_assignment.end_date = date.today()
            previous_assignment.ended_by = 'System (Year Transition)'
            previous_assignment.end_reason = 'Academic year transition'
            
            # Create new assignment
            new_assignment = StudentShiurAssignment(
                student_id=student.id,
                shiur_id=new_shiur.id,
                start_date=academic_year.start_date,
                assigned_by='System (Auto-Progression)',
                assignment_reason=f'Automatic assignment from prior year shiur: {previous_shiur.name}'
            )
            
            db.session.add(new_assignment)
            
            return {
                'success': True,
                'previous_shiur': previous_shiur.name,
                'new_shiur': new_shiur.name,
                'message': f'Assigned to {new_shiur.name} (continuation from previous year)'
            }
            
        except Exception as e:
            self.logger.error(f"Error assigning prior year shiur: {str(e)}")
            return {'success': False, 'reason': f'Error: {str(e)}'}
    
    def _assign_prior_year_bed(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Assign student to their prior year bed if available"""
        try:
            # Find student's current/previous bed assignment
            previous_assignment = BedAssignment.get_current_assignment_for_student(student.id)
            
            if not previous_assignment:
                return {'success': False, 'reason': 'No previous bed assignment found'}
            
            previous_bed = previous_assignment.bed
            
            # Check if the same bed is available (not occupied by another student)
            current_occupant = BedAssignment.query.filter_by(
                bed_id=previous_bed.id,
                is_active=True
            ).filter(BedAssignment.student_id != student.id).first()
            
            if current_occupant:
                return {'success': False, 'reason': f'Bed {previous_bed.full_bed_name} is occupied by another student'}
            
            # Check if bed is still available for assignments
            if not previous_bed.allows_assignments or not previous_bed.is_active:
                return {'success': False, 'reason': f'Bed {previous_bed.full_bed_name} is no longer available'}
            
            # End previous assignment
            previous_assignment.is_active = False
            previous_assignment.end_date = date.today()
            previous_assignment.ended_by = 'System (Year Transition)'
            previous_assignment.end_reason = 'Academic year transition'
            
            # Create new assignment for the new academic year
            new_assignment = BedAssignment(
                student_id=student.id,
                bed_id=previous_bed.id,
                start_date=academic_year.start_date,
                assigned_by='System (Auto-Progression)',
                notes=f'Automatic re-assignment from prior year (continued from {previous_assignment.start_date})'
            )
            
            db.session.add(new_assignment)
            
            return {
                'success': True,
                'bed_name': previous_bed.full_bed_name,
                'message': f'Re-assigned to {previous_bed.full_bed_name} (continuation from previous year)'
            }
            
        except Exception as e:
            self.logger.error(f"Error assigning prior year bed: {str(e)}")
            return {'success': False, 'reason': f'Error: {str(e)}'}
    
    def _advance_college_program_level_new_year(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Advance student's college program levels automatically for new academic year"""
        try:
            if student.college_program_status != 'Enrolled':
                return {'success': False, 'reason': 'Student is not enrolled in college program'}
            
            # Get previous academic year
            previous_year = AcademicYear.query.filter(
                AcademicYear.start_date < academic_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            # Store current levels for comparison
            prev_fall_level = student.college_program_fall_level or 0
            prev_spring_level = student.college_program_spring_level or 0
            
            if not previous_year:
                # First year - start at Fall Level 1, Spring Level 1
                student.college_program_fall_level = 1
                student.college_program_spring_level = 1
                student.current_semester = 'Fall'
                
                return {
                    'success': True,
                    'message': 'Started college program at Fall Level 1, Spring Level 1',
                    'fall_level': 1,
                    'spring_level': 1,
                    'graduated': False
                }
            
            # Apply automatic advancement logic
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
            
            # Check if graduated
            graduated = student.should_graduate_college
            if graduated:
                student.college_program_status = 'Graduated'
            
            return {
                'success': True,
                'previous_fall_level': prev_fall_level,
                'previous_spring_level': prev_spring_level,
                'fall_level': student.college_program_fall_level,
                'spring_level': student.college_program_spring_level,
                'graduated': graduated,
                'message': f'Advanced from Fall {prev_fall_level}/Spring {prev_spring_level} to Fall {student.college_program_fall_level}/Spring {student.college_program_spring_level}' + 
                          (' - GRADUATED!' if graduated else '')
            }
            
        except Exception as e:
            self.logger.error(f"Error advancing college program levels for new year: {str(e)}")
            return {'success': False, 'reason': f'Error: {str(e)}'}
    
    def _get_previous_semester_level(self, student: Student, previous_year: AcademicYear, semester: str) -> int:
        """Get student's level for specified semester from previous academic year"""
        try:
            # Find enrollment history from previous year to get semester levels
            previous_history = StudentEnrollmentHistory.query.filter_by(
                student_id=student.id,
                academic_year_id=previous_year.id
            ).order_by(StudentEnrollmentHistory.decision_date.desc()).first()
            
            if not previous_history:
                return 0  # Not enrolled in previous year
            
            # If we stored semester levels in metadata, use those
            # Otherwise, try to infer from student's current levels
            if semester == 'Fall':
                return getattr(student, 'college_program_fall_level', 0) or 0
            else:
                return getattr(student, 'college_program_spring_level', 0) or 0
                
        except Exception as e:
            self.logger.error(f"Error getting previous semester level: {str(e)}")
            return 0
    
    def get_progression_preview(self, student_id: str, academic_year_id: int) -> Dict:
        """Get preview of what automatic progression would do for a student"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'error': 'Student not found'}
            
            academic_year = AcademicYear.query.get(academic_year_id)
            if not academic_year:
                return {'success': False, 'error': 'Academic year not found'}
            
            preview = {
                'student_name': student.student_name,
                'current_status': {
                    'enrollment_status': student.enrollment_status_current_year,
                    'college_program_status': student.college_program_status,
                    'college_program_level': student.college_program_level
                },
                'projected_changes': {}
            }
            
            # Preview shiur assignment
            shiur_preview = self._preview_shiur_assignment(student, academic_year)
            preview['projected_changes']['shiur'] = shiur_preview
            
            # Preview bed assignment
            bed_preview = self._preview_bed_assignment(student, academic_year)
            preview['projected_changes']['bed'] = bed_preview
            
            # Preview college program advancement
            college_preview = self._preview_college_advancement_new_year(student, academic_year)
            preview['projected_changes']['college_program'] = college_preview
            
            return {'success': True, 'preview': preview}
            
        except Exception as e:
            self.logger.error(f"Error generating progression preview: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _preview_shiur_assignment(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Preview what shiur assignment would be made"""
        # Find current shiur
        current_assignment = StudentShiurAssignment.query.filter_by(
            student_id=student.id,
            is_active=True
        ).first()
        
        if not current_assignment:
            return {'action': 'none', 'reason': 'No current shiur assignment'}
        
        current_shiur = current_assignment.shiur
        
        # Look for equivalent in new year
        new_shiur = Shiur.query.filter_by(
            academic_year_id=academic_year.id,
            name=current_shiur.name,
            instructor_name=current_shiur.instructor_name,
            division=student.division,
            is_active=True
        ).first()
        
        if new_shiur:
            return {
                'action': 'assign',
                'current_shiur': current_shiur.name,
                'new_shiur': new_shiur.name,
                'instructor': new_shiur.instructor_name
            }
        else:
            return {
                'action': 'none',
                'reason': f'No equivalent shiur found for {current_shiur.name}',
                'current_shiur': current_shiur.name
            }
    
    def _preview_bed_assignment(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Preview what bed assignment would be made"""
        current_assignment = BedAssignment.get_current_assignment_for_student(student.id)
        
        if not current_assignment:
            return {'action': 'none', 'reason': 'No current bed assignment'}
        
        current_bed = current_assignment.bed
        
        # Check if bed is available
        if current_bed.allows_assignments and current_bed.is_active:
            return {
                'action': 'assign',
                'bed_name': current_bed.full_bed_name,
                'room': current_bed.room.full_room_name,
                'dormitory': current_bed.room.dormitory.name
            }
        else:
            return {
                'action': 'none',
                'reason': f'Bed {current_bed.full_bed_name} is no longer available',
                'current_bed': current_bed.full_bed_name
            }
    
    def _preview_college_advancement_new_year(self, student: Student, academic_year: AcademicYear) -> Dict:
        """Preview college program level advancement for new academic year"""
        if student.college_program_status != 'Enrolled':
            return {'action': 'none', 'reason': 'Not enrolled in college program'}
        
        # Get previous year
        previous_year = AcademicYear.query.filter(
            AcademicYear.start_date < academic_year.start_date
        ).order_by(AcademicYear.start_date.desc()).first()
        
        # Current levels
        prev_fall_level = student.college_program_fall_level or 0
        prev_spring_level = student.college_program_spring_level or 0
        
        if not previous_year:
            # First year - start at Level 1 for both
            projected_fall = 1
            projected_spring = 1
        else:
            # Apply advancement logic
            if prev_fall_level > 0 and prev_spring_level > 0:
                # Student completed both semesters - advance both by 1
                projected_fall = min(prev_fall_level + 1, 5)
                projected_spring = min(prev_spring_level + 1, 5)
            elif prev_fall_level > 0 and prev_spring_level == 0:
                # Student only did Fall semester - advance Fall by 1, start Spring at 1
                projected_fall = min(prev_fall_level + 1, 5)
                projected_spring = 1
            elif prev_fall_level == 0 and prev_spring_level > 0:
                # Student only did Spring semester (started in spring) - keep Fall at 1, advance Spring
                projected_fall = 1
                projected_spring = min(prev_spring_level + 1, 5)
            else:
                # No previous levels - start at Level 1 for both
                projected_fall = 1
                projected_spring = 1
        
        will_graduate = (projected_fall >= 5 and projected_spring >= 5)
        
        return {
            'action': 'advance',
            'previous_fall_level': prev_fall_level,
            'previous_spring_level': prev_spring_level,
            'projected_fall_level': projected_fall,
            'projected_spring_level': projected_spring,
            'graduation': will_graduate,
            'message': f'Fall {prev_fall_level} → {projected_fall}, Spring {prev_spring_level} → {projected_spring}' + 
                      (' (GRADUATION!)' if will_graduate else '')
        } 