from flask import Blueprint, render_template, request, jsonify, send_file, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Student, TuitionRecord, AcademicYear, db, FinancialRecord, FinancialDocument, FinancialAidApplication, DivisionFinancialConfig, StudentTuitionComponent, TuitionComponent, DivisionTuitionComponent, StudentYearlyTracking, DivisionConfig, TuitionContract, Application, EmailTemplate, FormUploadLog, SecureFormLink
from utils.decorators import permission_required
from utils.helpers import parse_decimal
from datetime import datetime, date, timedelta
from decimal import Decimal
import os
from werkzeug.utils import secure_filename
import hashlib
from email_service import EmailService
import json
import traceback

financial = Blueprint('financial', __name__)

@financial.route('/financial-debug')
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

@financial.route('/financial-test')
@login_required
def financial_test():
    """Simple test route to check if financial blueprint is working"""
    return f"Financial test route working! User: {current_user.username}, Permissions: {[p.name for p in current_user.permissions]}"

def determine_tuition_type(components, total_amount):
    """
    Automatically determine tuition type based on components and payment amount
    
    Logic:
    - Full Scholarship: Student pays $0 (total_amount = 0)
    - Full Tuition: Student pays full amount for all active components (no discounts applied)
    - Reduced Tuition: Student has discounts applied but still pays something
    """
    if total_amount == 0:
        return 'Full Scholarship'
    
    # Check if any discounts were applied
    has_discounts = False
    total_original_amount = 0
    
    for comp_data in components:
        if comp_data.get('is_enabled', True):  # Only check active components
            original_amount = float(comp_data.get('amount', 0))
            final_amount = float(comp_data.get('final_amount', 0))
            discount_percentage = float(comp_data.get('discount_percentage', 0))
            
            total_original_amount += original_amount
            
            # Check if there's any discount applied
            if discount_percentage > 0 or final_amount < original_amount:
                has_discounts = True
    
    # If no discounts were applied, it's full tuition
    if not has_discounts:
        return 'Full Tuition'
    else:
        return 'Reduced Tuition'

@financial.route('/students/<student_id>/financial')
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
        current_app.logger.error(f"Error loading financial info for student {student_id}: {str(e)}")
        current_app.logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('404.html', message="Error loading financial information"), 500

