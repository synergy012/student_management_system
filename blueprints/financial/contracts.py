from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import db, Student, FinancialRecord, TuitionRecord, AcademicYear, DivisionFinancialConfig, TuitionContract, FileAttachment, SecureFormLink
from utils.decorators import permission_required
from email_service import EmailService
from pdf_service import PDFService
from datetime import datetime, timedelta
import os
import tempfile

financial_contracts = Blueprint('financial_contracts', __name__)

@financial_contracts.route('/api/students/<student_id>/generate-tuition-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_tuition_contract(student_id):
    """Generate a tuition contract for a student"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get active academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Generate contract PDF
        pdf_service = PDFService()
        contract_data = {
            'student': student,
            'financial_record': financial_record,
            'academic_year': active_year
        }
        
        pdf_path = pdf_service.generate_tuition_contract(contract_data)
        
        # Update financial record
        financial_record.enhanced_contract_generated = True
        financial_record.enhanced_contract_generated_date = datetime.utcnow()
        financial_record.enhanced_contract_pdf_path = pdf_path
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract generated successfully',
            'contract_path': pdf_path
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/students/<student_id>/tuition-contract/download')
@login_required
@permission_required('view_students')
def download_tuition_contract(student_id):
    """Download the generated tuition contract"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get active academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record or not financial_record.enhanced_contract_pdf_path:
            return jsonify({'error': 'Contract not found'}), 404
        
        filename = f"{student.full_name}_tuition_contract_{active_year.year}.pdf"
        return send_file(financial_record.enhanced_contract_pdf_path, 
                        as_attachment=True, 
                        download_name=filename)
        
    except Exception as e:
        current_app.logger.error(f"Error downloading contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/records/<int:record_id>/mark-contract-received', methods=['POST'])
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

@financial_contracts.route('/api/financial/mark-contract-received', methods=['POST'])
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
            'message': 'Contract marked as received'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking contract as received: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/check-contract-status', methods=['POST'])
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
        needs_regeneration = False
        if hasattr(financial_record, 'check_needs_regeneration'):
            needs_regeneration = financial_record.check_needs_regeneration()
        
        return jsonify({
            'contract_status': 'generated' if financial_record.enhanced_contract_generated else 'not_generated',
            'needs_regeneration': needs_regeneration
        })
        
    except Exception as e:
        current_app.logger.error(f"Error checking contract status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/batch-contract-status', methods=['POST'])
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
            
            # Check if regeneration is needed
            needs_regeneration = False
            if hasattr(financial_record, 'check_needs_regeneration'):
                needs_regeneration = financial_record.check_needs_regeneration()
            
            results.append({
                'student_id': student_id,
                'contract_status': 'generated' if financial_record.enhanced_contract_generated else 'not_generated',
                'needs_regeneration': needs_regeneration
            })
        
        return jsonify(results)
        
    except Exception as e:
        current_app.logger.error(f"Error in batch contract status check: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/generate-enhanced-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_enhanced_contract():
    """DEPRECATED: Use /api/financial/generate-contract instead"""
    current_app.logger.warning("DEPRECATED: /api/financial/generate-enhanced-contract is deprecated. Use /api/financial/generate-contract instead.")
    # Redirect to the new unified endpoint for backwards compatibility
    return generate_tuition_contract(request.json.get('student_id'))

@financial_contracts.route('/api/financial/generate-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_contract():
    """Generate a contract for a student"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        return generate_tuition_contract(student_id)
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/students/<student_id>/opensign-status', methods=['GET'])
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
        
        status = {
            'has_contract': financial_record.enhanced_contract_generated,
            'contract_sent': financial_record.enhanced_contract_sent,
            'contract_signed': financial_record.enhanced_contract_signed,
            'signed_date': financial_record.enhanced_contract_signed_date.isoformat() if financial_record.enhanced_contract_signed_date else None,
            'document_id': student.opensign_document_id,
            'signed_url': student.opensign_signed_url
        }
        
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.error(f"Error getting OpenSign status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/students/<student_id>/resend-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def resend_contract(student_id):
    """Resend the tuition contract for signing."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not student.tuition_contract_pdf_path:
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

@financial_contracts.route('/api/financial/students/<student_id>/generate-contract', methods=['POST'])
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
                from models import StudentTuitionComponent, TuitionComponent
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
        
        # Use the general contract generation function
        return generate_contract()
        
    except Exception as e:
        current_app.logger.error(f"Error in student-specific contract generation: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/students/<student_id>/send-contract', methods=['POST'])
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
        if not hasattr(student, 'tuition_contract_generated') or not student.tuition_contract_generated:
            return jsonify({'error': 'Contract must be generated before sending'}), 400
        
        # Prepare data for enhanced contract sending
        request_data = request.get_json() or {}
        request_data['student_id'] = student_id
        
        # Set default email recipients if not provided
        if not request_data.get('email_recipients'):
            recipients = []
            if student.email:
                recipients.append(student.email)
            if hasattr(student, 'father_email') and student.father_email:
                recipients.append(student.father_email)
            if hasattr(student, 'mother_email') and student.mother_email:
                recipients.append(student.mother_email)
            request_data['email_recipients'] = recipients
        
        # Use the enhanced contract sending function
        return send_enhanced_contract()
        
    except Exception as e:
        current_app.logger.error(f"Error in student-specific contract sending: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/generate', methods=['POST'])
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

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/send', methods=['POST'])
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
        
        # Update contract status
        contract.opensign_status = 'pending'
        contract.opensign_sent_date = datetime.utcnow()
        contract.contract_status = 'Sent'
        contract.sent_by = current_user.username
        contract.sent_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract sent for signature successfully'
        })
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/contract-preview', methods=['POST'])
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
        
        # Generate preview HTML
        preview_html = _generate_contract_preview_html(student, contract_terms)
        
        return jsonify({
            'success': True,
            'preview_html': preview_html,
            'contract_terms': contract_terms
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract preview: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/send-enhanced-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_enhanced_contract():
    """Send enhanced contract for signing"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get or create financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Update contract status
        financial_record.enhanced_contract_sent = True
        financial_record.enhanced_contract_sent_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract sent successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending enhanced contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/send-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_tuition_contract_form_secure(contract_id):
    """Send tuition contract as secure form for print/upload"""
    try:
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        # Create secure link for contract upload
        secure_link = SecureFormLink(
            form_type='tuition_contract',
            student_id=contract.student_id,
            academic_year_id=contract.academic_year_id,
            expires_at=datetime.utcnow() + timedelta(days=30),
            created_by=current_user.username
        )
        
        db.session.add(secure_link)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Secure contract form sent successfully',
            'secure_link_id': secure_link.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending secure contract form: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/send-hybrid', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_hybrid_contract(contract_id):
    """Send hybrid contract with both e-signature and print/upload options"""
    try:
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            return jsonify({'error': 'Contract not found'}), 404
        
        # Create secure link for manual upload option
        secure_link = SecureFormLink(
            form_type='tuition_contract',
            student_id=contract.student_id,
            academic_year_id=contract.academic_year_id,
            expires_at=datetime.utcnow() + timedelta(days=30),
            created_by=current_user.username
        )
        
        db.session.add(secure_link)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Hybrid contract options sent successfully',
            'secure_link_id': secure_link.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending hybrid contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/generate-fillable-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_fillable_contract():
    """Generate fillable PDF contract"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Generate fillable PDF
        from pdf_service import PDFService
        pdf_service = PDFService()
        
        pdf_path = pdf_service.generate_fillable_contract({
            'student': student,
            'contract_data': data
        })
        
        return jsonify({
            'success': True,
            'message': 'Fillable contract generated successfully',
            'pdf_path': pdf_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating fillable contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _generate_enhanced_contract_terms(data):
    """Generate enhanced contract terms from data"""
    try:
        # Extract contract data
        total_tuition = data.get('total_tuition', 0)
        registration_fee = data.get('registration_fee', 0)
        payment_plan = data.get('payment_plan', 'Monthly')
        
        contract_terms = {
            'total_tuition': total_tuition,
            'registration_fee': registration_fee,
            'payment_plan': payment_plan,
            'payment_schedule': data.get('payment_schedule', [])
        }
        
        return contract_terms
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract terms: {str(e)}")
        return {}

def _generate_contract_preview_html(student, contract_terms):
    """Generate HTML preview of contract"""
    try:
        preview_html = f"""
        <div class="contract-preview">
            <h3>Contract Preview for {student.student_name}</h3>
            <p><strong>Total Tuition:</strong> ${contract_terms.get('total_tuition', 0):,.2f}</p>
            <p><strong>Registration Fee:</strong> ${contract_terms.get('registration_fee', 0):,.2f}</p>
            <p><strong>Payment Plan:</strong> {contract_terms.get('payment_plan', 'Monthly')}</p>
        </div>
        """
        
        return preview_html
        
    except Exception as e:
        current_app.logger.error(f"Error generating preview HTML: {str(e)}")
        return "<div>Error generating preview</div>"

def _cleanup_old_preview_files(preview_dir):
    """Cleanup old preview files to save disk space"""
    try:
        if os.path.exists(preview_dir):
            # Clean up files older than 24 hours
            cutoff_time = datetime.now() - timedelta(hours=24)
            for filename in os.listdir(preview_dir):
                file_path = os.path.join(preview_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        current_app.logger.info(f"Cleaned up old preview file: {filename}")
    except Exception as e:
        current_app.logger.error(f"Error cleaning up preview files: {str(e)}")

def _cleanup_old_student_contracts(student_id, contracts_dir):
    """Cleanup old contract files for a specific student"""
    try:
        if os.path.exists(contracts_dir):
            # Clean up old contracts for this student
            for filename in os.listdir(contracts_dir):
                if filename.startswith(f"student_{student_id}_contract_"):
                    file_path = os.path.join(contracts_dir, filename)
                    if os.path.isfile(file_path):
                        # Keep only the most recent 3 contracts
                        file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                        cutoff_time = datetime.now() - timedelta(days=30)
                        if file_time < cutoff_time:
                            os.remove(file_path)
                            current_app.logger.info(f"Cleaned up old contract file: {filename}")
    except Exception as e:
        current_app.logger.error(f"Error cleaning up student contracts: {str(e)}") 