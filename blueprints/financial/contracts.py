from flask import Blueprint, render_template, request, jsonify, send_file, current_app, url_for
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
        
        # Generate enhanced contract using ContractStructureService
        from contract_structure_service import ContractStructureService
        from models import DivisionConfig, StudentTuitionComponent, TuitionComponent
        
        # Get student's tuition components for current year
        tuition_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id,
            is_active=True
        ).join(TuitionComponent).all()
        
        # Calculate component amounts
        registration_fee = 0
        tuition_amount = 0
        room_amount = 0
        board_amount = 0
        
        for comp in tuition_components:
            amount = float(comp.amount) if comp.amount else 0
            component_name = comp.component.name.lower()
            
            if 'registration' in component_name:
                registration_fee += amount
            elif 'room' in component_name:
                room_amount += amount
            elif 'board' in component_name:
                board_amount += amount
            else:
                tuition_amount += amount
        
        total_tuition = registration_fee + tuition_amount + room_amount + board_amount
        
        # Generate payment schedule (10 monthly payments from Sept-June)
        monthly_amount = (total_tuition - registration_fee) / 10 if total_tuition > registration_fee else 0
        payment_schedule = []
        months = ['September', 'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June']
        
        for i, month in enumerate(months, 1):
            payment_schedule.append({
                'payment_number': i,
                'due_date': f"{month} {active_year.start_date.year if active_year.start_date else '2025'}",
                'amount': monthly_amount
            })
        
        # Prepare contract data
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        
        contract_data = {
            'student_name': student_name,
            'academic_year': active_year.year_label,
            'division': student.division or 'YOH',
            'registration_fee': registration_fee,
            'tuition_total': total_tuition,
            'tuition_components': [
                {'name': 'Registration Fee', 'final_amount': registration_fee, 'is_enabled': True},
                {'name': 'Tuition', 'final_amount': tuition_amount, 'is_enabled': True},
                {'name': 'Room', 'final_amount': room_amount, 'is_enabled': room_amount > 0},
                {'name': 'Board', 'final_amount': board_amount, 'is_enabled': board_amount > 0}
            ],
            'payment_schedule': payment_schedule,
            'monthly_amount': monthly_amount,
            'school_name': "Yeshiva Ohr Hatzafon" if student.division == 'YOH' else "Yeshiva Zichron Aryeh",
            'school_address': "PO Box 486, Cedarhurst, NY 11516" if student.division == 'YOH' else "123 Torah Way, Brooklyn, NY 11230"
        }
        
        # Generate contract using ContractStructureService
        contract_service = ContractStructureService()
        
        # Create contracts directory
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Generate filename
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"enhanced_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Generate the enhanced contract PDF
        actual_path = contract_service.create_yza_contract(contract_data, output_path=pdf_path, fillable=True)
        
        # Update financial record with actual generated path
        financial_record.enhanced_contract_generated = True
        financial_record.enhanced_contract_generated_date = datetime.utcnow()
        financial_record.enhanced_contract_pdf_path = actual_path
        
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
        
        # Call the actual contract generation logic directly
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get active academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get or create financial record
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id
        ).first()
        
        if not financial_record:
            # Create new financial record if it doesn't exist
            financial_record = FinancialRecord(
                student_id=student_id,
                academic_year_id=active_year.id,
                created_by=current_user.username if current_user else 'system'
            )
            db.session.add(financial_record)
            db.session.flush()  # Get the ID without committing
        
        # Generate enhanced contract using ContractStructureService
        from contract_structure_service import ContractStructureService
        from models import DivisionConfig, StudentTuitionComponent, TuitionComponent
        
        # Get student's tuition components for current year
        tuition_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id,
            is_active=True
        ).join(TuitionComponent).all()
        
        # Calculate component amounts
        registration_fee = 0
        tuition_amount = 0
        room_amount = 0
        board_amount = 0
        
        # If no tuition components exist, use the data from the request
        if not tuition_components:
            registration_fee = float(data.get('registration_fee', 0))
            tuition_amount = float(data.get('total_tuition', 0)) - registration_fee
            # For room and board, we'll use defaults or split the tuition
        else:
            for comp in tuition_components:
                amount = float(comp.amount) if comp.amount else 0
                component_name = comp.component.name.lower()
                
                if 'registration' in component_name:
                    registration_fee += amount
                elif 'room' in component_name:
                    room_amount += amount
                elif 'board' in component_name:
                    board_amount += amount
                else:
                    tuition_amount += amount
        
        total_tuition = registration_fee + tuition_amount + room_amount + board_amount
        
        # Generate payment schedule (10 monthly payments from Sept-June)
        monthly_amount = (total_tuition - registration_fee) / 10 if total_tuition > registration_fee else 0
        payment_schedule = []
        months = ['September', 'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June']
        
        for i, month in enumerate(months, 1):
            payment_schedule.append({
                'payment_number': i,
                'due_date': f"{month} {active_year.start_date.year if active_year.start_date else '2025'}",
                'amount': monthly_amount
            })
        
        # Prepare contract data
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        
        contract_data = {
            'student_name': student_name,
            'academic_year': active_year.year_label,
            'division': student.division or 'YOH',
            'registration_fee': registration_fee,
            'tuition_total': total_tuition,
            'tuition_components': [
                {'name': 'Registration Fee', 'final_amount': registration_fee, 'is_enabled': True},
                {'name': 'Tuition', 'final_amount': tuition_amount, 'is_enabled': True},
                {'name': 'Room', 'final_amount': room_amount, 'is_enabled': room_amount > 0},
                {'name': 'Board', 'final_amount': board_amount, 'is_enabled': board_amount > 0}
            ],
            'payment_schedule': payment_schedule,
            'monthly_amount': monthly_amount,
            'school_name': "Yeshiva Ohr Hatzafon" if student.division == 'YOH' else "Yeshiva Zichron Aryeh",
            'school_address': "PO Box 486, Cedarhurst, NY 11516" if student.division == 'YOH' else "123 Torah Way, Brooklyn, NY 11230"
        }
        
        # Generate contract using ContractStructureService
        contract_service = ContractStructureService()
        
        # Create contracts directory
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Generate filename
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"enhanced_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Generate the enhanced contract PDF
        actual_path = contract_service.create_yza_contract(contract_data, output_path=pdf_path, fillable=True)
        
        # Update financial record with actual generated path
        financial_record.enhanced_contract_generated = True
        financial_record.enhanced_contract_generated_date = datetime.utcnow()
        financial_record.enhanced_contract_pdf_path = actual_path
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Contract generated successfully',
            'contract_path': actual_path
        })
        
    except Exception as e:
        db.session.rollback()
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
        from models import DivisionConfig
        
        # Get division config
        division_config = DivisionConfig.query.filter_by(division=contract.division).first()
        
        # Generate PDF content using static method
        pdf_content = PDFService.generate_tuition_contract_pdf(contract.student, division_config)
        
        # Save PDF to file
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Generate filename
        student_name = contract.student.student_name or f"{contract.student.student_first_name or ''} {contract.student.student_last_name or ''}".strip()
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"tuition_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Write PDF content to file
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        
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
        
        # Generate actual contract PDF and convert to preview
        try:
            # Generate the actual contract that would be sent
            from contract_structure_service import ContractStructureService
            from models import StudentTuitionComponent, TuitionComponent
            
            # Get student's tuition components
            tuition_components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=AcademicYear.query.filter_by(is_active=True).first().id,
                is_active=True
            ).join(TuitionComponent).all()
            
            # Calculate component amounts
            registration_fee = 0
            tuition_amount = 0
            room_amount = 0
            board_amount = 0
            
            if not tuition_components:
                # Use default values for preview
                registration_fee = 1000
                tuition_amount = 10000
                room_amount = 6000
                board_amount = 5000
            else:
                for comp in tuition_components:
                    amount = float(comp.amount) if comp.amount else 0
                    component_name = comp.component.name.lower()
                    
                    if 'registration' in component_name:
                        registration_fee += amount
                    elif 'room' in component_name:
                        room_amount += amount
                    elif 'board' in component_name:
                        board_amount += amount
                    else:
                        tuition_amount += amount
            
            total_tuition = registration_fee + tuition_amount + room_amount + board_amount
            
            # Generate payment schedule
            active_year = AcademicYear.query.filter_by(is_active=True).first()
            monthly_amount = (total_tuition - registration_fee) / 10 if total_tuition > registration_fee else 0
            payment_schedule = []
            months = ['September', 'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June']
            
            for i, month in enumerate(months, 1):
                payment_schedule.append({
                    'payment_number': i,
                    'due_date': f"{month} {active_year.start_date.year if active_year and active_year.start_date else '2025'}",
                    'amount': monthly_amount
                })
            
            # Prepare contract data for preview
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            
            contract_data = {
                'student_name': student_name,
                'academic_year': active_year.year_label if active_year else '2025-2026',
                'division': student.division or 'YOH',
                'registration_fee': registration_fee,
                'tuition_total': total_tuition,
                'tuition_components': [
                    {'name': 'Registration Fee', 'final_amount': registration_fee, 'is_enabled': True},
                    {'name': 'Tuition', 'final_amount': tuition_amount, 'is_enabled': True},
                    {'name': 'Room', 'final_amount': room_amount, 'is_enabled': room_amount > 0},
                    {'name': 'Board', 'final_amount': board_amount, 'is_enabled': board_amount > 0}
                ],
                'payment_schedule': payment_schedule,
                'monthly_amount': monthly_amount,
                'school_name': "Yeshiva Ohr Hatzafon" if student.division == 'YOH' else "Yeshiva Zichron Aryeh",
                'school_address': "PO Box 486, Cedarhurst, NY 11516" if student.division == 'YOH' else "123 Torah Way, Brooklyn, NY 11230"
            }
            
            # Generate HTML representation of the actual contract
            preview_html = _generate_actual_contract_preview_html(contract_data)
            contract_terms = contract_data  # Use the enhanced contract data
            
        except Exception as e:
            current_app.logger.error(f"Error generating actual contract preview: {str(e)}")
            # Fallback to basic terms if contract generation fails
            contract_terms = _generate_enhanced_contract_terms(data)
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
    """Send enhanced contract with hybrid signing options"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        email_recipients = data.get('email_recipients', [])
        email_subject = data.get('email_subject', 'Enhanced Tuition Contract')
        email_message = data.get('email_message', '')
        signing_method = data.get('signing_method', 'hybrid')  # hybrid, digital, upload
        use_opensign = data.get('use_opensign', True)
        use_secure_upload = data.get('use_secure_upload', True)
        expires_hours = data.get('expires_hours', 72)
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        if not email_recipients:
            return jsonify({'error': 'Email recipients are required'}), 400
        
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
        
        # Check if contract has been generated
        if not financial_record.enhanced_contract_generated or not financial_record.enhanced_contract_pdf_path:
            return jsonify({'error': 'Contract must be generated before sending'}), 400
        
        # Create secure upload link if requested
        secure_upload_url = None
        if use_secure_upload and signing_method in ['hybrid', 'upload']:
            try:
                from secure_forms_service import SecureFormsService
                secure_forms = SecureFormsService()
                
                # Create secure link for contract upload
                secure_link = secure_forms.create_secure_link_only(
                    student_id=student_id,
                    form_type='tuition_contract',
                    expires_hours=expires_hours
                )
                
                # Set the contract PDF path for download
                secure_link.pre_filled_pdf_path = financial_record.enhanced_contract_pdf_path
                db.session.commit()
                
                # Generate secure upload URL
                secure_upload_url = url_for('secure_forms.upload_form', token=secure_link.token, _external=True)
                
            except Exception as e:
                current_app.logger.error(f"Error creating secure upload link: {str(e)}")
                if signing_method == 'upload':  # If upload-only, this is critical
                    return jsonify({'error': 'Failed to create secure upload link'}), 500
        
        # Set up digital signing if requested
        opensign_url = None
        if use_opensign and signing_method in ['hybrid', 'digital']:
            try:
                # Placeholder for OpenSign/Dropbox Sign integration
                # This would integrate with the DropboxSignService
                current_app.logger.info(f"Digital signing requested for student {student_id} but not implemented")
                
            except Exception as e:
                current_app.logger.error(f"Error setting up digital signing: {str(e)}")
                if signing_method == 'digital':  # If digital-only, this is critical
                    return jsonify({'error': 'Failed to set up digital signing'}), 500
        
        # Enhanced email template with signing options
        enhanced_message = email_message
        
        # Add signing options to email
        if signing_method == 'hybrid' and (secure_upload_url or opensign_url):
            enhanced_message += """
            
            <div style="margin: 30px 0; padding: 20px; border: 2px solid #e0e0e0; border-radius: 10px;">
                <h3 style="color: #333; margin-bottom: 20px;">Contract Signing Options</h3>
                <p style="margin-bottom: 20px;">Please choose your preferred method to sign the contract:</p>
            """
            
            if opensign_url:
                enhanced_message += f"""
                <div style="margin: 15px 0; padding: 15px; background: #e3f2fd; border-radius: 8px;">
                    <h4 style="color: #1976d2; margin: 0 0 10px 0;">🖊️ Digital Signature</h4>
                    <p style="margin: 0 0 10px 0;">Sign electronically using our secure digital signature platform.</p>
                    <a href="{opensign_url}" style="display: inline-block; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 5px;">Sign Digitally</a>
                </div>
                """
            
            if secure_upload_url:
                enhanced_message += f"""
                <div style="margin: 15px 0; padding: 15px; background: #f3e5f5; border-radius: 8px;">
                    <h4 style="color: #7b1fa2; margin: 0 0 10px 0;">📄 Print & Upload</h4>
                    <p style="margin: 0 0 10px 0;">Download, print, sign by hand, and upload the signed contract.</p>
                    <a href="{secure_upload_url}" style="display: inline-block; padding: 10px 20px; background: #7b1fa2; color: white; text-decoration: none; border-radius: 5px;">Download & Upload</a>
                </div>
                """
            
            enhanced_message += "</div>"
            
        elif signing_method == 'upload' and secure_upload_url:
            enhanced_message += f"""
            
            <div style="margin: 30px 0; padding: 20px; background: #f3e5f5; border-radius: 10px;">
                <h3 style="color: #7b1fa2;">📄 Contract Download & Upload</h3>
                <p>Please download the contract, print it, sign it, and upload the signed copy using the secure link below.</p>
                <a href="{secure_upload_url}" style="display: inline-block; margin-top: 15px; padding: 12px 24px; background: #7b1fa2; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">Download Contract & Upload Signed Copy</a>
            </div>
            """
            
        elif signing_method == 'digital' and opensign_url:
            enhanced_message += f"""
            
            <div style="margin: 30px 0; padding: 20px; background: #e3f2fd; border-radius: 10px;">
                <h3 style="color: #1976d2;">🖊️ Digital Contract Signing</h3>
                <p>Please sign the contract electronically using our secure digital signature platform.</p>
                <a href="{opensign_url}" style="display: inline-block; margin-top: 15px; padding: 12px 24px; background: #1976d2; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">Sign Contract Digitally</a>
            </div>
            """
        
        # Send enhanced email
        from flask_mail import Message
        from extensions import mail
        
        msg = Message(
            subject=email_subject,
            sender=('Financial Office', current_app.config.get('MAIL_DEFAULT_SENDER')),
            recipients=email_recipients,
            html=enhanced_message,
            reply_to=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        
        # Attach the contract PDF
        if os.path.exists(financial_record.enhanced_contract_pdf_path):
            with open(financial_record.enhanced_contract_pdf_path, 'rb') as f:
                msg.attach(
                    filename=f'Tuition_Contract_{student.student_name or "Student"}_{active_year.year_label}.pdf',
                    content_type='application/pdf',
                    data=f.read()
                )
        
        mail.send(msg)
        
        # Update contract status only after successful email sending
        financial_record.enhanced_contract_sent = True
        financial_record.enhanced_contract_sent_date = datetime.utcnow()
        
        db.session.commit()
        
        current_app.logger.info(f"Enhanced contract email sent successfully to {email_recipients} for student {student_id} with signing method: {signing_method}")
        
        return jsonify({
            'success': True,
            'message': 'Contract sent successfully',
            'signing_method': signing_method,
            'secure_upload_url': secure_upload_url,
            'opensign_url': opensign_url
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
        from models import DivisionConfig
        
        # Get division config
        division_config = DivisionConfig.query.filter_by(division=student.division).first()
        
        # Generate PDF content using static method
        pdf_content = PDFService.generate_tuition_contract_pdf(student, division_config)
        
        # Save PDF to file
        contracts_dir = os.path.join(os.getcwd(), 'contracts')
        if not os.path.exists(contracts_dir):
            os.makedirs(contracts_dir)
        
        # Generate filename
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"fillable_contract_{clean_name}_{timestamp}.pdf"
        pdf_path = os.path.join(contracts_dir, filename)
        
        # Write PDF content to file
        with open(pdf_path, 'wb') as f:
            f.write(pdf_content)
        
        return jsonify({
            'success': True,
            'message': 'Fillable contract generated successfully',
            'pdf_path': pdf_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating fillable contract: {str(e)}")
        return jsonify({'error': str(e)}), 500

def _generate_enhanced_contract_terms(data):
    """Generate enhanced contract terms with actual student data"""
    try:
        student_id = data.get('student_id')
        
        # Get student and financial data
        from models import AcademicYear, StudentTuitionComponent, TuitionComponent
        
        student = Student.query.get(student_id)
        if not student:
            return {}
            
        # Get active academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        if not active_year:
            return {}
        
        # Get student's tuition components
        tuition_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=active_year.id,
            is_active=True
        ).join(TuitionComponent).all()
        
        # Calculate component amounts
        registration_fee = 0
        tuition_amount = 0
        room_amount = 0
        board_amount = 0
        
        for comp in tuition_components:
            amount = float(comp.amount) if comp.amount else 0
            component_name = comp.component.name.lower()
            
            if 'registration' in component_name:
                registration_fee += amount
            elif 'room' in component_name:
                room_amount += amount
            elif 'board' in component_name:
                board_amount += amount
            else:
                tuition_amount += amount
        
        total_tuition = registration_fee + tuition_amount + room_amount + board_amount
        
        # Generate payment schedule
        monthly_amount = (total_tuition - registration_fee) / 10 if total_tuition > registration_fee else 0
        payment_schedule = []
        months = ['September', 'October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June']
        
        for i, month in enumerate(months, 1):
            payment_schedule.append({
                'payment_number': i,
                'due_date': f"{month} {active_year.start_date.year if active_year.start_date else '2025'}",
                'amount': monthly_amount,
                'description': f"Payment {i}"
            })
        
        contract_terms = {
            'total_tuition': total_tuition,
            'registration_fee': registration_fee,
            'tuition_amount': tuition_amount,
            'room_amount': room_amount,
            'board_amount': board_amount,
            'monthly_amount': monthly_amount,
            'payment_plan': 'Monthly (10 payments)',
            'payment_schedule': payment_schedule,
            'academic_year': active_year.year_label,
            'tuition_components': {
                'Registration Fee': registration_fee,
                'Tuition': tuition_amount,
                'Room': room_amount,
                'Board': board_amount,
                'TOTAL': total_tuition
            }
        }
        
        return contract_terms
        
    except Exception as e:
        current_app.logger.error(f"Error generating enhanced contract terms: {str(e)}")
        return {}

def _generate_contract_preview_html(student, contract_terms):
    """Generate HTML preview of enhanced contract with payment schedules"""
    try:
        # Get student's division for branding
        division = student.division or 'YZA'
        school_name = "Yeshiva Zichron Aryeh" if division == 'YZA' else "Yeshiva Ohr Hatzafon"
        
        # Get payment schedule if available
        payment_schedule = contract_terms.get('payment_schedule', [])
        total_tuition = contract_terms.get('total_tuition', 0)
        registration_fee = contract_terms.get('registration_fee', 0)
        payment_plan = contract_terms.get('payment_plan', 'Monthly')
        
        # Calculate monthly amount if not provided
        if payment_schedule:
            monthly_amount = payment_schedule[0].get('amount', 0) if payment_schedule else 0
        else:
            # Calculate basic monthly payment (assuming 10 months)
            monthly_amount = (total_tuition - registration_fee) / 10 if total_tuition > registration_fee else 0
        
        # Generate enhanced contract preview
        preview_html = f"""
        <div class="contract-preview" style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px; background: #fff;">
            <!-- Header -->
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #2c3e50; margin-bottom: 10px;">{school_name}</h2>
                <h3 style="color: #34495e; margin-bottom: 5px;">Tuition Contract - Academic Year 2024-2025</h3>
                <p style="color: #666; margin: 0;">Student: <strong>{student.student_name}</strong></p>
            </div>
            
            <!-- Financial Summary -->
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h4 style="color: #495057; margin-bottom: 15px; border-bottom: 2px solid #dee2e6; padding-bottom: 5px;">Financial Summary</h4>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <span><strong>Total Annual Tuition:</strong></span>
                    <span>${total_tuition:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <span><strong>Registration Fee:</strong></span>
                    <span>${registration_fee:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 10px; padding-top: 10px; border-top: 1px solid #dee2e6;">
                    <span><strong>Payment Plan:</strong></span>
                    <span>{payment_plan}</span>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 16px; font-weight: bold; color: #2c3e50;">
                    <span>Monthly Payment Amount:</span>
                    <span>${monthly_amount:,.2f}</span>
                </div>
            </div>
            
            <!-- Payment Schedule -->
            <div style="margin-bottom: 25px;">
                <h4 style="color: #495057; margin-bottom: 15px; border-bottom: 2px solid #dee2e6; padding-bottom: 5px;">Payment Schedule</h4>
        """
        
        if payment_schedule:
            # Show actual payment schedule
            preview_html += '<div style="background: #fff; border: 1px solid #dee2e6; border-radius: 5px;">'
            for i, payment in enumerate(payment_schedule):
                bg_color = "#f8f9fa" if i % 2 == 0 else "#fff"
                preview_html += f'''
                <div style="padding: 10px 15px; background: {bg_color}; display: flex; justify-content: space-between; align-items: center;">
                    <span><strong>{payment.get("description", f"Payment {i+1}")}</strong></span>
                    <span style="color: #28a745; font-weight: bold;">${payment.get("amount", 0):,.2f}</span>
                    <span style="color: #666; font-size: 14px;">{payment.get("due_date", "TBD")}</span>
                </div>
                '''
            preview_html += '</div>'
        else:
            # Show standard 10-month payment schedule
            preview_html += '''
                <div style="background: #fff; border: 1px solid #dee2e6; border-radius: 5px;">
                    <div style="padding: 15px; text-align: center; color: #666;">
                        <p><strong>Standard 10-Month Payment Plan</strong></p>
                        <p>Registration Fee due upon enrollment</p>
                        <p>Monthly payments from September through June</p>
                    </div>
                </div>
            '''
        
        preview_html += '''
            </div>
            
            <!-- Contract Terms -->
            <div style="margin-bottom: 25px;">
                <h4 style="color: #495057; margin-bottom: 15px; border-bottom: 2px solid #dee2e6; padding-bottom: 5px;">Contract Terms</h4>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; font-size: 14px; line-height: 1.6;">
                    <ul style="margin: 0; padding-left: 20px;">
                        <li>This contract is for the 2024-2025 academic year</li>
                        <li>All payments are due by the 1st of each month</li>
                        <li>Late fees may apply for payments received after the 10th</li>
                        <li>Tuition is non-refundable after the start of the academic year</li>
                        <li>This contract must be signed and returned within 30 days</li>
                    </ul>
                </div>
            </div>
            
            <!-- Signing Options Preview -->
            <div style="margin-bottom: 20px; padding: 20px; background: #e3f2fd; border-radius: 8px; text-align: center;">
                <h4 style="color: #1976d2; margin-bottom: 15px;">Signing Options</h4>
                <p style="color: #666; margin-bottom: 15px;">You will have multiple ways to sign this contract:</p>
                <div style="display: flex; gap: 20px; justify-content: center;">
                    <div style="background: #fff; padding: 15px; border-radius: 5px; flex: 1; max-width: 200px;">
                        <div style="color: #1976d2; font-size: 24px; margin-bottom: 10px;">🖊️</div>
                        <strong>Digital Signature</strong>
                        <p style="font-size: 12px; color: #666; margin: 5px 0 0 0;">Sign electronically online</p>
                    </div>
                    <div style="background: #fff; padding: 15px; border-radius: 5px; flex: 1; max-width: 200px;">
                        <div style="color: #7b1fa2; font-size: 24px; margin-bottom: 10px;">📄</div>
                        <strong>Print & Upload</strong>
                        <p style="font-size: 12px; color: #666; margin: 5px 0 0 0;">Print, sign, and upload</p>
                    </div>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="text-align: center; padding-top: 20px; border-top: 1px solid #dee2e6; color: #666; font-size: 12px;">
                <p>This is a preview of your tuition contract. The actual contract will include additional terms and conditions.</p>
                <p>For questions, contact the Financial Office at <strong>aderdik@priority-1.org</strong></p>
            </div>
        </div>
        '''
        
        return preview_html
        
    except Exception as e:
        current_app.logger.error(f"Error generating enhanced contract preview HTML: {str(e)}")
        return f"<div class='alert alert-danger'>Error generating contract preview: {str(e)}</div>"

def _generate_actual_contract_preview_html(contract_data):
    """Generate HTML preview that matches the actual PDF contract content"""
    try:
        student_name = contract_data.get('student_name', 'Student Name')
        academic_year = contract_data.get('academic_year', '2025-2026')
        school_name = contract_data.get('school_name', 'Yeshiva Ohr Hatzafon')
        registration_fee = contract_data.get('registration_fee', 0)
        tuition_total = contract_data.get('tuition_total', 0)
        monthly_amount = contract_data.get('monthly_amount', 0)
        tuition_components = contract_data.get('tuition_components', [])
        payment_schedule = contract_data.get('payment_schedule', [])
        
        # Generate HTML that looks like the actual contract PDF
        preview_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: white; border: 1px solid #ccc;">
            <!-- PAGE 1 - Contract Terms -->
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #2c3e50; font-size: 24px; margin-bottom: 10px;">{school_name.upper()}</h1>
                <h2 style="color: #34495e; font-size: 18px; margin-bottom: 20px;">ENROLLMENT CONTRACT</h2>
            </div>
            
            <div style="margin-bottom: 20px;">
                <p><strong>Student Name:</strong> {student_name}</p>
                <p><strong>Academic Year:</strong> {academic_year}</p>
            </div>
            
            <div style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border: 1px solid #dee2e6;">
                <h3 style="color: #495057; margin-bottom: 10px;">PAYMENT TERMS</h3>
                <p><strong>Registration Fee:</strong> ${registration_fee:,.2f}</p>
                <p style="font-style: italic; color: #666;">Use payment method below</p>
                <p style="margin-top: 15px;"><strong>TUITION TOTAL:</strong> ${tuition_total:,.2f}</p>
                <p style="font-style: italic; color: #666;">See payment schedule and breakdown details on page 2</p>
            </div>
            
            <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #dee2e6;">
                <h3 style="color: #495057; margin-bottom: 15px;">PAYMENT METHOD</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 15px;">
                    <div>
                        <p><strong>☐ Credit Card</strong></p>
                        <p style="font-size: 12px; margin: 5px 0;">Card Number: _______________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Cardholder Name: ___________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Exp Date: _______ CVV: _______</p>
                        <p style="font-size: 12px; margin: 5px 0;">Billing ZIP: ____________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Charge Date: ___________</p>
                    </div>
                    <div>
                        <p><strong>☐ ACH/Bank Transfer</strong></p>
                        <p style="font-size: 12px; margin: 5px 0;">Routing Number: ____________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Account Number: ____________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Account Holder: ____________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Check Debit Date: __________________</p>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <p><strong>☐ Check enclosed</strong></p>
                        <p><strong>☐ I will mail 10 post-dated checks in the amount of ${monthly_amount:,.2f} each</strong></p>
                    </div>
                    <div>
                        <p><strong>☐ Third Party Payer</strong></p>
                        <p style="font-size: 12px; margin: 5px 0;">Name: _____________________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Relationship: ______________________</p>
                        <p style="font-size: 12px; margin: 5px 0;">Contact Information: _______________</p>
                    </div>
                </div>
            </div>
            
            <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #dee2e6;">
                <h3 style="color: #495057; margin-bottom: 10px;">AGREEMENT</h3>
                <p style="font-size: 14px; line-height: 1.4;">I hereby enroll my son for the {academic_year} academic year in {school_name}. I understand that this is a binding obligation toward the Yeshiva and that I will be responsible for satisfaction of his tuition obligation as well as all costs incurred by my son, including damage caused to the Yeshiva property. With my signature I hereby accept the terms of this contract and authorize all payments required herein.</p>
                <div style="margin-top: 20px; display: flex; justify-content: space-between;">
                    <div>
                        <p>Parent/Guardian Signature: _________________________</p>
                    </div>
                    <div>
                        <p>Date: _______________</p>
                    </div>
                </div>
            </div>
            
            <!-- PAGE BREAK INDICATOR -->
            <div style="margin: 40px 0; text-align: center; padding: 10px; background: #f0f0f0; border-top: 2px dashed #ccc; border-bottom: 2px dashed #ccc;">
                <strong>— PAGE 2 —</strong>
            </div>
            
            <!-- PAGE 2 - Breakdown and Schedule -->
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #2c3e50; font-size: 18px;">TUITION BREAKDOWN & PAYMENT SCHEDULE</h2>
                <p><strong>Student:</strong> {student_name}</p>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #495057; margin-bottom: 10px;">TUITION COMPONENTS</h3>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Component</th>
                            <th style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        # Add tuition components
        total_components = 0
        for component in tuition_components:
            if component.get('is_enabled', True):
                name = component.get('name', '')
                amount = component.get('final_amount', 0)
                total_components += amount
                preview_html += f"""
                        <tr>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">{name}</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">{amount:,.2f}</td>
                        </tr>
                """
        
        preview_html += f"""
                        <tr style="background: #f8f9fa; font-weight: bold;">
                            <td style="padding: 8px; border: 1px solid #dee2e6;">TOTAL</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">{total_components:,.2f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div style="margin-bottom: 25px;">
                <h3 style="color: #495057; margin-bottom: 10px;">PAYMENT SCHEDULE</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 8px; border: 1px solid #dee2e6;">Payment #</th>
                            <th style="padding: 8px; border: 1px solid #dee2e6;">Due Date</th>
                            <th style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">Registration</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">At Contract Signing</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">{registration_fee:,.2f}</td>
                        </tr>
        """
        
        # Add payment schedule rows
        for payment in payment_schedule:
            payment_num = payment.get('payment_number', '')
            due_date = payment.get('due_date', '')
            amount = payment.get('amount', 0)
            preview_html += f"""
                        <tr>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">{payment_num}</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6;">{due_date}</td>
                            <td style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">{amount:,.2f}</td>
                        </tr>
            """
        
        preview_html += f"""
                    </tbody>
                </table>
            </div>
            
            <div style="margin-top: 30px; padding: 15px; background: #f8f9fa; border: 1px solid #dee2e6;">
                <h4 style="color: #495057; margin-bottom: 10px;">IMPORTANT NOTES</h4>
                <ul style="font-size: 14px; line-height: 1.4; margin: 0; padding-left: 20px;">
                    <li>Please do not modify this contract in any way</li>
                    <li>If you have any questions or concerns please contact the financial office</li>
                    <li>Checks should be mailed to {school_name}, {contract_data.get('school_address', 'PO Box 486, Cedarhurst, NY 11516')}</li>
                </ul>
            </div>
        </div>
        """
        
        return preview_html
        
    except Exception as e:
        current_app.logger.error(f"Error generating actual contract preview HTML: {str(e)}")
        return f"<div class='alert alert-danger'>Error generating contract preview: {str(e)}</div>"

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