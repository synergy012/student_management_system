from flask import Blueprint, render_template, request, jsonify, current_app, send_file, url_for
from flask_login import login_required, current_user
from models import (Student, TuitionRecord, AcademicYear, db, FinancialRecord, 
                   TuitionContract, DivisionFinancialConfig, FormUploadLog, SecureFormLink,
                   DivisionConfig, EmailTemplate, StudentTuitionComponent, TuitionComponent,
                   DivisionTuitionComponent)
from utils.decorators import permission_required
from datetime import datetime, date
from decimal import Decimal
import traceback
import os

financial_contracts = Blueprint('financial_contracts', __name__)

@financial_contracts.route('/api/students/<student_id>/generate-tuition-contract', methods=['POST'])
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

@financial_contracts.route('/api/students/<student_id>/tuition-contract/download')
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

@financial_contracts.route('/api/students/<student_id>/resend-contract', methods=['POST'])
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
        with current_app.test_request_context('/api/financial/generate-contract', 
                                            method='POST', 
                                            json=request_data):
            # Import here to avoid circular imports
            from blueprints.financial.core import generate_contract
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

def _generate_enhanced_contract_terms(data):
    """Generate enhanced contract terms from request data"""
    try:
        # Extract payment schedule data
        payment_start_month = int(data.get('payment_start_month', 9))  # September
        payment_start_year = int(data.get('payment_start_year', datetime.now().year))
        payment_end_month = int(data.get('payment_end_month', 6))      # June
        payment_end_year = int(data.get('payment_end_year', datetime.now().year + 1))
        
        # Calculate monthly payment amounts
        total_tuition = float(data.get('total_tuition', 0))
        registration_fee = float(data.get('registration_fee', 0))
        registration_fee_option = data.get('registration_fee_option', 'upfront')
        
        # Calculate number of payments
        num_payments = ((payment_end_year - payment_start_year) * 12 + 
                       (payment_end_month - payment_start_month + 1))
        
        # Adjust for registration fee
        if registration_fee_option == 'upfront':
            monthly_amount = (total_tuition - registration_fee) / max(num_payments, 1)
        else:
            monthly_amount = total_tuition / max(num_payments, 1)
        
        # Generate payment schedule
        payment_schedule = []
        current_month = payment_start_month
        current_year = payment_start_year
        
        for i in range(num_payments):
            payment_date = datetime(current_year, current_month, 1)
            
            # Special handling for registration fee
            if i == 0 and registration_fee_option == 'with_first':
                amount = monthly_amount + registration_fee
                payment_schedule.append({
                    'month': payment_date.strftime('%B'),
                    'year': current_year,
                    'amount': amount,
                    'includes_registration': True
                })
            else:
                payment_schedule.append({
                    'month': payment_date.strftime('%B'),
                    'year': current_year,
                    'amount': monthly_amount,
                    'includes_registration': False
                })
            
            # Move to next month
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        
        return {
            'total_tuition': total_tuition,
            'registration_fee': registration_fee,
            'registration_fee_option': registration_fee_option,
            'payment_start_month': payment_start_month,
            'payment_start_year': payment_start_year,
            'payment_end_month': payment_end_month,
            'payment_end_year': payment_end_year,
            'num_payments': num_payments,
            'monthly_amount': monthly_amount,
            'payment_schedule': payment_schedule
        }
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract terms: {str(e)}")
        return {
            'total_tuition': 0,
            'registration_fee': 0,
            'registration_fee_option': 'upfront',
            'payment_schedule': []
        }

@financial_contracts.route('/api/financial/send-enhanced-contract', methods=['POST'])
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
        
        # Determine email content
        if custom_subject and custom_message:
            # Use custom content provided from the editable preview
            email_subject = custom_subject
            email_message = custom_message
            current_app.logger.info(f"Using custom email content from editable preview")
        else:
            # Use email template system if available
            if email_template:
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
        
        # Send email with contract
        from email_service import EmailService
        email_service = EmailService()
        
        # Prepare attachments
        attachments = []
        if financial_record.enhanced_contract_pdf_path and os.path.exists(financial_record.enhanced_contract_pdf_path):
            attachments.append({
                'filename': f'enrollment_contract_{student.student_name}.pdf',
                'path': financial_record.enhanced_contract_pdf_path
            })
        
        # Send the email
        try:
            email_result = email_service.send_email(
                to_addresses=email_recipients,
                subject=email_subject,
                body=email_message,
                attachments=attachments,
                is_html=True
            )
            
            if email_result.get('success'):
                # Update financial record
                financial_record.enhanced_contract_sent = True
                financial_record.enhanced_contract_sent_date = datetime.utcnow()
                financial_record.updated_by = current_user.username
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Contract sent successfully'
                })
            else:
                return jsonify({
                    'error': email_result.get('error', 'Failed to send email')
                }), 500
                
        except Exception as e:
            current_app.logger.error(f"Error sending contract email: {str(e)}")
            return jsonify({'error': f'Failed to send email: {str(e)}'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error sending enhanced contract: {str(e)}")
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
        
        # Use the new ContractStructureService for preview
        current_app.logger.info("Using ContractStructureService for preview generation")
        from contract_structure_service import ContractStructureService
        
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
        
        # Generate the preview using contract service
        preview_url = pdf_service.generate_contract_preview(
            student_data=student_data,
            contract_data={
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
        )
        
        return jsonify({
            'success': True,
            'preview_url': preview_url,
            'contract_terms': contract_terms,
            'total_tuition': total_tuition,
            'final_amount': total_tuition - data.get('financial_aid_amount', 0)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating contract preview: {str(e)}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@financial_contracts.route('/api/financial/generate-fillable-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def generate_fillable_contract():
    """DEPRECATED: Use /api/financial/generate-contract instead"""
    current_app.logger.warning("DEPRECATED: /api/financial/generate-fillable-contract is deprecated. Use /api/financial/generate-contract instead.")
    # Redirect to the new unified endpoint for backwards compatibility
    return generate_contract()

@financial_contracts.route('/api/financial/generate-contract', methods=['POST'])
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

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/send-form', methods=['POST'])
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

@financial_contracts.route('/api/tuition-contracts/<int:contract_id>/send-hybrid', methods=['POST'])
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
            'message': 'Hybrid contract options sent successfully',
            'secure_link_id': secure_link.id,
            'opensign_document_id': contract.opensign_document_id,
            'expires_at': secure_link.expires_at.isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending hybrid contract: {str(e)}")
        return jsonify({'error': str(e)}), 500
