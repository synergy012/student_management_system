from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import Student, TuitionRecord, AcademicYear, db, FinancialRecord
from utils.decorators import permission_required
from datetime import datetime
import traceback

financial_core = Blueprint('financial_core', __name__)

@financial_core.route('/financial-debug')
@login_required
def financial_debug():
    """Debug route to test financial blueprint and logging"""
    current_app.logger.info(f"Financial debug accessed by user: {current_user.username}")
    current_app.logger.info(f"User permissions: {[p.name for p in current_user.permissions]}")
    
    # Test database connection
    try:
        academic_years = AcademicYear.query.count()
        financial_records = FinancialRecord.query.count()
        students = Student.query.count()
        current_app.logger.info(f"Database counts - Academic years: {academic_years}, Financial records: {financial_records}, Students: {students}")
        
        return f"""
        <h1>Financial Debug</h1>
        <p>User: {current_user.username}</p>
        <p>Permissions: {[p.name for p in current_user.permissions]}</p>
        <p>Academic Years: {academic_years}</p>
        <p>Financial Records: {financial_records}</p>
        <p>Students: {students}</p>
        <p>Check logs for detailed information</p>
        """
    except Exception as e:
        current_app.logger.error(f"Error in financial debug: {str(e)}")
        return f"Error: {str(e)}"

@financial_core.route('/financial-test')
@login_required
def financial_test():
    """Simple test route to check if financial blueprint is working"""
    return f"Financial test route working! User: {current_user.username}, Permissions: {[p.name for p in current_user.permissions]}"