@financial.route('/api/students/<student_id>/update-financial', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_student_financial(student_id):
    """Update student financial information."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        
        # Update financial fields
        if 'tuition_amount' in data:
            student.tuition_amount = parse_decimal(data['tuition_amount'])
        
        if 'tuition_amount_paid' in data:
            student.tuition_amount_paid = parse_decimal(data['tuition_amount_paid'])
        
        if 'scholarship_amount' in data:
            student.scholarship_amount = parse_decimal(data['scholarship_amount'])
        
        if 'tuition_payment_plan' in data:
            student.tuition_payment_plan = data['tuition_payment_plan']
        
        if 'financial_aid_status' in data:
            student.financial_aid_status = data['financial_aid_status']
        
        if 'tuition_notes' in data:
            student.tuition_notes = data['tuition_notes']
        
        # Update tuition record for current year if exists
        if 'current_year_id' in data and 'current_year_amount' in data:
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=data['current_year_id']
            ).first()
            
            if tuition_record:
                tuition_record.tuition_amount = parse_decimal(data['current_year_amount'])
                if 'current_year_paid' in data:
                    tuition_record.amount_paid = parse_decimal(data['current_year_paid'])
                if 'current_year_plan' in data:
                    tuition_record.payment_plan = data['current_year_plan']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Financial information updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating financial info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/change-academic-year', methods=['POST'])
@login_required
@permission_required('edit_students')
def change_academic_year(student_id):
    """Change the selected academic year for student financial view."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        # Get the selected academic year
        selected_year = AcademicYear.query.filter_by(id=academic_year_id).first()
        if not selected_year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        # Get tuition record for the selected year
        tuition_record = None
        try:
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition record for year change: {str(e)}")
        
        # Get tuition history
        tuition_history = []
        try:
            tuition_history = TuitionRecord.query.filter_by(student_id=student_id).order_by(TuitionRecord.academic_year_id.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition history for year change: {str(e)}")
        
        # Calculate totals with error handling
        total_tuition = 0
        total_paid = 0
        try:
            total_tuition = sum(record.tuition_amount for record in tuition_history if record.tuition_amount)
            total_paid = sum(record.amount_paid for record in tuition_history if record.amount_paid)
        except Exception as e:
            current_app.logger.error(f"Error calculating totals for year change: {str(e)}")
        
        total_balance = total_tuition - total_paid
        
        # Safely build the response with error handling
        try:
            response_data = {
                'success': True,
                'selected_year': {
                    'id': selected_year.id,
                    'year_label': selected_year.year_label,
                    'is_active': selected_year.is_active,
                    'is_current': selected_year.is_current,
                    'status_color': getattr(selected_year, 'status_color', 'secondary'),
                    'status_badge': getattr(selected_year, 'status_badge', 'Unknown')
                },
                'tuition_record': None,
                'tuition_history': [],
                'totals': {
                    'total_tuition': float(total_tuition),
                    'total_paid': float(total_paid),
                    'total_balance': float(total_balance)
                }
            }
            
            # Safely add tuition record data
            if tuition_record:
                try:
                    response_data['tuition_record'] = {
                        'id': tuition_record.id,
                        'tuition_determination': float(tuition_record.tuition_determination) if tuition_record.tuition_determination else None,
                        'tuition_determination_notes': tuition_record.tuition_determination_notes if tuition_record else None,
                        'financial_aid_type': tuition_record.financial_aid_type if tuition_record else None,
                        'financial_aid_app_sent': tuition_record.financial_aid_app_sent if tuition_record else False,
                        'financial_aid_app_received': tuition_record.financial_aid_app_received if tuition_record else False,
                        'contract_status': tuition_record.contract_status if tuition_record else None,
                        'payment_status': tuition_record.payment_status if tuition_record else None,
                        'payment_plan': tuition_record.payment_plan if tuition_record else None,
                        'amount_paid': float(tuition_record.amount_paid) if tuition_record and tuition_record.amount_paid else 0,
                        'opensign_document_id': tuition_record.opensign_document_id if tuition_record else None
                    }
                except Exception as e:
                    current_app.logger.error(f"Error processing tuition record data: {str(e)}")
                    response_data['tuition_record'] = None
            
            # Safely add tuition history data
            try:
                response_data['tuition_history'] = [
                    {
                        'academic_year_id': record.academic_year_id,
                        'academic_year': {
                            'year_label': record.academic_year.year_label if record.academic_year else 'Unknown',
                            'status_color': getattr(record.academic_year, 'status_color', 'secondary') if record.academic_year else 'secondary',
                            'status_badge': getattr(record.academic_year, 'status_badge', 'Unknown') if record.academic_year else 'Unknown'
                        },
                        'tuition_determination': float(record.tuition_determination) if record.tuition_determination else None,
                        'contract_status': record.contract_status or 'Unknown',
                        'payment_status': record.payment_status or 'Unknown',
                        'payment_status_color': getattr(record, 'payment_status_color', 'secondary'),
                        'matriculation_status_for_year': getattr(record, 'matriculation_status_for_year', None)
                    } 
                    for record in tuition_history
                ]
            except Exception as e:
                current_app.logger.error(f"Error processing tuition history data: {str(e)}")
                response_data['tuition_history'] = []
            
            return jsonify(response_data)
            
        except Exception as e:
            current_app.logger.error(f"Error building response data: {str(e)}")
            return jsonify({'error': 'Error processing data'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error changing academic year for student {student_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/financial-action', methods=['POST'])
@login_required
@permission_required('edit_students')
def student_financial_action(student_id):
    """Handle financial actions like payments, adjustments, etc."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        action = data.get('action')
        
        if action == 'record_payment':
            amount = parse_decimal(data.get('amount', 0))
            payment_date = datetime.strptime(data['payment_date'], '%Y-%m-%d').date()
            payment_method = data.get('payment_method', 'Cash')
            notes = data.get('notes', '')
            
            # Update student's total paid
            student.tuition_amount_paid = (student.tuition_amount_paid or Decimal('0')) + amount
            
            # Update current year's record if specified
            if 'academic_year_id' in data:
                tuition_record = TuitionRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=data['academic_year_id']
                ).first()
                
                if tuition_record:
                    tuition_record.amount_paid = (tuition_record.amount_paid or Decimal('0')) + amount
                    tuition_record.last_payment_date = payment_date
            
            # TODO: Create payment record in payment history table
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Payment of ${amount} recorded successfully'
            })
        
        elif action == 'apply_scholarship':
            amount = parse_decimal(data.get('amount', 0))
            reason = data.get('reason', '')
            
            student.scholarship_amount = (student.scholarship_amount or Decimal('0')) + amount
            
            # TODO: Create scholarship record
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Scholarship of ${amount} applied successfully'
            })
        
        else:
            return jsonify({'error': 'Invalid action'}), 400
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error processing financial action: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/generate-tuition-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_tuition_contract(student_id):
    """Generate a tuition contract PDF for the student."""
    try:
        current_app.logger.info(f"Starting contract generation for student: {student_id}")
        
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            current_app.logger.error(f"Student not found: {student_id}")
            return jsonify({'error': 'Student not found'}), 404
        
        current_app.logger.info(f"Found student: {student.student_name}, Division: {student.division}")
        
        data = request.get_json()
        current_app.logger.info(f"Request data: {data}")
        
        # Get current academic year
        year = AcademicYear.query.filter_by(is_active=True).first()
        if not year:
            current_app.logger.error("No active academic year found")
            return jsonify({'error': 'No active academic year found'}), 400
        
        current_app.logger.info(f"Active academic year: {year.year_label}")
        
        # Generate contract using PDF service
        current_app.logger.info("Importing PDFService...")
        from pdf_service import PDFService
        current_app.logger.info("PDFService imported successfully")

        # Get division config for the student's division
        current_app.logger.info(f"Getting division config for: {student.division}")
        division_config = DivisionConfig.query.filter_by(division=student.division).first()
        current_app.logger.info(f"Division config found: {division_config is not None}")
        
        # Generate PDF content
        current_app.logger.info("Generating PDF content...")
        pdf_content = PDFService.generate_tuition_contract_pdf(student, division_config)
        current_app.logger.info(f"PDF content generated, size: {len(pdf_content)} bytes")
        
        # Save PDF to file
        import os
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Generate filename
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"tuition_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Save PDF to file
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        
        # Get or create tuition record for the current academic year
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=year.id
        ).first()
        
        if not tuition_record:
            # Create a new tuition record
            tuition_record = TuitionRecord(
                student_id=student_id,
                academic_year_id=year.id
            )
            db.session.add(tuition_record)
        
        # Update tuition record
        tuition_record.tuition_contract_generated = True
        tuition_record.tuition_contract_generated_date = datetime.utcnow()
        tuition_record.tuition_contract_pdf_path = pdf_path
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition contract generated successfully',
            'contract_path': pdf_path
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating tuition contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/tuition-contract/download')
@login_required
@permission_required('view_students')
def download_tuition_contract(student_id):
    """Download the student's tuition contract."""
    try:
        # Get the current academic year
        year = AcademicYear.query.filter_by(is_active=True).first()
        if not year:
            return jsonify({'error': 'No active academic year found'}), 404
        
        # Get the tuition record for this student and academic year
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=year.id
        ).first()
        
        if not tuition_record or not tuition_record.tuition_contract_pdf_path:
            return jsonify({'error': 'No tuition contract found'}), 404
        
        if not os.path.exists(tuition_record.tuition_contract_pdf_path):
            return jsonify({'error': 'Contract file not found on disk'}), 404
        
        return send_file(
            tuition_record.tuition_contract_pdf_path,
            as_attachment=True,
            download_name=f'tuition_contract_{student_id}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading tuition contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/opensign-status', methods=['GET'])
@login_required
@permission_required('view_students')
def get_opensign_status(student_id):
    """Get OpenSign document status for the student."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get the current academic year
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not academic_year:
            return jsonify({'error': 'No active academic year found'}), 404
        
        # Get financial record for current contract status
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id
        ).first()
        
        if not financial_record:
            return jsonify({
                'has_contract': False,
                'contract_sent': False,
                'contract_signed': False,
                'signed_date': None,
                'document_id': None,
                'signed_url': None
            })
        
        # Check for uploaded contract (print & upload method)
        uploaded_contract = FormUploadLog.query.join(
            SecureFormLink, FormUploadLog.secure_link_id == SecureFormLink.id
        ).filter(
            FormUploadLog.student_id == student_id,
            SecureFormLink.form_type == 'tuition_contract',
            FormUploadLog.processing_status == 'processed'
        ).order_by(FormUploadLog.uploaded_at.desc()).first()
        
        status = {
            'has_contract': financial_record.enhanced_contract_generated,
            'contract_sent': financial_record.enhanced_contract_sent,
            'contract_signed': financial_record.enhanced_contract_signed,
            'signed_date': financial_record.enhanced_contract_signed_date.isoformat() if financial_record.enhanced_contract_signed_date else None,
            'document_id': student.opensign_document_id,
            'signed_url': student.opensign_signed_url,
            'document_url': student.opensign_certificate_url,  # Correct field name
            'uploaded_contract': bool(uploaded_contract)
        }
        
        # Add uploaded contract details if found
        if uploaded_contract:
            status.update({
                'uploaded_contract_id': uploaded_contract.id,
                'uploaded_contract_filename': uploaded_contract.original_filename,
                'uploaded_contract_date': uploaded_contract.uploaded_at.strftime('%B %d, %Y at %I:%M %p') if uploaded_contract.uploaded_at else None,
                'uploaded_contract_url': f'/students/{student_id}/view-uploaded-contract'  # URL to view the uploaded contract
            })
        
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.error(f"Error getting OpenSign status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/resend-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def resend_contract(student_id):
    """Resend the tuition contract for signing."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not student.tuition_contract_path:
            return jsonify({'error': 'No contract generated yet'}), 400
        
        # TODO: Implement OpenSign integration
        # For now, just simulate sending
        student.opensign_document_id = f"doc_{student_id}_{datetime.utcnow().timestamp()}"
        student.tuition_contract_sent_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract resent successfully',
            'document_id': student.opensign_document_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resending contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/financial')
@login_required  
@permission_required('view_students')
def financial_dashboard():
    """Main financial management dashboard"""
    try:
        current_app.logger.info(f"Financial dashboard accessed by user: {current_user.username}")
        
        # Get academic year parameter
        academic_year_param = request.args.get('academic_year_id')
        current_app.logger.info(f"Academic year param: {academic_year_param}")
        
        # If academic_year_param is provided, use that specific year
        selected_academic_year = None
        if academic_year_param:
            try:
                academic_year_id = int(academic_year_param)
                selected_academic_year = AcademicYear.query.get(academic_year_id)
                current_app.logger.info(f"Selected academic year from param: {selected_academic_year}")
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Error parsing academic year param: {e}")
                pass
        
        # If no specific year selected, use the active academic year
        if not selected_academic_year:
            selected_academic_year = AcademicYear.query.filter_by(is_active=True).first()
            current_app.logger.info(f"Active academic year: {selected_academic_year}")
        
        # Get all available academic years for dropdown
        available_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        current_app.logger.info(f"Available academic years count: {len(available_academic_years)}")
        
        # Get financial records for the selected academic year
        if selected_academic_year:
            current_app.logger.info(f"Querying financial records for year: {selected_academic_year.id}")
            financial_records = FinancialRecord.query.filter_by(
                academic_year_id=selected_academic_year.id
            ).join(Student).order_by(Student.student_name).all()
            current_app.logger.info(f"Found {len(financial_records)} financial records")
        else:
            financial_records = []
            current_app.logger.warning("No academic year selected, using empty financial records")
        
        # Enhance financial records with tuition component information
        current_app.logger.info("Starting to enhance financial records with tuition components")
        for i, record in enumerate(financial_records):
            current_app.logger.debug(f"Processing record {i+1}/{len(financial_records)}: student_id={record.student_id}")
            
            # Check if student has tuition set through tuition components
            tuition_record = TuitionRecord.query.filter_by(
                student_id=record.student_id,
                academic_year_id=selected_academic_year.id if selected_academic_year else None
            ).first()
            
            if tuition_record:
                # Student has tuition set through components
                record.tuition_amount = tuition_record.tuition_amount
                record.tuition_type = tuition_record.tuition_type
                record.has_tuition_components = True
                
                # Get component details for display
                components = StudentTuitionComponent.query.filter_by(
                    student_id=record.student_id,
                    academic_year_id=selected_academic_year.id if selected_academic_year else None,
                    is_active=True
                ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
                
                record.tuition_components = []
                for comp in components:
                    record.tuition_components.append({
                        'name': comp.component.name,
                        'amount': comp.amount,
                        'discount_percentage': comp.discount_percentage or 0
                    })
            else:
                # No tuition components, check if tuition is set in financial record
                record.has_tuition_components = False
                record.tuition_components = []
        
        current_app.logger.info("Finished enhancing financial records")
        
        # Calculate statistics
        total_students = len(financial_records)
        fa_forms_pending = sum(1 for r in financial_records if not r.financial_aid_form_received)
        contracts_pending = sum(1 for r in financial_records if not r.enrollment_contract_received)
        
        # Count tuition types
        full_tuition_count = sum(1 for r in financial_records 
                               if hasattr(r, 'tuition_type') and r.tuition_type == 'Full Tuition')
        
        current_app.logger.info(f"Statistics: total={total_students}, fa_pending={fa_forms_pending}, contracts_pending={contracts_pending}, full_tuition={full_tuition_count}")
        
        # Default tuition amount (can be configured)
        default_tuition_amount = 25000
        
        # Convert selected_academic_year to dict for JSON serialization
        selected_academic_year_dict = None
        if selected_academic_year:
            selected_academic_year_dict = {
                'id': selected_academic_year.id,
                'year_label': selected_academic_year.year_label,
                'is_active': selected_academic_year.is_active,
                'start_date': selected_academic_year.start_date.isoformat() if selected_academic_year.start_date else None,
                'end_date': selected_academic_year.end_date.isoformat() if selected_academic_year.end_date else None
            }
        
        current_app.logger.info("About to render template")
        return render_template('financial_dashboard.html',
                             financial_records=financial_records,
                             available_academic_years=available_academic_years,
                             selected_academic_year=selected_academic_year,
                             selected_academic_year_dict=selected_academic_year_dict,
                             total_students=total_students,
                             fa_forms_pending=fa_forms_pending,
                             contracts_pending=contracts_pending,
                             full_tuition_count=full_tuition_count,
                             default_tuition_amount=default_tuition_amount)
                             
    except Exception as e:
        current_app.logger.error(f"Error loading financial dashboard: {str(e)}")
        current_app.logger.error(f"Exception type: {type(e)}")
        current_app.logger.error(f"Exception args: {e.args}")
        import traceback
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        flash('Error loading financial dashboard', 'error')
        return redirect(url_for('core.index'))

@financial.route('/api/students/<student_id>/financial-info')
@login_required
@permission_required('edit_students')
def get_student_financial_info(student_id):
    """Get student financial information for API calls."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Handle potential UTF-8 encoding issues in student data
        try:
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            student_email = student.email or ""
            student_phone = student.phone_number or ""
            student_division = student.division or ""
        except UnicodeDecodeError as e:
            current_app.logger.error(f"Unicode decode error for student {student_id}: {str(e)}")
            student_name = f"Student {student_id[:8]}"
            student_email = ""
            student_phone = ""
            student_division = ""
        
        # Get all academic years
        try:
            academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading academic years: {str(e)}")
            academic_years = []
        
        # Get current/active academic year
        selected_year = None
        try:
            selected_year = AcademicYear.query.filter_by(is_active=True).first()
            if not selected_year:
                selected_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
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
            except Exception as e:
                current_app.logger.error(f"Error loading tuition record: {str(e)}")
        
        # Get tuition history
        tuition_history = []
        try:
            tuition_history = TuitionRecord.query.filter_by(student_id=student_id).order_by(TuitionRecord.academic_year_id.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition history: {str(e)}")
        
        # Calculate totals with error handling
        total_tuition = 0
        total_paid = 0
        try:
            total_tuition = sum(record.tuition_amount for record in tuition_history if record.tuition_amount)
            total_paid = sum(record.amount_paid for record in tuition_history if record.amount_paid)
        except Exception as e:
            current_app.logger.error(f"Error calculating totals: {str(e)}")
        
        total_balance = total_tuition - total_paid
        
        # Safely build the response
        try:
            response_data = {
                'student': {
                    'id': student.id,
                    'student_name': student_name,
                    'email': student_email,
                    'phone_number': student_phone,
                    'division': student_division,
                    'status': getattr(student, 'status', 'Unknown'),
                    'status_color': getattr(student, 'status_color', 'secondary')
                },
                'academic_years': [
                    {
                        'id': year.id,
                        'year_label': year.year_label,
                        'is_active': year.is_active,
                        'is_current': year.is_current,
                        'status_color': getattr(year, 'status_color', 'secondary'),
                        'status_badge': getattr(year, 'status_badge', 'Unknown')
                    } for year in academic_years
                ],
                'selected_year': {
                    'id': selected_year.id,
                    'year_label': selected_year.year_label,
                    'is_active': selected_year.is_active,
                    'is_current': selected_year.is_current,
                    'status_color': getattr(selected_year, 'status_color', 'secondary'),
                    'status_badge': getattr(selected_year, 'status_badge', 'Unknown')
                } if selected_year else None,
                'tuition_record': None,
                'tuition_history': [],
                'totals': {
                    'total_tuition': float(total_tuition),
                    'total_paid': float(total_paid),
                    'total_balance': float(total_balance)
                }
            }
            
            # Safely add tuition record data
            if tuition_record:
                try:
                    response_data['tuition_record'] = {
                        'id': tuition_record.id,
                        'tuition_determination': float(tuition_record.tuition_determination) if tuition_record.tuition_determination else None,
                        'tuition_determination_notes': tuition_record.tuition_determination_notes if tuition_record else None,
                        'financial_aid_type': tuition_record.financial_aid_type if tuition_record else None,
                        'financial_aid_app_sent': tuition_record.financial_aid_app_sent if tuition_record else False,
                        'financial_aid_app_received': tuition_record.financial_aid_app_received if tuition_record else False,
                        'contract_status': tuition_record.contract_status if tuition_record else None,
                        'payment_status': tuition_record.payment_status if tuition_record else None,
                        'payment_plan': tuition_record.payment_plan if tuition_record else None,
                        'amount_paid': float(tuition_record.amount_paid) if tuition_record and tuition_record.amount_paid else 0,
                        'opensign_document_id': tuition_record.opensign_document_id if tuition_record else None
                    }
                except Exception as e:
                    current_app.logger.error(f"Error processing tuition record data: {str(e)}")
                    response_data['tuition_record'] = None
            
            # Safely add tuition history data
            try:
                response_data['tuition_history'] = [
                    {
                        'academic_year_id': record.academic_year_id,
                        'academic_year': {
                            'year_label': record.academic_year.year_label if record.academic_year else 'Unknown',
                            'status_color': getattr(record.academic_year, 'status_color', 'secondary') if record.academic_year else 'secondary',
                            'status_badge': getattr(record.academic_year, 'status_badge', 'Unknown') if record.academic_year else 'Unknown'
                        },
                        'tuition_determination': float(record.tuition_determination) if record.tuition_determination else None,
                        'contract_status': record.contract_status or 'Unknown',
                        'payment_status': record.payment_status or 'Unknown',
                        'payment_status_color': getattr(record, 'payment_status_color', 'secondary'),
                        'matriculation_status_for_year': getattr(record, 'matriculation_status_for_year', None)
                    } 
                    for record in tuition_history
                ]
            except Exception as e:
                current_app.logger.error(f"Error processing tuition history data: {str(e)}")
                response_data['tuition_history'] = []
            
            return jsonify(response_data)
            
        except Exception as e:
            current_app.logger.error(f"Error building response data: {str(e)}")
            return jsonify({'error': 'Error processing data'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error loading financial info for student {student_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/application-defaults')
@login_required
@permission_required('view_students')
def get_application_defaults(student_id):
    """Get defaults based on application and prior year data"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        defaults = {
            'dormitory_requested': False,
            'meals_requested': False,
            'scholarship_amount_requested': 0,
            'base_tuition': 0
        }
        
        # Check application data
        if student.application:
            # Parse dormitory/meals option
            dorm_meals = student.application.dormitory_meals_option or ''
            defaults['dormitory_requested'] = 'dorm' in dorm_meals.lower() or 'room' in dorm_meals.lower()
            defaults['meals_requested'] = 'meal' in dorm_meals.lower() or 'board' in dorm_meals.lower() or 'food' in dorm_meals.lower()
            defaults['scholarship_amount_requested'] = float(student.application.scholarship_amount_requested or 0)
        
        # Get base tuition for division
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if academic_year:
            tuition_component = TuitionComponent.query.filter_by(name='Tuition', is_active=True).first()
            if tuition_component:
                division_config = DivisionTuitionComponent.query.filter_by(
                    division=student.division,
                    component_id=tuition_component.id,
                    academic_year_id=academic_year.id
                ).first()
                
                if division_config:
                    defaults['base_tuition'] = float(division_config.default_amount)
        
        # Check prior year data for returning students
        if academic_year:
            prior_year = AcademicYear.query.filter(
                AcademicYear.start_date < academic_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            if prior_year:
                prior_components = StudentTuitionComponent.query.filter_by(
                    student_id=student_id,
                    academic_year_id=prior_year.id,
                    is_active=True
                ).join(TuitionComponent).all()
                
                for comp in prior_components:
                    if comp.component.component_type == 'room':
                        defaults['dormitory_requested'] = True
                    elif comp.component.component_type == 'board':
                        defaults['meals_requested'] = True
        
        return jsonify({
            'success': True,
            'defaults': defaults,
            'application_preferences': {
                'dormitory_meals_option': student.application.dormitory_meals_option if student.application else None,
                'financial_aid_request': bool(student.application and student.application.scholarship_amount_requested and student.application.scholarship_amount_requested > 0) if student.application else False
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting application defaults: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/tuition-components/save', methods=['POST'])
@login_required
@permission_required('edit_students')
def save_student_tuition_components(student_id):
    """Save student tuition components for the academic year"""
    try:
        data = request.get_json()
        
        # Get academic year from data or current year
        academic_year_id = data.get('academic_year_id')
        if not academic_year_id:
            # Try to get from academic_year field (year number)
            academic_year_year = data.get('academic_year', datetime.now().year)
            academic_year = AcademicYear.query.filter(
                AcademicYear.start_date <= datetime(academic_year_year, 12, 31),
                AcademicYear.end_date >= datetime(academic_year_year, 1, 1)
            ).first()
            
            if not academic_year:
                academic_year = AcademicYear.query.filter_by(is_active=True).first()
            
            academic_year_id = academic_year.id if academic_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Process each component
        total_amount = 0
        components_summary = []
        dorm_program = False
        meal_program = False
        
        for comp_data in data.get('components', []):
            component_id = comp_data['component_id']
            
            # Get or create student component
            student_comp = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id,
                component_id=component_id
            ).first()
            
            if not student_comp:
                student_comp = StudentTuitionComponent(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    component_id=component_id
                )
                db.session.add(student_comp)
            
            # Update component data  
            student_comp.is_active = comp_data.get('is_enabled', True)
            student_comp.amount = Decimal(str(comp_data.get('amount', 0)))
            student_comp.original_amount = student_comp.amount
            student_comp.discount_percentage = Decimal(str(comp_data.get('discount_percentage', 0)))
            student_comp.updated_by = current_user.username
            
            # Handle proration information  
            proration_percentage = data.get('proration_percentage', 100)
            proration_reason = data.get('proration_reason', '')
            
            # Set proration fields if applicable
            if proration_percentage < 100:
                student_comp.is_prorated = True
                student_comp.proration_percentage = Decimal(str(proration_percentage))
                student_comp.proration_reason = proration_reason
            else:
                student_comp.is_prorated = False
                student_comp.proration_percentage = Decimal('100.00')
                student_comp.proration_reason = ''
            
            # Set discount reason if global discount was applied
            global_discount = data.get('global_discount_percentage', 0)
            if global_discount > 0 and student_comp.discount_percentage > 0:
                student_comp.discount_reason = data.get('global_discount_reason', f'Global {global_discount}% discount applied')
            elif comp_data.get('discount_percentage', 0) > 0 and not student_comp.discount_reason:
                student_comp.discount_reason = 'Individual discount applied'
            
            # Calculate discount amount based on percentage (for reference)
            if student_comp.discount_percentage > 0:
                student_comp.discount_amount = student_comp.amount * (student_comp.discount_percentage / 100)
            else:
                student_comp.discount_amount = Decimal('0')
            
            # Calculate final amount and track components
            final_amount = float(comp_data.get('final_amount', 0))
            if student_comp.is_active:
                total_amount += final_amount
                
                # Track program participation
                component = TuitionComponent.query.get(component_id)
                if component:
                    if component.component_type == 'room':
                        dorm_program = True
                    elif component.component_type == 'board':
                        meal_program = True
                    
                    # Add to components summary
                    components_summary.append({
                        'component_id': component_id,
                        'name': component.name,
                        'component_type': component.component_type,
                        'is_active': True,
                        'original_amount': float(student_comp.original_amount),
                        'discount_percentage': float(student_comp.discount_percentage or 0),
                        'is_prorated': student_comp.is_prorated,
                        'proration_percentage': float(student_comp.proration_percentage or 100),
                        'proration_reason': student_comp.proration_reason or '',
                        'final_amount': final_amount
                    })
        
        # Update or create tuition record
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not tuition_record:
            tuition_record = TuitionRecord(
                student_id=student_id,
                academic_year_id=academic_year_id
            )
            db.session.add(tuition_record)
        
        # Determine tuition type automatically
        tuition_type = determine_tuition_type(data.get('components', []), total_amount)
        
        # Update tuition record
        tuition_record.tuition_determination = Decimal(str(total_amount))
        tuition_record.tuition_amount = Decimal(str(total_amount))
        tuition_record.tuition_type = tuition_type
        tuition_record.updated_by = current_user.username
        tuition_record.updated_at = datetime.utcnow()
        
        # Update student tracking flags
        student.current_year_tuition = Decimal(str(total_amount))
        
        # Also update the FinancialRecord if it exists
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if financial_record:
            financial_record.tuition_type = tuition_type
            financial_record.tuition_amount = Decimal(str(total_amount))
            financial_record.final_tuition_amount = Decimal(str(total_amount))
        
        # Create or update yearly tracking record
        yearly_tracking = StudentYearlyTracking.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not yearly_tracking:
            yearly_tracking = StudentYearlyTracking(
                student_id=student_id,
                academic_year_id=academic_year_id
            )
            db.session.add(yearly_tracking)
        
        # Update tracking data
        yearly_tracking.dorm_program_status = data.get('dorm_program_this_year', dorm_program)
        yearly_tracking.meal_program_status = data.get('meal_program_this_year', meal_program) 
        yearly_tracking.total_tuition_charged = Decimal(str(total_amount))
        yearly_tracking.tuition_components_summary = components_summary
        yearly_tracking.fafsa_required = data.get('fafsa_required', False)
        yearly_tracking.updated_by = current_user.username
        yearly_tracking.updated_at = datetime.utcnow()
        
        # Check if tuition changes require contract regeneration
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if financial_record and financial_record.enhanced_contract_generated:
            current_hash = financial_record.generate_tuition_hash()
            if current_hash != financial_record.contract_generation_hash:
                financial_record.mark_contract_outdated("Tuition components updated")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition components saved successfully',
            'total_amount': total_amount,
            'tuition_type': tuition_type,
            'record_id': tuition_record.id,
            'tracking_id': yearly_tracking.id,
            'program_summary': yearly_tracking.program_summary,
            'contract_status': financial_record.get_contract_status() if financial_record else 'not_generated'
        })
        
    except Exception as e:
        db.session.rollback()
        error_message = str(e)
        current_app.logger.error(f"Error saving tuition components: {error_message}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': error_message,
            'message': f'Failed to save tuition components: {error_message}'
        }), 500

@financial.route('/api/financial/students/<student_id>/set-tuition', methods=['POST'])
@login_required
@permission_required('edit_students')
def set_student_tuition(student_id):
    """Set tuition for a student for the current academic year"""
    try:
        data = request.get_json()
        
        # Get academic year
        academic_year_id = data.get('academic_year_id') or request.args.get('academic_year_id')
        if not academic_year_id:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = academic_year.id if academic_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        # Get or create financial record
        record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not record:
            record = FinancialRecord(
                student_id=student_id,
                academic_year_id=academic_year_id,
                created_by=current_user.username
            )
            db.session.add(record)
        
        # Update tuition information
        record.tuition_type = data.get('tuition_type', 'Full')
        record.tuition_amount = Decimal(str(data.get('tuition_amount', 0)))
        record.discount_percentage = int(data.get('discount_percentage', 0))
        record.discount_reason = data.get('discount_reason')
        record.final_tuition_amount = Decimal(str(data.get('final_tuition_amount', 0)))
        record.fafsa_required = data.get('fafsa_required', False)
        record.updated_by = current_user.username
        record.updated_at = datetime.utcnow()
        
        # Calculate balance
        record.calculate_balance()
        
        # Check if tuition changes require contract regeneration
        if record.enhanced_contract_generated:
            current_hash = record.generate_tuition_hash()
            if current_hash != record.contract_generation_hash:
                record.mark_contract_outdated("Tuition amounts changed")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition set successfully',
            'record_id': record.id,
            'contract_status': record.get_contract_status()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting tuition: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Old financial aid form endpoint removed - now handled by unified system in students blueprint

@financial.route('/api/financial/records/<int:record_id>/mark-fa-received', methods=['POST'])
@login_required
@permission_required('edit_students')
def mark_fa_form_received(record_id):
    """Mark financial aid form as received"""
    try:
        record = FinancialRecord.query.get(record_id)
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        record.financial_aid_form_received = True
        record.financial_aid_form_received_date = datetime.utcnow()
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Financial aid form marked as received'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/students/<student_id>/generate-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_enrollment_contract(student_id):
    """Generate enrollment contract for student using unified contract system"""
    try:
        # Get student to validate
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Prepare data for unified contract generation
        request_data = request.get_json() or {}
        request_data['student_id'] = student_id
        
        # If no specific contract terms provided, use reasonable defaults
        if not request_data.get('total_tuition'):
            # Try to get tuition from student's components
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
            if academic_year:
                student_components = StudentTuitionComponent.query.filter_by(
                    student_id=student_id,
                    academic_year_id=academic_year.id,
                    is_active=True
                ).join(TuitionComponent).all()
                
                total_tuition = sum(float(comp.calculated_amount) for comp in student_components) if student_components else 0
                request_data['total_tuition'] = total_tuition
        
        # Set default payment terms if not provided
        current_year = datetime.now().year
        request_data.setdefault('payment_start_month', 8)  # September
        request_data.setdefault('payment_start_year', current_year)
        request_data.setdefault('payment_end_month', 5)    # June
        request_data.setdefault('payment_end_year', current_year + 1)
        request_data.setdefault('registration_fee_option', 'upfront')
        
        # Create a new request with the prepared data
        from flask import Flask
        with current_app.test_request_context('/api/financial/generate-contract', 
                                            method='POST', 
                                            json=request_data):
            return generate_contract()
        
    except Exception as e:
        current_app.logger.error(f"Error in student-specific contract generation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/students/<student_id>/send-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_enrollment_contract(student_id):
    """Send enrollment contract to student using enhanced sending system"""
    try:
        # Get student to validate
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check if contract has been generated
        if not student.tuition_contract_generated:
            return jsonify({'error': 'Contract must be generated before sending'}), 400
        
        # Prepare data for enhanced contract sending
        request_data = request.get_json() or {}
        request_data['student_id'] = student_id
        
        # Set default email recipients if not provided
        if not request_data.get('email_recipients'):
            recipients = []
            if student.email:
                recipients.append(student.email)
            if student.father_email:
                recipients.append(student.father_email)
            if student.mother_email:
                recipients.append(student.mother_email)
            request_data['email_recipients'] = recipients
        
        # Create a new request with the prepared data
        with current_app.test_request_context('/api/financial/send-enhanced-contract', 
                                            method='POST', 
                                            json=request_data):
            return send_enhanced_contract()
        
    except Exception as e:
        current_app.logger.error(f"Error in student-specific contract sending: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/records/<int:record_id>/mark-contract-received', methods=['POST'])
@login_required
@permission_required('edit_students')
def mark_contract_received(record_id):
    """Mark enrollment contract as received"""
    try:
        record = FinancialRecord.query.get(record_id)
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        # Update both legacy and enhanced fields for consistency
        record.enrollment_contract_received = True
        record.enrollment_contract_received_date = datetime.utcnow()
        record.enhanced_contract_signed = True
        record.enhanced_contract_signed_date = datetime.utcnow()
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract marked as received'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/records/<int:record_id>/mark-admire-setup', methods=['POST'])
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

@financial.route('/api/financial/records/<int:record_id>')
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

@financial.route('/api/financial/records/<int:record_id>/update-fafsa', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_fafsa_status(record_id):
    """Update FAFSA status"""
    try:
        data = request.get_json()
        record = FinancialRecord.query.get(record_id)
        
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        record.fafsa_status = data.get('fafsa_status')
        
        if data.get('fafsa_submission_date'):
            record.fafsa_submission_date = datetime.strptime(data['fafsa_submission_date'], '%Y-%m-%d')
        
        record.pell_grant_eligible = data.get('pell_grant_eligible', False)
        record.pell_grant_amount = Decimal(str(data.get('pell_grant_amount', 0)))
        
        if record.pell_grant_eligible and record.pell_grant_amount > 0:
            record.pell_grant_received_date = datetime.utcnow()
        
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'FAFSA status updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/unenroll', methods=['POST'])
@login_required
@permission_required('edit_students')
def unenroll_student(student_id):
    """Unenroll a student (mark as inactive)"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        student.status = 'Inactive'
        student.date_left = date.today()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student unenrolled successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial.route('/divisions/<division>/financial-aid')
@login_required
@permission_required('view_students')
def division_financial_aid(division):
    """Display financial aid applications for a specific division"""
    try:
        # Get academic year
        academic_year_id = request.args.get('academic_year_id')
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if not academic_year:
            flash('No active academic year found', 'error')
            return redirect(url_for('financial.financial_dashboard'))
        
        # Get all applications for this division and year
        applications = FinancialAidApplication.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).order_by(FinancialAidApplication.application_date.desc()).all()
        
        # Get academic years for selector
        all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('financial/division_financial_aid.html',
                             division=division,
                             applications=applications,
                             academic_year=academic_year,
                             all_academic_years=all_academic_years)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division financial aid: {str(e)}")
        flash('Error loading financial aid applications', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial.route('/divisions/<division>/tuition-contracts')
@login_required
@permission_required('view_students')
def division_tuition_contracts(division):
    """Display tuition contracts for a specific division"""
    try:
        # Get academic year
        academic_year_id = request.args.get('academic_year_id')
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if not academic_year:
            flash('No active academic year found', 'error')
            return redirect(url_for('financial.financial_dashboard'))
        
        # Get all contracts for this division and year
        contracts = TuitionContract.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).order_by(TuitionContract.contract_date.desc()).all()
        
        # Get academic years for selector
        all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('financial/division_tuition_contracts.html',
                             division=division,
                             contracts=contracts,
                             academic_year=academic_year,
                             all_academic_years=all_academic_years)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division tuition contracts: {str(e)}")
        flash('Error loading tuition contracts', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial.route('/api/financial-aid/<int:application_id>/update', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_financial_aid_application(application_id):
    """Update a financial aid application"""
    try:
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        
        # Update application fields
        if 'household_income' in data:
            application.household_income = Decimal(str(data['household_income']))
        if 'household_size' in data:
            application.household_size = int(data['household_size'])
        if 'requested_aid_amount' in data:
            application.requested_aid_amount = Decimal(str(data['requested_aid_amount']))
        if 'hardship_explanation' in data:
            application.hardship_explanation = data['hardship_explanation']
        
        # Update status if needed
        if 'application_status' in data:
            application.application_status = data['application_status']
            if data['application_status'] == 'Submitted':
                application.submission_date = datetime.utcnow()
        
        application.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Application updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating financial aid application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/tuition-contracts/<int:contract_id>/generate', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_division_tuition_contract(contract_id):
    """Generate a division-specific tuition contract"""
    try:
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        # Get division config
        config = DivisionFinancialConfig.query.filter_by(division=contract.division).first()
        if not config:
            return jsonify({'error': 'Division configuration not found'}), 400
        
        # Generate contract PDF
        from pdf_service import PDFService
        pdf_service = PDFService()
        
        contract_data = {
            'student': contract.student,
            'academic_year': contract.academic_year,
            'division': contract.division,
            'tuition_amount': float(contract.tuition_amount),
            'final_amount': float(contract.final_tuition_amount),
            'payment_plan': contract.payment_plan,
            'payment_schedule': contract.payment_schedule,
            'contract_terms': contract.contract_terms or config.contract_terms_path,
            'letterhead': config.letterhead_path,
            'logo': config.logo_path
        }
        
        # Generate PDF
        pdf_path = pdf_service.generate_division_contract(contract_data)
        
        # Update contract record
        contract.contract_pdf_path = pdf_path
        contract.contract_status = 'Generated'
        contract.generated_by = current_user.username
        contract.generated_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract generated successfully',
            'pdf_path': pdf_path
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/tuition-contracts/<int:contract_id>/send', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_division_tuition_contract(contract_id):
    """Send a tuition contract for e-signature"""
    try:
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        if not contract.contract_pdf_path:
            return jsonify({'error': 'Contract must be generated first'}), 400
        
        # Get division config
        config = DivisionFinancialConfig.query.filter_by(division=contract.division).first()
        if not config:
            return jsonify({'error': 'Division configuration not found'}), 400
        
        # Send via OpenSign
        from opensign_service import OpenSignService
        opensign = OpenSignService()
        
        signers = []
        if contract.parent1_email:
            signers.append({
                'name': contract.parent1_name,
                'email': contract.parent1_email,
                'role': 'Parent/Guardian 1'
            })
        if contract.parent2_email:
            signers.append({
                'name': contract.parent2_name,
                'email': contract.parent2_email,
                'role': 'Parent/Guardian 2'
            })
        
        result = opensign.send_for_signature(
            document_path=contract.contract_pdf_path,
            signers=signers,
            template_id=config.opensign_template_id,
            folder_id=config.opensign_folder_id
        )
        
        if result.get('success'):
            contract.opensign_document_id = result['document_id']
            contract.opensign_status = 'pending'
            contract.opensign_sent_date = datetime.utcnow()
            contract.contract_status = 'Sent'
            contract.sent_by = current_user.username
            contract.sent_date = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Contract sent for signature successfully',
                'document_id': result['document_id']
            })
        else:
            return jsonify({
                'error': result.get('error', 'Failed to send contract')
            }), 400
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/contract-preview', methods=['POST'])
@login_required
@permission_required('edit_students')
def preview_enhanced_contract():
    """Generate a preview of the enhanced contract with custom terms"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        current_app.logger.info(f"Generating contract preview for student: {student.student_name} (ID: {student_id})")
        
        # Generate enhanced contract terms
        contract_terms = _generate_enhanced_contract_terms(data)
        current_app.logger.info(f"Contract terms generated for preview: {contract_terms}")
        
        # Use the new ContractStructureService for preview
        current_app.logger.info("Using ContractStructureService for preview generation")
        from contract_structure_service import ContractStructureService
        from models import StudentTuitionComponent, TuitionComponent, DivisionTuitionComponent, AcademicYear
        
        pdf_service = ContractStructureService()
        
        # Prepare student data
        student_data = {
            'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
            'division': student.division or 'YZA'
        }
        
        # Get student's actual tuition data from database
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        actual_tuition_data = {'total_tuition': 0, 'registration_fee': 0, 'room_amount': 0, 'board_amount': 0}
        
        if academic_year:
            # Get student's tuition components
            student_components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year.id,
                is_active=True
            ).join(TuitionComponent).all()
            
            # If no student components exist, get division defaults
            if not student_components:
                division_components = db.session.query(DivisionTuitionComponent, TuitionComponent).join(
                    TuitionComponent, DivisionTuitionComponent.component_id == TuitionComponent.id
                ).filter(
                    DivisionTuitionComponent.division == student.division,
                    DivisionTuitionComponent.academic_year_id == academic_year.id,
                    DivisionTuitionComponent.is_enabled == True,
                    TuitionComponent.is_active == True
                ).all()
                
                # Calculate totals from division defaults
                for div_comp, comp in division_components:
                    amount = float(div_comp.default_amount)
                    actual_tuition_data['total_tuition'] += amount
                    
                    if comp.component_type == 'fee' or 'registration' in comp.name.lower():
                        actual_tuition_data['registration_fee'] = amount
                    elif comp.component_type == 'room' or 'room' in comp.name.lower():
                        actual_tuition_data['room_amount'] = amount
                    elif comp.component_type == 'board' or 'board' in comp.name.lower():
                        actual_tuition_data['board_amount'] = amount
            else:
                # Calculate totals from student components
                for comp in student_components:
                    amount = float(comp.calculated_amount)
                    actual_tuition_data['total_tuition'] += amount
                    
                    if comp.component.component_type == 'fee' or 'registration' in comp.component.name.lower():
                        actual_tuition_data['registration_fee'] = amount
                    elif comp.component.component_type == 'room' or 'room' in comp.component.name.lower():
                        actual_tuition_data['room_amount'] = amount
                    elif comp.component.component_type == 'board' or 'board' in comp.component.name.lower():
                        actual_tuition_data['board_amount'] = amount
        
        current_app.logger.info(f"Actual tuition data from database: {actual_tuition_data}")
        
        # Use actual database data if available, otherwise fall back to form data
        total_tuition = actual_tuition_data['total_tuition'] if actual_tuition_data['total_tuition'] > 0 else contract_terms.get('total_tuition', 0)
        registration_fee = actual_tuition_data['registration_fee'] if actual_tuition_data['registration_fee'] > 0 else contract_terms.get('registration_fee', 0)
        room_amount = actual_tuition_data['room_amount']
        board_amount = actual_tuition_data['board_amount']
        
        # Prepare contract data for the preview
        contract_data = {
            'academic_year': f"{contract_terms.get('payment_start_year', 2025)}-{contract_terms.get('payment_start_year', 2025) + 1}",
            'total_tuition': total_tuition,
            'registration_fee': registration_fee,
            'registration_fee_option': contract_terms.get('registration_fee_option', 'upfront'),
            'room_amount': room_amount,
            'board_amount': board_amount,
            'financial_aid_amount': data.get('financial_aid_amount', 0),
            'final_amount': total_tuition - data.get('financial_aid_amount', 0),
            'payment_plan': 'Monthly',
            'payment_method': data.get('payment_method', ''),
            'payment_timing': data.get('payment_timing', ''),
            'payment_schedule': contract_terms.get('payment_schedule', [])
        }
        
        # Prepare data for the contract structure service
        contract_service_data = {
            'student_name': student_data['student_name'],
            'division': student_data['division'],  # Include division for proper school name
            'academic_year': contract_data['academic_year'],
            'registration_fee': f"${contract_data['registration_fee']:.2f}" if isinstance(contract_data['registration_fee'], (int, float)) else str(contract_data['registration_fee']),
            'registration_fee_option': contract_data['registration_fee_option'],
            'total_amount': f"${contract_data['final_amount']:.2f}" if isinstance(contract_data['final_amount'], (int, float)) else str(contract_data['final_amount']),
            'payment_timing': contract_data['payment_timing'],
            'payment_method': contract_data['payment_method'],
            
            # Credit card info - get from original data request
            'cc_number': data.get('cc_number', ''),
            'cc_holder_name': data.get('cc_holder_name', ''),
            'cc_exp_date': data.get('cc_exp_date', ''),
            'cc_cvv': data.get('cc_cvv', ''),
            'cc_zip': data.get('cc_zip', ''),
            'cc_charge_date': data.get('cc_charge_date', ''),
            
            # ACH info - get from original data request
            'ach_account_holder_name': data.get('ach_account_holder_name', ''),
            'ach_routing_number': data.get('ach_routing_number', ''),
            'ach_account_number': data.get('ach_account_number', ''),
            'ach_debit_date': data.get('ach_debit_date', ''),
            
            # Third party info - get from original data request
            'third_party_payer_name': data.get('third_party_payer_name', ''),
            'third_party_payer_relationship': data.get('third_party_payer_relationship', ''),
            'third_party_payer_contact': data.get('third_party_payer_contact', ''),
            
            # Tuition components - calculate actual tuition excluding room and board
            'tuition_components': [
                {'name': 'Registration Fee', 'final_amount': contract_data['registration_fee'], 'is_enabled': True},
                {'name': 'Tuition', 'final_amount': contract_data['total_tuition'] - contract_data['registration_fee'] - contract_data['room_amount'] - contract_data['board_amount'], 'is_enabled': True},
                {'name': 'Room', 'final_amount': contract_data['room_amount'], 'is_enabled': contract_data['room_amount'] > 0},
                {'name': 'Board', 'final_amount': contract_data['board_amount'], 'is_enabled': contract_data['board_amount'] > 0}
            ],
            
            # Payment schedule - format properly for the contract
            'payment_schedule': contract_terms.get('payment_schedule', [])
        }
        
        current_app.logger.info(f"Contract service data for preview: {contract_service_data}")
        
        # Generate preview PDF
        import os
        from datetime import datetime
        
        # Create preview directory if it doesn't exist
        preview_dir = os.path.join(os.getcwd(), 'static', 'temp', 'previews')
        if not os.path.exists(preview_dir):
            os.makedirs(preview_dir)
        
        # Generate temporary filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        preview_filename = f"contract_preview_{student_id}_{timestamp}.pdf"
        preview_path = os.path.join(preview_dir, preview_filename)
        
        # Generate the preview PDF using YZA method
        pdf_path = pdf_service.create_yza_contract(
            data=contract_service_data,
            output_path=preview_path
        )
        
        current_app.logger.info(f"Preview PDF generated: {pdf_path}")
        
        # Clean up old preview files (older than 1 hour)
        _cleanup_old_preview_files(preview_dir)
        
        # Create the preview HTML with embedded PDF viewer
        preview_url = f"/static/temp/previews/{preview_filename}"
        
        preview_html = f"""
        <div class="mb-3">
            <div class="alert alert-success">
                <h5><i class="fas fa-file-pdf"></i> Contract Preview</h5>
                <p><strong>Student:</strong> {contract_service_data['student_name']}</p>
                <p><strong>Division:</strong> {student_data['division']}</p>
                <p><strong>Academic Year:</strong> {contract_service_data['academic_year']}</p>
                <p><strong>Total Amount:</strong> {contract_service_data['total_amount']}</p>
                <p><strong>Payment Method:</strong> {contract_service_data['payment_method']}</p>
                <p><em>This is the actual PDF that will be generated with the current settings.</em></p>
            </div>
        </div>
        <div class="pdf-preview-container" style="width: 100%; height: 600px; border: 1px solid #ddd; border-radius: 4px;">
            <iframe src="{preview_url}" 
                    style="width: 100%; height: 100%; border: none;" 
                    type="application/pdf">
                <p>Your browser does not support PDFs. 
                   <a href="{preview_url}" target="_blank">Download the PDF</a> to view it.</p>
            </iframe>
        </div>
        <div class="mt-2 text-center">
            <a href="{preview_url}" target="_blank" class="btn btn-outline-primary">
                <i class="fas fa-external-link-alt"></i> Open PDF in New Tab
            </a>
        </div>
        """
        
        return jsonify({
            'success': True,
            'preview_html': preview_html,
            'contract_terms': contract_terms,
            'uses_template': False,
            'template_name': 'YZA Enrollment Contract'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract preview: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/generate-enhanced-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_enhanced_contract():
    """DEPRECATED: Use /api/financial/generate-contract instead"""
    current_app.logger.warning("DEPRECATED: /api/financial/generate-enhanced-contract is deprecated. Use /api/financial/generate-contract instead.")
    # Redirect to the new unified endpoint for backwards compatibility
    return generate_contract()

@financial.route('/api/financial/send-enhanced-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_enhanced_contract():
    """Send enhanced contract to student and update status"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        # Get student and validate
        student = Student.query.get_or_404(student_id)
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record or not financial_record.enhanced_contract_generated:
            return jsonify({'error': 'Contract must be generated before sending'}), 400
        
        # Check if contract needs regeneration
        if financial_record.check_needs_regeneration():
            return jsonify({
                'error': 'Contract is outdated due to tuition changes. Please regenerate before sending.',
                'needs_regeneration': True
            }), 400
        
        # Get email recipients
        email_recipients = data.get('email_recipients', [])
        
        # Check if custom email content was provided (from editable preview)
        custom_subject = data.get('email_subject')
        custom_message = data.get('email_message')
        
        # Always try to load the email template for tracking purposes
        email_template = None
        try:
            # Look for division-specific enrollment contract template first
            email_template = EmailTemplate.query.filter_by(
                category='enrollment_contract',
                division=student.division,
                is_active=True
            ).first()
            
            # If no division-specific template, try global enrollment contract template
            if not email_template:
                email_template = EmailTemplate.query.filter_by(
                    category='enrollment_contract',
                    division=None,
                    is_active=True
                ).first()
        except Exception as e:
            current_app.logger.warning(f"Error querying email templates: {str(e)}")
        
        # Now decide whether to use custom content or template content
        if custom_subject and custom_message:
            # Use custom content provided from the editable preview
            email_subject = custom_subject
            email_message = custom_message
            current_app.logger.info(f"Using custom email content from editable preview (template loaded: {email_template.name if email_template else 'None'})")
        else:
            # Use email template system if available
            if email_template:
                # Use email template system
                try:
                    # Prepare template context
                    school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
                    current_year = datetime.now().year
                    academic_year_label = f"{current_year}-{current_year + 1}"
                    
                    template_context = {
                        'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
                        'student_first_name': student.student_first_name or '',
                        'student_last_name': student.student_last_name or '',
                        'father_title': student.father_title or '',
                        'father_name': student.father_name or '',
                        'father_email': student.father_email or '',
                        'mother_title': student.mother_title or '',
                        'mother_name': student.mother_name or '',
                        'mother_email': student.mother_email or '',
                        'academic_year': academic_year_label,
                        'school_name': school_name,
                        'division': student.division,
                        'current_date': datetime.now().strftime('%B %d, %Y'),
                        'tuition_amount': str(financial_record.final_tuition_amount or financial_record.tuition_amount or 0),
                        'portal_url': request.url_root.rstrip('/'),
                    }
                    
                    # Render template
                    rendered = email_template.render(template_context)
                    email_subject = rendered['subject']
                    email_message = rendered['body']
                    
                    current_app.logger.info(f"Using email template '{email_template.name}' for enrollment contract")
                except Exception as e:
                    current_app.logger.error(f"Error rendering email template: {str(e)}")
                    # Fall back to default content
                    email_subject = f'Enrollment Contract - {student.student_name}'
                    email_message = 'Please find your enrollment contract attached.'
            else:
                # Fall back to default content
                email_subject = f'Enrollment Contract - {student.student_name}'
                email_message = 'Please find your enrollment contract attached. Please review, sign, and return.'
                current_app.logger.info("No enrollment contract email template found, using default content")
        
        # Add OpenSign integration and secure upload options
        opensign_document_id = None
        secure_upload_url = None
        
        # Check if we should use OpenSign or hybrid approach
        use_opensign = data.get('use_opensign', False)
        use_secure_upload = data.get('use_secure_upload', False)
        
        # Only create/query TuitionContract if we're actually using OpenSign or secure upload
        if use_opensign or use_secure_upload:
            # Get or create TuitionContract record for this student
            tuition_contract = TuitionContract.query.filter_by(
                student_id=student_id,
                academic_year_id=active_year.id,
                division=student.division
            ).first()
            
            if not tuition_contract:
                # Create new TuitionContract record
                tuition_contract = TuitionContract(
                    student_id=student_id,
                    academic_year_id=active_year.id,
                    division=student.division,
                    contract_type='Enhanced',
                    tuition_amount=financial_record.final_tuition_amount or financial_record.tuition_amount or 0,
                    final_tuition_amount=financial_record.final_tuition_amount or financial_record.tuition_amount or 0,
                    contract_pdf_path=financial_record.enhanced_contract_pdf_path,
                    parent1_name=f"{student.father_first_name or ''} {student.father_last_name or ''}".strip(),
                    parent1_email=student.father_email,
                    parent2_name=f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip(),
                    parent2_email=student.mother_email,
                    generated_by=current_user.username,
                    generated_date=datetime.utcnow()
                )
                db.session.add(tuition_contract)
                db.session.flush()  # Get the ID
            
            # Set signing method
            if use_opensign and use_secure_upload:
                tuition_contract.signing_method = 'both_available'
            elif use_opensign:
                tuition_contract.signing_method = 'digital_only'
            elif use_secure_upload:
                tuition_contract.signing_method = 'print_only'
            
            # OpenSign integration
            if use_opensign:
                from opensign_service import OpenSignService
                opensign = OpenSignService()
                
                signers = []
                if tuition_contract.parent1_email:
                    signers.append({
                        'name': tuition_contract.parent1_name,
                        'email': tuition_contract.parent1_email,
                        'role': 'Parent/Guardian 1'
                    })
                if tuition_contract.parent2_email:
                    signers.append({
                        'name': tuition_contract.parent2_name,
                        'email': tuition_contract.parent2_email,
                        'role': 'Parent/Guardian 2'
                    })
                
                # Get division config for OpenSign settings
                config = DivisionFinancialConfig.query.filter_by(division=student.division).first()
                
                opensign_result = opensign.send_for_signature(
                    document_path=financial_record.enhanced_contract_pdf_path,
                    signers=signers,
                    template_id=config.opensign_template_id if config else None,
                    folder_id=config.opensign_folder_id if config else None
                )
                
                if opensign_result.get('success'):
                    tuition_contract.opensign_document_id = opensign_result['document_id']
                    tuition_contract.opensign_status = 'pending'
                    tuition_contract.opensign_sent_date = datetime.utcnow()
                    opensign_document_id = opensign_result['document_id']
            
            # Secure upload integration - create link WITHOUT sending separate email
            if use_secure_upload:
                from secure_forms_service import SecureFormsService
                forms_service = SecureFormsService()
                
                # Use create_secure_link_only to avoid duplicate emails
                secure_link = forms_service.create_secure_link_only(
                    student_id=student_id,
                    form_type='tuition_contract',
                    form_id=tuition_contract.id,
                    expires_hours=data.get('expires_hours', 72)
                )
                
                tuition_contract.secure_upload_token = secure_link.token
                secure_upload_url = url_for('secure_forms.upload_form', token=secure_link.token, _external=True)
            
            # Update contract status
            tuition_contract.contract_status = 'Sent'
            tuition_contract.sent_by = current_user.username
            tuition_contract.sent_date = datetime.utcnow()
        
        # Enhance email content if OpenSign or secure upload is used
        if use_opensign or use_secure_upload:
            # Create enhanced email with signing options
            digital_url = f"https://opensign.io/sign/{opensign_document_id}" if opensign_document_id else None
            
            enhanced_message = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #0d6efd;">{student.division} Enrollment Contract</h2>
                
                <p>Dear {student.student_name} Family,</p>
                
                {email_message}
                
                <div style="margin: 30px 0;">
                    <h3>Signing Options Available:</h3>
            """
            
            if digital_url and secure_upload_url:
                enhanced_message += f"""
                    <div style="display: flex; gap: 20px; margin: 20px 0;">
                        <div style="flex: 1; background: #e3f2fd; padding: 20px; border-radius: 10px;">
                            <h4 style="color: #1976d2; margin-top: 0;">Digital Signature</h4>
                            <p>Sign electronically using our secure platform</p>
                            <a href="{digital_url}" style="background: #2196f3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">
                                Sign Digitally
                            </a>
                        </div>
                        <div style="flex: 1; background: #f3e5f5; padding: 20px; border-radius: 10px;">
                            <h4 style="color: #7b1fa2; margin-top: 0;">Print & Upload</h4>
                            <p>Print, sign by hand, and upload the signed contract</p>
                            <a href="{secure_upload_url}" style="background: #9c27b0; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">
                                Upload Signed Contract
                            </a>
                        </div>
                    </div>
                    <p><em>Please use only ONE of these methods - not both.</em></p>
                """
            elif digital_url:
                enhanced_message += f"""
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; text-align: center;">
                        <h4 style="color: #1976d2; margin-top: 0;">Digital Signature Available</h4>
                        <p>Sign your contract electronically using our secure platform</p>
                        <a href="{digital_url}" style="background: #2196f3; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                            Sign Contract Digitally
                        </a>
                    </div>
                """
            elif secure_upload_url:
                enhanced_message += f"""
                    <div style="background: #f3e5f5; padding: 20px; border-radius: 10px;">
                        <h4 style="color: #7b1fa2; margin-top: 0; text-align: center;">Print & Upload Instructions</h4>
                        
                        <div style="background: #fafafa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                            <h5 style="color: #495057; margin-top: 0;">Step-by-Step Process:</h5>
                            <ol style="margin: 0; padding-left: 20px;">
                                <li><strong>Print</strong> the attached contract PDF</li>
                                <li><strong>Sign</strong> all required signature fields by hand</li>
                                <li><strong>Upload</strong> the signed contract using the secure link below</li>
                            </ol>
                        </div>
                        
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{secure_upload_url}" style="background: #9c27b0; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                                Upload Signed Contract
                            </a>
                        </div>
                        
                        <div style="background: #fff3cd; padding: 10px; border-radius: 5px; font-size: 14px;">
                            <strong>Important:</strong> Upload link expires in {data.get('expires_hours', 72)} hours. 
                            Accepted formats: PDF, JPG, PNG (Max 10MB)
                        </div>
                    </div>
                """
            
            enhanced_message += """
                </div>
                
                <p>If you have any questions about the signing process, please contact our office.</p>
                
                <p>Best regards,<br>
                Financial Office</p>
            </div>
            """
            
            email_message = enhanced_message
        
        # Send email with contract
        from email_service import EmailService
        email_service = EmailService()
        
        # Prepare email data
        email_data = {
            'recipients': email_recipients,
            'subject': email_subject,
            'message': email_message,
            'attachment_path': financial_record.enhanced_contract_pdf_path,
            'attachment_name': f'enrollment_contract_{student.student_name.replace(" ", "_")}.pdf'
        }
        
        email_result = email_service.send_email_with_attachment(email_data)
        
        if email_result.get('success'):
            # Update contract status - both enhanced and legacy fields for UI compatibility
            financial_record.enhanced_contract_sent = True
            financial_record.enhanced_contract_sent_date = datetime.utcnow()
            financial_record.enrollment_contract_sent = True
            financial_record.enrollment_contract_sent_date = datetime.utcnow()
            
            # Also update tuition record for backwards compatibility
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=active_year.id
            ).first()
            
            if tuition_record:
                tuition_record.tuition_contract_sent = True
                tuition_record.tuition_contract_sent_date = datetime.utcnow()
            
            db.session.commit()
            
            response_data = {
                'success': True,
                'message': 'Contract sent successfully',
                'contract_status': financial_record.get_contract_status(),
                'template_used': email_template.name if email_template else 'Default Content'
            }
            
            # Add signing method information if used
            if use_opensign or use_secure_upload:
                response_data['signing_methods'] = {
                    'opensign_enabled': use_opensign,
                    'secure_upload_enabled': use_secure_upload,
                    'opensign_document_id': opensign_document_id,
                    'secure_upload_url': secure_upload_url
                }
            
            return jsonify(response_data)
        else:
            return jsonify({'error': f'Failed to send email: {email_result.get("error", "Unknown error")}'}), 500
            
    except Exception as e:
        import traceback
        db.session.rollback()
        
        # Log comprehensive error details
        error_details = {
            'error_type': type(e).__name__,
            'error_message': str(e),
            'student_id': data.get('student_id'),
            'email_recipients': data.get('email_recipients'),
            'use_opensign': data.get('use_opensign'),
            'use_secure_upload': data.get('use_secure_upload'),
            'traceback': traceback.format_exc(),
            'request_data': dict(data) if data else None,
            'user': current_user.username if current_user and current_user.is_authenticated else 'anonymous'
        }
        
        # Log to app logger with full details
        current_app.logger.error(f"SEND_ENHANCED_CONTRACT_ERROR: {json.dumps(error_details, indent=2)}")
        
        # Also log individual components for easier searching
        current_app.logger.error(f"Error sending enhanced contract for student {data.get('student_id')}: {str(e)}")
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__,
            'debug_info': error_details if current_app.debug else None
        }), 500

@financial.route('/api/financial/mark-contract-received', methods=['POST'])
@login_required
@permission_required('edit_students')
def mark_enhanced_contract_received():
    """Mark enhanced contract as received/signed"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record or not financial_record.enhanced_contract_sent:
            return jsonify({'error': 'Contract must be sent before marking as received'}), 400
        
        # Update contract status - both enhanced and legacy fields for UI compatibility
        financial_record.enhanced_contract_signed = True
        financial_record.enhanced_contract_signed_date = datetime.utcnow()
        financial_record.enrollment_contract_received = True
        financial_record.enrollment_contract_received_date = datetime.utcnow()
        
        # Also update tuition record for backwards compatibility
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if tuition_record:
            tuition_record.tuition_contract_signed = True
            tuition_record.tuition_contract_signed_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract marked as received',
            'contract_status': financial_record.get_contract_status()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking contract as received: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial/check-contract-status', methods=['POST'])
@login_required
@permission_required('view_students')
def check_contract_status():
    """Check if contract needs regeneration due to tuition changes"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record:
            return jsonify({'contract_status': 'not_generated'})
        
        # Check if regeneration is needed
        needs_regeneration = financial_record.check_needs_regeneration()
        
        if needs_regeneration and not financial_record.contract_needs_regeneration:
            # Mark as needing regeneration
            financial_record.mark_contract_outdated("Tuition amounts have changed")
            db.session.commit()
        
        # Get additional contract data for view signed contract buttons
        contract_data = {
            'contract_status': financial_record.get_contract_status(),
            'needs_regeneration': needs_regeneration,
            'regeneration_reason': financial_record.contract_regeneration_reason,
            'contract_generated_date': financial_record.enhanced_contract_generated_date.isoformat() if financial_record.enhanced_contract_generated_date else None,
            'contract_sent_date': financial_record.enhanced_contract_sent_date.isoformat() if financial_record.enhanced_contract_sent_date else None,
            'contract_signed_date': financial_record.enhanced_contract_signed_date.isoformat() if financial_record.enhanced_contract_signed_date else None
        }

        # Get TuitionContract data for OpenSign information
        tuition_contract = TuitionContract.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if tuition_contract:
            contract_data.update({
                'opensign_status': tuition_contract.opensign_status,
                'opensign_signed_url': tuition_contract.opensign_signed_url,
                'opensign_certificate_url': tuition_contract.opensign_certificate_url
            })

        # Get uploaded contract information (print & upload method)
        uploaded_contract_file = FormUploadLog.query.join(
            SecureFormLink, FormUploadLog.secure_link_id == SecureFormLink.id
        ).filter(
            FormUploadLog.student_id == student_id,
            SecureFormLink.form_type == 'tuition_contract',
            FormUploadLog.processing_status == 'processed'
        ).order_by(FormUploadLog.uploaded_at.desc()).first()
        
        # If no processed uploads found, check for pending ones and fix them (one-time migration)
        if not uploaded_contract_file:
            try:
                from secure_forms_service import SecureFormsService
                fixed_count = SecureFormsService.fix_existing_tuition_contract_uploads()
                if fixed_count > 0:
                    # Try the query again after fixing
                    uploaded_contract_file = FormUploadLog.query.join(
                        SecureFormLink, FormUploadLog.secure_link_id == SecureFormLink.id
                    ).filter(
                        FormUploadLog.student_id == student_id,
                        SecureFormLink.form_type == 'tuition_contract',
                        FormUploadLog.processing_status == 'processed'
                    ).order_by(FormUploadLog.uploaded_at.desc()).first()
            except Exception as e:
                current_app.logger.error(f"Error running tuition contract upload fix: {str(e)}")
        
        if uploaded_contract_file:
            contract_data.update({
                'uploaded_contract_id': uploaded_contract_file.id,
                'uploaded_contract_filename': uploaded_contract_file.original_filename,
                'uploaded_contract_date': uploaded_contract_file.uploaded_at.strftime('%B %d, %Y at %I:%M %p') if uploaded_contract_file.uploaded_at else None
            })

        return jsonify(contract_data)
        
    except Exception as e:
        current_app.logger.error(f"Error checking contract status: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _generate_enhanced_contract_terms(data):
    """Generate enhanced contract terms from request data"""
    # Extract payment dates
    start_month = data.get('payment_start_month', 8)  # September default
    start_year = data.get('payment_start_year', datetime.now().year)
    end_month = data.get('payment_end_month', 5)  # June default
    end_year = data.get('payment_end_year', datetime.now().year + 1)
    
    # Calculate payment schedule
    payment_schedule = []
    current_month = start_month
    current_year = start_year
    payment_number = 1
    total_payments = data.get('number_of_payments', 10)
    monthly_amount = data.get('monthly_payment', 0)
    
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    
    while payment_number <= total_payments:
        payment_schedule.append({
            'payment_number': payment_number,
            'due_date': f"{month_names[current_month]} 1, {current_year}",
            'amount': monthly_amount,
            'description': f'Monthly tuition payment {payment_number} of {total_payments}'
        })
        
        payment_number += 1
        current_month += 1
        if current_month > 11:
            current_month = 0
            current_year += 1
    
    # Add registration rolled in flag for PDF generation
    registration_rolled_in = data.get('registration_fee_option', 'upfront') == 'rolled'
    
    return {
        'total_tuition': data.get('total_tuition', 0),
        'registration_fee': data.get('registration_fee', 0),
        'registration_fee_option': data.get('registration_fee_option', 'upfront'),
        'registration_rolled_in': registration_rolled_in,  # Add this flag
        'payment_start_month': start_month,
        'payment_start_year': start_year,
        'payment_end_month': end_month,
        'payment_end_year': end_year,
        'number_of_payments': total_payments,
        'monthly_payment': monthly_amount,
        'payment_schedule': payment_schedule,
        'start_month_name': month_names[start_month],
        'end_month_name': month_names[end_month]
    }

def _generate_contract_preview_html(student, contract_terms):
    """Generate HTML preview of the contract"""
    student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
    
    # Build payment schedule table
    schedule_rows = ""
    for payment in contract_terms['payment_schedule']:
        schedule_rows += f"""
        <tr>
            <td>{payment['due_date']}</td>
            <td>${payment['amount']:.2f}</td>
            <td>{payment['description']}</td>
        </tr>
        """
    
    # Registration fee section
    reg_fee_section = ""
    if contract_terms['registration_fee_option'] == 'upfront':
        reg_fee_section = f"""
        <div class="alert alert-warning">
            <strong>Registration Fee:</strong> ${contract_terms['registration_fee']:.2f} due at contract signing
        </div>
        """
    else:
        reg_fee_section = f"""
        <div class="alert alert-info">
            <strong>Registration Fee:</strong> ${contract_terms['registration_fee']:.2f} included in monthly payments
        </div>
        """
    
    preview_html = f"""
    <div class="container-fluid">
        <div class="text-center mb-4">
            <h2>ENROLLMENT CONTRACT PREVIEW</h2>
            <h4>{student.division} Division</h4>
            <p class="text-muted">Academic Year {contract_terms['payment_start_year']}-{contract_terms['payment_start_year'] + 1}</p>
        </div>
        
        <div class="row mb-4">
            <div class="col-md-6">
                <h5>Student Information</h5>
                <p><strong>Name:</strong> {student_name}</p>
                <p><strong>Division:</strong> {student.division}</p>
            </div>
            <div class="col-md-6">
                <h5>Financial Summary</h5>
                <p><strong>Total Tuition:</strong> ${contract_terms['total_tuition']:.2f}</p>
                <p><strong>Monthly Payment:</strong> ${contract_terms['monthly_payment']:.2f}</p>
                <p><strong>Number of Payments:</strong> {contract_terms['number_of_payments']}</p>
            </div>
        </div>
        
        {reg_fee_section}
        
        <h5>Payment Schedule</h5>
        <div class="table-responsive">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Due Date</th>
                        <th>Amount</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {schedule_rows}
                </tbody>
            </table>
        </div>
        
        <div class="mt-4">
            <h5>Contract Terms</h5>
            <p>Payment period: {contract_terms['start_month_name']} {contract_terms['payment_start_year']} - {contract_terms['end_month_name']} {contract_terms['payment_end_year']}</p>
            <p>Late payments may incur additional fees. Please contact the financial office if you have any questions.</p>
        </div>
    </div>
    """
    
    return preview_html

@financial.route('/divisions/<division>/config')
@login_required
@permission_required('manage_users')
def division_financial_config(division):
    """Configure financial settings for a division"""
    try:
        # Get or create config
        config = DivisionFinancialConfig.query.filter_by(division=division).first()
        if not config:
            config = DivisionFinancialConfig(
                division=division,
                base_tuition_amount=Decimal('25000'),
                payment_plans_available=['Annual', 'Semester', 'Monthly'],
                late_fee_policy={'amount': 50, 'percentage': 1.5, 'grace_days': 10}
            )
            db.session.add(config)
            db.session.commit()
        
        return render_template('financial/division_config.html',
                             division=division,
                             config=config)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division config: {str(e)}")
        flash('Error loading configuration', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial.route('/api/divisions/<division>/config/update', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_division_financial_config(division):
    """Update financial configuration for a division"""
    try:
        config = DivisionFinancialConfig.query.filter_by(division=division).first()
        if not config:
            return jsonify({'error': 'Configuration not found'}), 404
        
        data = request.get_json()
        
        # Update config fields
        if 'base_tuition_amount' in data:
            config.base_tuition_amount = Decimal(str(data['base_tuition_amount']))
        if 'aid_application_deadline' in data:
            config.aid_application_deadline = datetime.strptime(data['aid_application_deadline'], '%Y-%m-%d').date()
        if 'aid_application_requirements' in data:
            config.aid_application_requirements = data['aid_application_requirements']
        if 'payment_plans_available' in data:
            config.payment_plans_available = data['payment_plans_available']
        if 'late_fee_policy' in data:
            config.late_fee_policy = data['late_fee_policy']
        if 'opensign_template_id' in data:
            config.opensign_template_id = data['opensign_template_id']
        
        config.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating division config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/financial-aid/<int:application_id>/send-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_financial_aid_form_secure(application_id):
    """Send secure financial aid form to student/parents"""
    try:

        from secure_forms_service import SecureFormsService
        
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        recipient_email = data.get('recipient_email')
        expires_hours = data.get('expires_hours', 72)
        
        # Create secure link and send email
        forms_service = SecureFormsService()
        secure_link = forms_service.create_secure_link_and_send_email(
            student_id=application.student_id,
            form_type='financial_aid_app',
            form_id=application_id,
            expires_hours=expires_hours,
            recipient_email=recipient_email
        )
        
        return jsonify({
            'success': True,
            'message': 'Secure form link created and email sent successfully',
            'link_id': secure_link.id,
            'expires_at': secure_link.expires_at.isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending financial aid form: {str(e)}")
        return jsonify({'error': str(e)}), 500


@financial.route('/api/tuition-contracts/<int:contract_id>/send-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_tuition_contract_form_secure(contract_id):
    """Send secure tuition contract form to student/parents"""
    try:
        from secure_forms_service import SecureFormsService
        
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        data = request.get_json()
        recipient_email = data.get('recipient_email')
        expires_hours = data.get('expires_hours', 72)
        
        # Create secure link and send email
        forms_service = SecureFormsService()
        secure_link = forms_service.create_secure_link_and_send_email(
            student_id=contract.student_id,
            form_type='tuition_contract',
            form_id=contract_id,
            expires_hours=expires_hours,
            recipient_email=recipient_email
        )
        
        return jsonify({
            'success': True,
            'message': 'Secure contract link created and email sent successfully',
            'link_id': secure_link.id,
            'expires_at': secure_link.expires_at.isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending tuition contract form: {str(e)}")
        return jsonify({'error': str(e)}), 500


@financial.route('/api/tuition-contracts/<int:contract_id>/send-hybrid', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_hybrid_contract(contract_id):
    """Send contract with BOTH digital signature AND print/upload options"""
    try:
        from secure_forms_service import SecureFormsService
        from opensign_service import OpenSignService
        
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        data = request.get_json()
        recipient_email = data.get('recipient_email')
        expires_hours = data.get('expires_hours', 72)
        
        # Set signing method to both available
        contract.signing_method = 'both_available'
        
        # 1. Create secure upload link for print option
        forms_service = SecureFormsService()
        secure_link = forms_service.create_secure_link_and_send_email(
            student_id=contract.student_id,
            form_type='tuition_contract',
            form_id=contract_id,
            expires_hours=expires_hours,
            recipient_email=recipient_email
        )
        
        # Store the secure upload token in the contract
        contract.secure_upload_token = secure_link.token
        
        # 2. Send via OpenSign for digital signature option
        opensign = OpenSignService()
        
        signers = []
        if contract.parent1_email:
            signers.append({
                'name': contract.parent1_name,
                'email': contract.parent1_email,
                'role': 'Parent/Guardian 1'
            })
        if contract.parent2_email:
            signers.append({
                'name': contract.parent2_name,
                'email': contract.parent2_email,
                'role': 'Parent/Guardian 2'
            })
        
        # Get division config for OpenSign settings
        config = DivisionFinancialConfig.query.filter_by(division=contract.division).first()
        
        opensign_result = opensign.send_for_signature(
            document_path=contract.contract_pdf_path,
            signers=signers,
            template_id=config.opensign_template_id if config else None,
            folder_id=config.opensign_folder_id if config else None
        )
        
        if opensign_result.get('success'):
            contract.opensign_document_id = opensign_result['document_id']
            contract.opensign_status = 'pending'
            contract.opensign_sent_date = datetime.utcnow()
        
        # Update contract status
        contract.contract_status = 'Sent'
        contract.sent_by = current_user.username
        contract.sent_date = datetime.utcnow()
        
        db.session.commit()
        
        # 3. Send custom email explaining both options
        from email_service import EmailService
        email_service = EmailService()
        
        subject = f"{contract.division} Tuition Contract - Choose Your Signing Method"
        
        # Create URLs
        digital_url = f"https://opensign.io/sign/{contract.opensign_document_id}" if contract.opensign_document_id else "#"
        print_download_url = url_for('secure_forms.download_form', token=secure_link.token, _external=True)
        print_upload_url = url_for('secure_forms.upload_form', token=secure_link.token, _external=True)
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #0d6efd;">{contract.division} Tuition Contract</h2>
            
            <p>Dear {contract.student.student_name} Family,</p>
            
            <p>Your tuition contract is ready for signature. We're offering you <strong>two convenient options</strong> to complete this process:</p>
            
            <div style="display: flex; gap: 20px; margin: 30px 0;">
                <!-- Digital Option -->
                <div style="flex: 1; background: #e3f2fd; padding: 20px; border-radius: 10px; border-left: 4px solid #2196f3;">
                    <h3 style="color: #1976d2; margin-top: 0;">
                        <i class="fas fa-signature"></i> Option 1: Digital Signature
                    </h3>
                    <p>Sign electronically using our secure digital platform:</p>
                    <ul>
                        <li>✅ Instant completion</li>
                        <li>✅ Secure and legally binding</li>
                        <li>✅ No printing required</li>
                    </ul>
                    <div style="text-align: center; margin-top: 15px;">
                        <a href="{digital_url}" style="background: #2196f3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                            Sign Digitally
                        </a>
                    </div>
                </div>
                
                <!-- Print Option -->
                <div style="flex: 1; background: #f3e5f5; padding: 20px; border-radius: 10px; border-left: 4px solid #9c27b0;">
                    <h3 style="color: #7b1fa2; margin-top: 0;">
                        <i class="fas fa-print"></i> Option 2: Print & Upload
                    </h3>
                    <p>Prefer to print, sign by hand, and upload:</p>
                    <ul>
                        <li>✅ Traditional pen-and-paper signing</li>
                        <li>✅ Review at your own pace</li>
                        <li>✅ Secure upload when ready</li>
                    </ul>
                    <div style="text-align: center; margin-top: 15px;">
                        <a href="{print_download_url}" style="background: #9c27b0; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; margin-right: 5px;">
                            Download
                        </a>
                        <a href="{print_upload_url}" style="background: #9c27b0; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px;">
                            Upload
                        </a>
                    </div>
                </div>
            </div>
            
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <h4 style="margin-top: 0;">Choose ONE Method:</h4>
                <p>Please use either the digital signature OR the print & upload option - not both. 
                Once you complete the contract using one method, the other option will be automatically disabled.</p>
                <p><strong>Contract expires:</strong> {secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
            
            <h4>Contract Details:</h4>
            <ul>
                <li><strong>Student:</strong> {contract.student.student_name}</li>
                <li><strong>Division:</strong> {contract.division}</li>
                <li><strong>Academic Year:</strong> {contract.academic_year.year_label}</li>
                <li><strong>Tuition Amount:</strong> ${contract.final_tuition_amount:,.2f}</li>
                <li><strong>Payment Plan:</strong> {contract.payment_plan}</li>
            </ul>
            
            <p>If you have any questions about either signing method, please contact our office.</p>
            
            <p>Best regards,<br>
            {contract.division} Financial Office</p>
        </div>
        """
        
        email_service.send_email(
            to_email=recipient_email,
            subject=subject,
            html_content=html_content
        )
        
        return jsonify({
            'success': True,
            'message': 'Hybrid contract sent successfully - both digital and print options available',
            'opensign_document_id': contract.opensign_document_id,
            'secure_upload_token': contract.secure_upload_token,
            'digital_url': digital_url,
            'print_upload_url': print_upload_url
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending hybrid contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial.route('/api/students/<student_id>/tuition-history')
@login_required
@permission_required('view_students')
def get_student_tuition_history(student_id):
    """Get complete tuition history with year-over-year tracking"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get all yearly tracking records
        tracking_records = StudentYearlyTracking.query.filter_by(
            student_id=student_id
        ).join(AcademicYear).order_by(AcademicYear.start_date.desc()).all()
        
        history = []
        for tracking in tracking_records:
            # Get tuition record for this year
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=tracking.academic_year_id
            ).first()
            
            # Get component details for this year
            components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=tracking.academic_year_id,
                is_active=True
            ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
            
            component_details = []
            for comp in components:
                component_details.append({
                    'name': comp.component.name,
                    'type': comp.component.component_type,
                    'amount': float(comp.amount),
                    'discount_percentage': float(comp.discount_percentage or 0),
                    'final_amount': float(comp.calculated_amount)
                })
            
            history_item = {
                'academic_year': {
                    'id': tracking.academic_year.id,
                    'year_label': tracking.academic_year.year_label,
                    'start_date': tracking.academic_year.start_date.strftime('%Y-%m-%d'),
                    'end_date': tracking.academic_year.end_date.strftime('%Y-%m-%d')
                },
                'programs': {
                    'dorm_program': tracking.dorm_program_status,
                    'meal_program': tracking.meal_program_status,
                    'program_summary': tracking.program_summary
                },
                'tuition': {
                    'total_charged': float(tracking.total_tuition_charged or 0),
                    'amount_paid': float(tuition_record.amount_paid or 0) if tuition_record else 0,
                    'balance_due': float(tuition_record.balance_due or 0) if tuition_record else 0
                },
                'financial_aid': {
                    'financial_aid_received': float(tracking.financial_aid_received or 0),
                    'scholarship_amount': float(tracking.scholarship_amount or 0),
                    'fafsa_amount': float(tracking.fafsa_amount or 0)
                },
                'components': component_details,
                'enrollment_status': tracking.enrollment_status,
                'notes': tracking.notes,
                'last_updated': tracking.updated_at.strftime('%Y-%m-%d %H:%M') if tracking.updated_at else None
            }
            
            history.append(history_item)
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'student_name': student.student_name,
            'division': student.division,
            'history': history,
            'summary': {
                'total_years': len(history),
                'years_with_dorm': sum(1 for h in history if h['programs']['dorm_program']),
                'years_with_meals': sum(1 for h in history if h['programs']['meal_program']),
                'total_tuition_all_years': sum(h['tuition']['total_charged'] for h in history)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting tuition history: {str(e)}")
        return jsonify({'error': str(e)}), 500 

@financial.route('/api/financial/batch-contract-status', methods=['POST'])
@login_required
@permission_required('view_students')
def batch_contract_status():
    """Check contract status for multiple students at once"""
    try:
        data = request.get_json()
        student_ids = data.get('student_ids', [])
        
        if not student_ids:
            return jsonify({'error': 'No student IDs provided'}), 400
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get all financial records for the students in one query
        financial_records = FinancialRecord.query.filter(
            FinancialRecord.student_id.in_(student_ids),
            FinancialRecord.academic_year_id == active_year.id
        ).all()
        
        # Create a mapping for quick lookup
        records_by_student = {record.student_id: record for record in financial_records}
        
        results = []
        for student_id in student_ids:
            financial_record = records_by_student.get(student_id)
            
            if not financial_record:
                results.append({
                    'student_id': student_id,
                    'contract_status': 'not_generated'
                })
                continue
            
            # Check if regeneration is needed (batch processing optimization)
            needs_regeneration = financial_record.check_needs_regeneration()
            
            if needs_regeneration and not financial_record.contract_needs_regeneration:
                # Mark as needing regeneration
                financial_record.mark_contract_outdated("Tuition amounts have changed")
            
            results.append({
                'student_id': student_id,
                'contract_status': financial_record.get_contract_status(),
                'needs_regeneration': needs_regeneration,
                'regeneration_reason': financial_record.contract_regeneration_reason,
                'contract_generated_date': financial_record.enhanced_contract_generated_date.isoformat() if financial_record.enhanced_contract_generated_date else None,
                'contract_sent_date': financial_record.enhanced_contract_sent_date.isoformat() if financial_record.enhanced_contract_sent_date else None,
                'contract_signed_date': financial_record.enhanced_contract_signed_date.isoformat() if financial_record.enhanced_contract_signed_date else None
            })
        
        # Commit any changes made during the batch check
        db.session.commit()
        
        return jsonify(results)
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in batch contract status check: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _cleanup_old_preview_files(preview_dir):
    """Clean up preview files older than 1 hour"""
    try:
        import os
        import time
        from datetime import datetime, timedelta
        
        if not os.path.exists(preview_dir):
            return
        
        cutoff_time = time.time() - 3600  # 1 hour ago
        
        for filename in os.listdir(preview_dir):
            if filename.startswith('contract_preview_') and filename.endswith('.pdf'):
                file_path = os.path.join(preview_dir, filename)
                if os.path.getmtime(file_path) < cutoff_time:
                    try:
                        os.remove(file_path)
                        current_app.logger.debug(f"Cleaned up old preview file: {filename}")
                    except Exception as e:
                        current_app.logger.warning(f"Could not remove preview file {filename}: {str(e)}")
    except Exception as e:
        current_app.logger.warning(f"Error during preview cleanup: {str(e)}")

def _cleanup_old_student_contracts(student_id, contracts_dir):
    """Clean up old contract files for a specific student to prevent accumulation"""
    try:
        import os
        import glob
        
        # Get student info for name pattern matching
        student = Student.query.get(student_id)
        if not student:
            return
        
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        
        # Find all contracts for this student
        pattern = os.path.join(contracts_dir, f"*contract*{clean_name}*.pdf")
        old_contracts = glob.glob(pattern)
        
        # Also check the current contract path from database
        if student.tuition_contract_pdf_path:
            old_contracts.append(student.tuition_contract_pdf_path)
        
        # Remove duplicates and clean up
        old_contracts = list(set(old_contracts))
        
        for contract_path in old_contracts:
            if os.path.exists(contract_path):
                try:
                    os.remove(contract_path)
                    current_app.logger.info(f"Cleaned up old contract: {contract_path}")
                except Exception as e:
                    current_app.logger.warning(f"Could not remove old contract {contract_path}: {str(e)}")
                    
    except Exception as e:
        current_app.logger.warning(f"Error cleaning up old contracts for student {student_id}: {str(e)}")

@financial.route('/api/financial/generate-fillable-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_fillable_contract():
    """DEPRECATED: Use /api/financial/generate-contract instead"""
    current_app.logger.warning("DEPRECATED: /api/financial/generate-fillable-contract is deprecated. Use /api/financial/generate-contract instead.")
    # Redirect to the new unified endpoint for backwards compatibility
    return generate_contract()

@financial.route('/api/financial/documents/upload', methods=['POST'])
@login_required
@permission_required('edit_students')
def upload_financial_document():
    """Upload a financial document for a specific financial record"""
    try:
        # Get form data
        financial_record_id = request.form.get('financial_record_id')
        document_type = request.form.get('document_type')
        description = request.form.get('description', '')
        
        # Validate required fields
        if not financial_record_id:
            return jsonify({'error': 'Financial record ID is required'}), 400
        
        if not document_type:
            return jsonify({'error': 'Document type is required'}), 400
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate financial record exists
        financial_record = FinancialRecord.query.get(financial_record_id)
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Get the student for additional validation
        student = financial_record.student
        if not student:
            return jsonify({'error': 'Student not found for this financial record'}), 404
        
        # Process upload using the storage service
        try:
            from storage_service import StorageService
            storage_service = StorageService()
            
            upload_result = storage_service.upload_file(
                uploaded_file,
                uploaded_file.filename,
                folder='financial_documents',
                student_id=str(student.id),
                form_type=document_type
            )
            
            file_path = upload_result['path']
            
        except Exception as e:
            current_app.logger.error(f"File upload failed: {str(e)}")
            return jsonify({'error': f'File upload failed: {str(e)}'}), 500
        
        # Create FinancialDocument record
        financial_document = FinancialDocument(
            financial_record_id=financial_record_id,
            document_type=document_type,
            filename=uploaded_file.filename,
            file_path=file_path,
            file_size=len(uploaded_file.read()),
            mime_type=uploaded_file.content_type,
            uploaded_by=current_user.username,
            description=description,
            encrypted=True
        )
        
        # Reset file pointer after reading for size
        uploaded_file.seek(0)
        
        # Generate checksum for security
        import hashlib
        file_content = uploaded_file.read()
        checksum = hashlib.sha256(file_content).hexdigest()
        financial_document.checksum = checksum
        
        db.session.add(financial_document)
        
        # Update financial record based on document type
        if document_type == 'financial_aid_form':
            financial_record.financial_aid_form_received = True
            financial_record.financial_aid_form_received_date = datetime.utcnow()
        elif document_type == 'enrollment_contract':
            # Update both enhanced and enrollment contract fields for consistency
            financial_record.enhanced_contract_signed = True
            financial_record.enhanced_contract_signed_date = datetime.utcnow()
            financial_record.enrollment_contract_received = True
            financial_record.enrollment_contract_received_date = datetime.utcnow()
        
        db.session.commit()
        
        # Send notification email to relevant staff
        try:
            email_service = EmailService()
            
            subject = f"Financial Document Uploaded - {student.student_name}"
            
            html_content = f"""
            <h3>Financial Document Upload</h3>
            
            <p><strong>Uploaded by:</strong> {current_user.full_name} ({current_user.username})</p>
            <p><strong>Student:</strong> {student.student_name} (ID: {student.id})</p>
            <p><strong>Division:</strong> {student.division}</p>
            <p><strong>Document Type:</strong> {document_type.replace('_', ' ').title()}</p>
            <p><strong>File:</strong> {uploaded_file.filename}</p>
            <p><strong>Size:</strong> {financial_document.file_size} bytes</p>
            <p><strong>Upload Time:</strong> {financial_document.uploaded_at.strftime('%B %d, %Y at %I:%M %p')}</p>
            
            {f'<p><strong>Description:</strong> {description}</p>' if description else ''}
            
            <p>The document has been securely stored and linked to the student's financial record.</p>
            """
            
            # Send to financial office
            admin_email = current_app.config.get('FINANCIAL_ADMIN_EMAIL', 'admin@school.edu')
            email_service.send_email(
                to_email=admin_email,
                subject=subject,
                html_content=html_content
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to send upload notification: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'{document_type.replace("_", " ").title()} uploaded successfully',
            'document_id': financial_document.id,
            'file_path': file_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error uploading financial document: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@financial.route('/api/students/<student_id>/get-or-create-financial-record', methods=['POST'])
@login_required
@permission_required('edit_students')
def get_or_create_financial_record(student_id):
    """Get or create a financial record for a student and academic year"""
    try:
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        # Validate student exists
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Validate academic year exists
        academic_year = AcademicYear.query.get(academic_year_id)
        if not academic_year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        # Try to find existing financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        # Create if doesn't exist
        if not financial_record:
            financial_record = FinancialRecord(
                student_id=student_id,
                academic_year_id=academic_year_id,
                financial_aid_required=False,  # Default to False
                tuition_type='Not Set'  # Default value
            )
            db.session.add(financial_record)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'financial_record_id': financial_record.id,
            'message': 'Financial record ready'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting/creating financial record: {str(e)}")
        return jsonify({'error': f'Failed to create financial record: {str(e)}'}), 500

@financial.route('/financial/records/<int:record_id>/documents')
@login_required
@permission_required('view_students')
def view_financial_documents(record_id):
    """View documents for a financial record"""
    financial_record = FinancialRecord.query.get_or_404(record_id)
    
    # Use the unified documents property that includes both manual and secure uploads
    documents = financial_record.all_documents
    
    return render_template('financial/documents.html',
                         financial_record=financial_record,
                         student=financial_record.student,
                         documents=documents)

@financial.route('/api/financial/generate-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_contract():
    """Generate a unified contract that is both fillable and printable"""
    try:
        current_app.logger.info("=== UNIFIED CONTRACT GENERATION REQUESTED ===")
        current_app.logger.info("Contract generation requested")
        
        data = request.get_json()
        current_app.logger.info(f"Generation request data: {data}")
        
        student_id = data.get('student_id')
        
        if not student_id:
            current_app.logger.error("No student ID provided in generation request")
            return jsonify({'error': 'Student ID is required'}), 400
        
        current_app.logger.info(f"Looking up student: {student_id}")
        student = Student.query.get(student_id)
        if not student:
            current_app.logger.error(f"Student not found: {student_id}")
            return jsonify({'error': 'Student not found'}), 404
        
        current_app.logger.info(f"Found student: {student.student_name}, Division: {student.division}")
        
        # Generate contract terms
        current_app.logger.info("Generating contract terms")
        contract_terms = _generate_enhanced_contract_terms(data)
        current_app.logger.info(f"Contract terms generated: {contract_terms}")
        
        # Use ContractStructureService for unified generation (both fillable and printable)
        current_app.logger.info("Using ContractStructureService for unified contract generation")
        from contract_structure_service import ContractStructureService
        from models import StudentTuitionComponent, TuitionComponent, DivisionTuitionComponent, AcademicYear
        
        pdf_service = ContractStructureService()
        
        # Prepare student data
        student_data = {
            'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
            'division': student.division or 'YZA'
        }
        
        # Get student's actual tuition data from database
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        actual_tuition_data = {'total_tuition': 0, 'registration_fee': 0, 'room_amount': 0, 'board_amount': 0}
        
        if academic_year:
            # Get student's tuition components
            student_components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year.id,
                is_active=True
            ).join(TuitionComponent).all()
            
            # If no student components exist, get division defaults
            if not student_components:
                division_components = db.session.query(DivisionTuitionComponent, TuitionComponent).join(
                    TuitionComponent, DivisionTuitionComponent.component_id == TuitionComponent.id
                ).filter(
                    DivisionTuitionComponent.division == student.division,
                    DivisionTuitionComponent.academic_year_id == academic_year.id,
                    DivisionTuitionComponent.is_enabled == True,
                    TuitionComponent.is_active == True
                ).all()
                
                # Calculate totals from division defaults
                for div_comp, comp in division_components:
                    amount = float(div_comp.default_amount)
                    actual_tuition_data['total_tuition'] += amount
                    
                    if comp.component_type == 'fee' or 'registration' in comp.name.lower():
                        actual_tuition_data['registration_fee'] = amount
                    elif comp.component_type == 'room' or 'room' in comp.name.lower():
                        actual_tuition_data['room_amount'] = amount
                    elif comp.component_type == 'board' or 'board' in comp.name.lower():
                        actual_tuition_data['board_amount'] = amount
            else:
                # Calculate totals from student components
                for comp in student_components:
                    amount = float(comp.calculated_amount)
                    actual_tuition_data['total_tuition'] += amount
                    
                    if comp.component.component_type == 'fee' or 'registration' in comp.component.name.lower():
                        actual_tuition_data['registration_fee'] = amount
                    elif comp.component.component_type == 'room' or 'room' in comp.component.name.lower():
                        actual_tuition_data['room_amount'] = amount
                    elif comp.component.component_type == 'board' or 'board' in comp.component.name.lower():
                        actual_tuition_data['board_amount'] = amount
        
        current_app.logger.info(f"Actual tuition data from database: {actual_tuition_data}")
        
        # Use actual database data if available, otherwise fall back to form data
        total_tuition = actual_tuition_data['total_tuition'] if actual_tuition_data['total_tuition'] > 0 else contract_terms.get('total_tuition', 0)
        registration_fee = actual_tuition_data['registration_fee'] if actual_tuition_data['registration_fee'] > 0 else contract_terms.get('registration_fee', 0)
        room_amount = actual_tuition_data['room_amount']
        board_amount = actual_tuition_data['board_amount']
        
        # Prepare contract data
        contract_data = {
            'academic_year': f"{contract_terms.get('payment_start_year', 2025)}-{contract_terms.get('payment_start_year', 2025) + 1}",
            'total_tuition': total_tuition,
            'registration_fee': registration_fee,
            'registration_fee_option': contract_terms.get('registration_fee_option', 'upfront'),
            'room_amount': room_amount,
            'board_amount': board_amount,
            'financial_aid_amount': data.get('financial_aid_amount', 0),
            'final_amount': total_tuition - data.get('financial_aid_amount', 0),
            'payment_plan': 'Monthly',
            'payment_method': data.get('payment_method', ''),
            'payment_timing': data.get('payment_timing', ''),
            'payment_schedule': contract_terms.get('payment_schedule', [])
        }
        
        # Prepare data for the contract service
        contract_service_data = {
            'student_name': student_data['student_name'],
            'division': student_data['division'],  # Include division for proper school name
            'academic_year': contract_data['academic_year'],
            'registration_fee': f"${contract_data['registration_fee']:.2f}" if isinstance(contract_data['registration_fee'], (int, float)) else str(contract_data['registration_fee']),
            'registration_fee_option': contract_data['registration_fee_option'],
            'total_amount': f"${contract_data['final_amount']:.2f}" if isinstance(contract_data['final_amount'], (int, float)) else str(contract_data['final_amount']),
            'payment_timing': contract_data['payment_timing'],
            'payment_method': contract_data['payment_method'],
            
            # Credit card info
            'cc_number': data.get('cc_number', ''),
            'cc_holder_name': data.get('cc_holder_name', ''),
            'cc_exp_date': data.get('cc_exp_date', ''),
            'cc_cvv': data.get('cc_cvv', ''),
            'cc_zip': data.get('cc_zip', ''),
            'cc_charge_date': data.get('cc_charge_date', ''),
            
            # ACH info
            'ach_account_holder_name': data.get('ach_account_holder_name', ''),
            'ach_routing_number': data.get('ach_routing_number', ''),
            'ach_account_number': data.get('ach_account_number', ''),
            'ach_debit_date': data.get('ach_debit_date', ''),
            
            # Third party info
            'third_party_payer_name': data.get('third_party_payer_name', ''),
            'third_party_payer_relationship': data.get('third_party_payer_relationship', ''),
            'third_party_payer_contact': data.get('third_party_payer_contact', ''),
            
            # Tuition components - calculate actual tuition excluding room and board
            'tuition_components': [
                {'name': 'Registration Fee', 'final_amount': contract_data['registration_fee'], 'is_enabled': True},
                {'name': 'Tuition', 'final_amount': contract_data['total_tuition'] - contract_data['registration_fee'] - contract_data['room_amount'] - contract_data['board_amount'], 'is_enabled': True},
                {'name': 'Room', 'final_amount': contract_data['room_amount'], 'is_enabled': contract_data['room_amount'] > 0},
                {'name': 'Board', 'final_amount': contract_data['board_amount'], 'is_enabled': contract_data['board_amount'] > 0}
            ],
            
            # Payment schedule
            'payment_schedule': contract_terms.get('payment_schedule', [])
        }
        
        # Generate filename and path with versioning
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        
        # Create contracts directory if it doesn't exist
        import os
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Clean up old contracts for this student to prevent accumulation
        _cleanup_old_student_contracts(student_id, contracts_dir)
        
        # Use current timestamp for new contract
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"tuition_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Generate unified contract (both fillable and printable)
        actual_pdf_path = pdf_service.create_yza_contract(
            data=contract_service_data,
            output_path=pdf_path
        )
        
        current_app.logger.info(f"Unified contract generated: {actual_pdf_path}")
        
        # Reset Student model contract fields when regenerating
        student.tuition_contract_generated = True
        student.tuition_contract_generated_date = datetime.utcnow()
        student.tuition_contract_pdf_path = actual_pdf_path
        
        # Reset contract status to "generated" when regenerating
        # This forces the contract to be sent and signed again
        student.tuition_contract_sent = False
        student.tuition_contract_sent_date = None
        student.tuition_contract_signed = False
        student.tuition_contract_signed_date = None
        student.opensign_document_id = None
        student.opensign_document_status = None
        student.opensign_signed_url = None
        student.opensign_certificate_url = None
        
        # Update database records
        academic_year_id = data.get('academic_year_id')
        if not academic_year_id:
            active_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = active_year.id if active_year else None
        
        # Also reset Student model contract status fields when regenerating
        student.tuition_contract_sent = False
        student.tuition_contract_sent_date = None
        student.tuition_contract_signed = False
        student.tuition_contract_signed_date = None
        student.opensign_document_id = None
        student.opensign_document_status = None
        student.opensign_signed_url = None
        student.opensign_certificate_url = None
        
        if academic_year_id:
            # Update tuition record
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
            if not tuition_record:
                tuition_record = TuitionRecord(
                    student_id=student_id,
                    academic_year_id=academic_year_id
                )
                db.session.add(tuition_record)
            
            tuition_record.tuition_contract_generated = True
            tuition_record.tuition_contract_generated_date = datetime.utcnow()
            tuition_record.tuition_contract_pdf_path = actual_pdf_path
            tuition_record.contract_terms = contract_terms
            
            # Reset contract status to "generated" when regenerating
            # This forces the contract to be sent and signed again
            tuition_record.tuition_contract_sent = False
            tuition_record.tuition_contract_sent_date = None
            tuition_record.tuition_contract_signed = False 
            tuition_record.tuition_contract_signed_date = None
            tuition_record.opensign_document_id = None
            tuition_record.opensign_document_status = None
            tuition_record.opensign_signed_url = None
            tuition_record.opensign_certificate_url = None
            
            # Update financial record
            financial_record = FinancialRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
            if financial_record:
                financial_record.enhanced_contract_generated = True
                financial_record.enhanced_contract_generated_date = datetime.utcnow()
                financial_record.enhanced_contract_pdf_path = actual_pdf_path
                financial_record.contract_generation_hash = financial_record.generate_tuition_hash()
                financial_record.contract_needs_regeneration = False
                financial_record.contract_regeneration_reason = None
                
                # Reset contract status to "generated" when regenerating
                # This forces the contract to be sent and signed again
                financial_record.enhanced_contract_sent = False
                financial_record.enhanced_contract_sent_date = None
                financial_record.enhanced_contract_signed = False
                financial_record.enhanced_contract_signed_date = None
                financial_record.enhanced_contract_opensign_id = None
                financial_record.enhanced_contract_opensign_status = None
        
        db.session.commit()
        current_app.logger.info("Contract generation completed successfully")
        
        return jsonify({
            'success': True,
            'message': 'Contract generated successfully',
            'contract_path': actual_pdf_path,
            'contract_terms': contract_terms,
            'contract_status': financial_record.get_contract_status() if financial_record else 'generated'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating contract: {str(e)}")
        return jsonify({'error': str(e)}), 500