@financial_core.route('/financial')
@login_required  
@permission_required('view_students')
def financial_dashboard():
    """Main financial dashboard."""
    current_app.logger.info(f"Financial dashboard accessed by user: {current_user.username}")
    
    try:
        # Get filter parameters
        division = request.args.get('division', '')
        academic_year_id = request.args.get('academic_year', '')
        status_filter = request.args.get('status', '')
        
        # Get available academic years
        academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        # Get current academic year as default
        current_academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not current_academic_year:
            current_academic_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
        
        # Use selected year or default to current
        selected_year_id = academic_year_id if academic_year_id else (current_academic_year.id if current_academic_year else None)
        
        # Get base query for students
        students_query = Student.query
        
        # Apply filters
        if division:
            students_query = students_query.filter_by(division=division)
        if status_filter:
            students_query = students_query.filter_by(status=status_filter)
        
        students = students_query.all()
        
        # Get financial records for selected year
        financial_records = []
        if selected_year_id:
            financial_records = FinancialRecord.query.filter_by(academic_year_id=selected_year_id).all()
        
        # Calculate summary statistics
        total_students = len(students)
        total_tuition = sum(record.tuition_amount or 0 for record in financial_records)
        total_paid = sum(record.total_paid or 0 for record in financial_records)
        total_balance = total_tuition - total_paid
        
        # Get unique divisions for filter
        divisions = db.session.query(Student.division).distinct().filter(Student.division.isnot(None)).all()
        divisions = [d[0] for d in divisions if d[0]]
        
        # Get unique statuses for filter
        statuses = db.session.query(Student.status).distinct().filter(Student.status.isnot(None)).all()
        statuses = [s[0] for s in statuses if s[0]]
        
        return render_template('financial_dashboard.html',
                             students=students,
                             financial_records=financial_records,
                             academic_years=academic_years,
                             selected_year_id=int(selected_year_id) if selected_year_id else None,
                             divisions=divisions,
                             statuses=statuses,
                             filters={
                                 'division': division,
                                 'academic_year': academic_year_id,
                                 'status': status_filter
                             },
                             summary={
                                 'total_students': total_students,
                                 'total_tuition': total_tuition,
                                 'total_paid': total_paid,
                                 'total_balance': total_balance
                             })
    except Exception as e:
        current_app.logger.error(f"Error in financial dashboard: {str(e)}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('500.html', error=str(e)), 500

@financial_core.route('/students/<student_id>/financial')
@login_required
@permission_required('edit_students')
def student_financial(student_id):
    """Display student financial information."""
    current_app.logger.info(f"Accessing student financial page for student_id: {student_id}")
    current_app.logger.info(f"User: {current_user.username}, Permissions: {[p.name for p in current_user.permissions]}")
    
    try:
        student = Student.query.filter_by(id=student_id).first()
        current_app.logger.info(f"Student found: {student is not None}")
        
        if not student:
            current_app.logger.warning(f"Student not found with ID: {student_id}")
            return render_template('404.html', message="Student not found"), 404
        
        # Handle potential UTF-8 encoding issues in student data
        try:
            # Safely access student attributes with encoding handling
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            student_email = student.email or ""
            student_phone = student.phone_number or ""
            student_division = student.division or ""
            current_app.logger.info(f"Student data processed: {student_name}, {student_email}, {student_division}")
        except UnicodeDecodeError as e:
            current_app.logger.error(f"Unicode decode error for student {student_id}: {str(e)}")
            # Provide fallback values
            student_name = f"Student {student_id[:8]}"
            student_email = ""
            student_phone = ""
            student_division = ""
        
        # Get all academic years for the selector
        try:
            academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
            current_app.logger.info(f"Found {len(academic_years)} academic years")
        except Exception as e:
            current_app.logger.error(f"Error loading academic years: {str(e)}")
            academic_years = []
        
        # Get current/active academic year as default selected year
        selected_year = None
        try:
            selected_year = AcademicYear.query.filter_by(is_active=True).first()
            if not selected_year:
                # Fallback to most recent year if no active year
                selected_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
            current_app.logger.info(f"Selected year: {selected_year.year_label if selected_year else 'None'}")
        except Exception as e:
            current_app.logger.error(f"Error loading selected year: {str(e)}")
        
        # Get tuition record for selected year
        tuition_record = None
        if selected_year:
            try:
                tuition_record = TuitionRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=selected_year.id
                ).first()
                current_app.logger.info(f"Tuition record found: {tuition_record is not None}")
            except Exception as e:
                current_app.logger.error(f"Error loading tuition record: {str(e)}")
        
        # Get tuition history (all records for this student)
        tuition_history = []
        try:
            tuition_history = TuitionRecord.query.filter_by(student_id=student_id).order_by(TuitionRecord.academic_year_id.desc()).all()
            current_app.logger.info(f"Found {len(tuition_history)} tuition history records")
        except Exception as e:
            current_app.logger.error(f"Error loading tuition history: {str(e)}")
        
        # Calculate totals with error handling
        total_tuition = 0
        total_paid = 0
        try:
            total_tuition = sum(record.tuition_amount for record in tuition_history if record.tuition_amount)
            total_paid = sum(record.amount_paid for record in tuition_history if record.amount_paid)
            current_app.logger.info(f"Calculated totals: tuition={total_tuition}, paid={total_paid}")
        except Exception as e:
            current_app.logger.error(f"Error calculating totals: {str(e)}")
        
        total_balance = total_tuition - total_paid
        
        # Create a safe student object for the template
        safe_student = type('SafeStudent', (), {
            'id': student.id,
            'student_name': student_name,
            'email': student_email,
            'phone_number': student_phone,
            'division': student_division,
            'status': getattr(student, 'status', 'Unknown'),
            'status_color': getattr(student, 'status_color', 'secondary')
        })()
        
        # Convert selected_year to JSON-serializable format for template
        selected_year_dict = None
        if selected_year:
            selected_year_dict = {
                'id': selected_year.id,
                'year_label': selected_year.year_label,
                'is_active': selected_year.is_active,
                'is_current': selected_year.is_current,
                'status_color': getattr(selected_year, 'status_color', 'secondary'),
                'status_badge': getattr(selected_year, 'status_badge', 'Unknown')
            }
        
        current_app.logger.info("Rendering student_financial.html template")
        return render_template('student_financial.html',
                             student=safe_student,
                             academic_years=academic_years,
                             selected_year=selected_year_dict,
                             tuition_record=tuition_record,
                             tuition_history=tuition_history,
                             total_tuition=total_tuition,
                             total_paid=total_paid,
                             total_balance=total_balance)
    
    except Exception as e:
        current_app.logger.error(f"Error in student_financial view: {str(e)}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('500.html', error=str(e)), 500 

@financial_core.route('/api/financial/records/<int:record_id>')
@login_required
@permission_required('view_students')
def get_financial_record(record_id):
    """Get financial record details"""
    try:
        record = FinancialRecord.query.get(record_id)
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        return jsonify({
            'id': record.id,
            'fafsa_status': record.fafsa_status,
            'fafsa_submission_date': record.fafsa_submission_date.isoformat() if record.fafsa_submission_date else None,
            'pell_grant_eligible': record.pell_grant_eligible,
            'pell_grant_amount': float(record.pell_grant_amount) if record.pell_grant_amount else 0
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@financial_core.route('/api/financial/records/<int:record_id>/mark-admire-setup', methods=['POST'])
@login_required
@permission_required('edit_students')
def mark_admire_setup(record_id):
    """Mark Admire billing system as setup"""
    try:
        data = request.get_json()
        record = FinancialRecord.query.get(record_id)
        
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        record.admire_charges_setup = True
        record.admire_charges_setup_date = datetime.utcnow()
        record.admire_account_number = data.get('account_number')
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Admire charges marked as setup'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500 