"""
Secure Forms Service - Handle pre-filled form generation and secure uploads
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from flask import current_app, url_for
from models import SecureFormLink, FormUploadLog, Student, FinancialAidApplication, TuitionContract, DivisionFinancialConfig, db
from email_service import EmailService
from storage_service import StorageService

class SecureFormsService:
    def __init__(self):
        self.upload_folder = os.path.join(current_app.root_path, 'uploads', 'secure_forms')
        self.forms_folder = os.path.join(current_app.root_path, 'generated_forms')
        self.storage_service = StorageService()
        
        # Ensure directories exist (for local storage and generated forms)
        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.forms_folder, exist_ok=True)
    
    def generate_financial_aid_form(self, application_id):
        """Generate a pre-filled financial aid application form"""
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            raise ValueError("Application not found")
        
        # Create filename
        filename = f"financial_aid_{application.division}_{application.student_id}_{application_id}.pdf"
        filepath = os.path.join(self.forms_folder, filename)
        
        # Create PDF using ReportLab
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1  # Center
        )
        
        story.append(Paragraph(f"{application.division} Financial Aid Application", title_style))
        story.append(Spacer(1, 20))
        
        # Student Information Section
        story.append(Paragraph("Student Information", styles['Heading2']))
        student_data = [
            ['Student Name:', application.student.student_name],
            ['Division:', application.division],
            ['Student ID:', application.student_id],
            ['Application Date:', application.application_date.strftime('%B %d, %Y')],
        ]
        
        student_table = Table(student_data, colWidths=[2*inch, 4*inch])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(student_table)
        story.append(Spacer(1, 20))
        
        # Build PDF
        doc.build(story)
        
        return filepath
    
    def generate_tuition_contract(self, contract_id):
        """Generate a pre-filled tuition contract"""
        contract = TuitionContract.query.get(contract_id)
        if not contract:
            raise ValueError("Contract not found")
        
        # Get division config for branding
        config = DivisionFinancialConfig.query.filter_by(division=contract.division).first()
        
        # Create filename
        filename = f"tuition_contract_{contract.division}_{contract.student_id}_{contract_id}.pdf"
        filepath = os.path.join(self.forms_folder, filename)
        
        # Create PDF
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        )
        
        story.append(Paragraph(f"{contract.division} Tuition Contract", title_style))
        story.append(Paragraph(f"Academic Year {contract.academic_year.year_label}", styles['Heading2']))
        story.append(Spacer(1, 20))
        
        # Contract Details
        story.append(Paragraph("Contract Information", styles['Heading2']))
        contract_data = [
            ['Student Name:', contract.student.student_name],
            ['Student ID:', contract.student_id],
            ['Division:', contract.division],
            ['Contract Date:', contract.contract_date.strftime('%B %d, %Y')],
            ['Contract Type:', contract.contract_type or 'Standard'],
        ]
        
        contract_table = Table(contract_data, colWidths=[2*inch, 4*inch])
        contract_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(contract_table)
        story.append(Spacer(1, 20))
        
        # Financial Terms
        story.append(Paragraph("Financial Terms", styles['Heading2']))
        financial_data = [
            ['Base Tuition Amount:', f"${contract.tuition_amount:,.2f}"],
            ['Discount Amount:', f"${contract.discount_amount:,.2f}" if contract.discount_amount > 0 else "N/A"],
            ['Financial Aid Amount:', f"${contract.financial_aid_amount:,.2f}" if contract.financial_aid_amount > 0 else "N/A"],
            ['Final Tuition Amount:', f"${contract.final_tuition_amount:,.2f}"],
            ['Payment Plan:', contract.payment_plan],
        ]
        
        if contract.first_payment_due:
            financial_data.append(['First Payment Due:', contract.first_payment_due.strftime('%B %d, %Y')])
        
        financial_table = Table(financial_data, colWidths=[2*inch, 4*inch])
        financial_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(financial_table)
        story.append(Spacer(1, 20))
        
        # Payment Schedule
        if contract.payment_schedule:
            story.append(Paragraph("Payment Schedule", styles['Heading2']))
            schedule_data = [['Due Date', 'Amount', 'Description']]
            
            for payment in contract.payment_schedule:
                schedule_data.append([
                    payment.get('due_date', ''),
                    f"${payment.get('amount', 0):,.2f}",
                    payment.get('description', '')
                ])
            
            schedule_table = Table(schedule_data, colWidths=[2*inch, 1.5*inch, 2.5*inch])
            schedule_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(schedule_table)
            story.append(Spacer(1, 20))
        
        # Signature Section
        story.append(Paragraph("Signatures Required", styles['Heading2']))
        signature_text = f"""
        This contract requires signatures from:
        • {contract.parent1_name} ({contract.parent1_email})
        """
        
        if contract.parent2_email:
            signature_text += f"• {contract.parent2_name} ({contract.parent2_email})"
        
        story.append(Paragraph(signature_text, styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Instructions
        story.append(Paragraph("Instructions", styles['Heading2']))
        instructions = """
        Please review this contract carefully. If you agree to the terms:
        1. Print and sign the contract
        2. Upload the signed contract through the secure link provided
        3. You will receive a confirmation once we receive your signed contract
        
        If you have any questions, please contact the financial office.
        """
        story.append(Paragraph(instructions, styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        return filepath
    
    def _create_secure_link(self, student_id, form_type, form_id=None, expires_hours=72):
        """Core secure link creation logic without email sending"""
        student = Student.query.get(student_id)
        if not student:
            raise ValueError("Student not found")
        
        # Set up form metadata
        if form_type == 'financial_aid_app':
            title = f"{student.division} Financial Aid Application"
            description = "Please review, complete, and upload your financial aid application."
        elif form_type == 'tuition_contract':
            title = f"{student.division} Tuition Contract"
            description = "Please review, sign, and upload your tuition contract."
        else:
            raise ValueError("Invalid form type")
        
        # Create secure link
        secure_link = SecureFormLink.create_form_link(
            student_id=student_id,
            form_type=form_type,
            form_id=form_id,
            division=student.division,
            title=title,
            description=description,
            expires_hours=expires_hours
        )
        
        # Enable multiple uploads for financial aid applications
        if form_type == 'financial_aid_app':
            secure_link.allow_multiple_files = True
            secure_link.max_uses = 10  # Allow up to 10 document uploads
        
        return secure_link
    
    def create_secure_link_only(self, student_id, form_type, form_id=None, expires_hours=72):
        """Create secure link without sending email - for use when email will be sent separately"""
        # Create the secure link
        secure_link = self._create_secure_link(student_id, form_type, form_id, expires_hours)
        
        # Handle pre-filled PDF for tuition contracts
        if form_type == 'tuition_contract' and form_id:
            try:
                contract = TuitionContract.query.get(form_id)
                if contract:
                    # Get the enhanced contract PDF path from the related financial record
                    from models import FinancialRecord, AcademicYear
                    
                    academic_year_id = getattr(contract, 'academic_year_id', None)
                    if not academic_year_id:
                        active_year = AcademicYear.query.filter_by(is_active=True).first()
                        academic_year_id = active_year.id if active_year else None
                    
                    if academic_year_id:
                        financial_record = FinancialRecord.query.filter_by(
                            student_id=contract.student_id,
                            academic_year_id=academic_year_id
                        ).first()
                        
                        # Try enhanced contract PDF first
                        if (financial_record and 
                            hasattr(financial_record, 'enhanced_contract_pdf_path') and 
                            financial_record.enhanced_contract_pdf_path and
                            os.path.exists(financial_record.enhanced_contract_pdf_path)):
                            secure_link.pre_filled_pdf_path = financial_record.enhanced_contract_pdf_path
                        # Fallback to contract PDF
                        elif (hasattr(contract, 'contract_pdf_path') and 
                              contract.contract_pdf_path and
                              os.path.exists(contract.contract_pdf_path)):
                            secure_link.pre_filled_pdf_path = contract.contract_pdf_path
                        
                        db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Error setting up PDF for secure link: {str(e)}")
        
        return secure_link

    def create_secure_link_and_send_email(self, student_id, form_type, form_id=None, 
                                        expires_hours=72, recipient_email=None):
        """Create secure link and send email with form"""
        student = Student.query.get(student_id)
        if not student:
            raise ValueError("Student not found")
        
        # Create the secure link using shared logic
        secure_link = self._create_secure_link(student_id, form_type, form_id, expires_hours)
        
        # Handle pre-filled forms
        form_path = None
        if form_type == 'financial_aid_app':
            form_path = self.generate_financial_aid_form(form_id)
        elif form_type == 'tuition_contract' and form_id:
            # Use same logic as create_secure_link_only for consistency
            try:
                contract = TuitionContract.query.get(form_id)
                if contract:
                    from models import FinancialRecord, AcademicYear
                    
                    academic_year_id = getattr(contract, 'academic_year_id', None)
                    if not academic_year_id:
                        active_year = AcademicYear.query.filter_by(is_active=True).first()
                        academic_year_id = active_year.id if active_year else None
                    
                    if academic_year_id:
                        financial_record = FinancialRecord.query.filter_by(
                            student_id=student_id,
                            academic_year_id=academic_year_id
                        ).first()
                        
                        if (financial_record and 
                            hasattr(financial_record, 'enhanced_contract_pdf_path') and 
                            financial_record.enhanced_contract_pdf_path and
                            os.path.exists(financial_record.enhanced_contract_pdf_path)):
                            form_path = financial_record.enhanced_contract_pdf_path
                        elif (hasattr(contract, 'contract_pdf_path') and 
                              contract.contract_pdf_path and
                              os.path.exists(contract.contract_pdf_path)):
                            form_path = contract.contract_pdf_path
            except Exception as e:
                current_app.logger.error(f"Error setting up tuition contract form: {str(e)}")
        
        # Store the pre-filled form path
        if form_path:
            secure_link.pre_filled_pdf_path = form_path
            db.session.commit()
        
        # Send email notification with secure upload link
        try:
            email_service = EmailService()
            
            # Determine recipient email
            if not recipient_email:
                # Default to father's email, then mother's email
                if student.father_email:
                    recipient_email = student.father_email
                elif student.mother_email:
                    recipient_email = student.mother_email
                else:
                    current_app.logger.warning(f"No email address found for student {student_id}")
                    return secure_link  # Return without sending email
            
            # Create email content based on form type
            if form_type == 'financial_aid_app':
                subject = f"{student.division} Financial Aid Application - Secure Upload Link"
                
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0d6efd;">{student.division} Financial Aid Application</h2>
                    
                    <p>Dear {student.student_name} Family,</p>
                    
                    <p>Please use the secure link below to upload your financial aid application and supporting documents:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{url_for('secure_forms.upload_form', token=secure_link.token, _external=True)}" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                            Upload Financial Aid Documents
                        </a>
                    </div>
                    
                    <h4>What to Upload:</h4>
                    <ul>
                        <li>Completed Financial Aid Application</li>
                        <li>Tax Returns (most recent year)</li>
                        <li>W-2 Forms</li>
                        <li>Bank Statements</li>
                        <li>Any other supporting financial documents</li>
                    </ul>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                        <h4 style="margin-top: 0;">Important Information:</h4>
                        <p><strong>Upload Link Expires:</strong> {secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                        <p><strong>Multiple Files:</strong> You can upload multiple documents using this same link</p>
                        <p><strong>File Types:</strong> PDF, DOC, DOCX, JPG, PNG (Max 10MB each)</p>
                    </div>
                    
                    <p>If you have any questions or technical difficulties, please contact our office.</p>
                    
                    <p>Best regards,<br>
                    Financial Aid Office</p>
                </div>
                """
                
            elif form_type == 'tuition_contract':
                subject = f"{student.division} Tuition Contract - Print & Upload Instructions"
                
                # Get download URL if pre-filled form exists
                download_url = url_for('secure_forms.download_form', token=secure_link.token, _external=True) if secure_link.pre_filled_pdf_path else None
                upload_url = url_for('secure_forms.upload_form', token=secure_link.token, _external=True)
                
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0d6efd;">{student.division} Tuition Contract</h2>
                    
                    <p>Dear {student.student_name} Family,</p>
                    
                    <p>Your tuition contract is ready for signature. Please follow these steps to complete the print & upload process:</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #495057; margin-top: 0;">
                            <i class="fas fa-list-ol"></i> Step-by-Step Instructions:
                        </h3>
                        
                        <div style="margin: 15px 0;">
                            <h4 style="color: #6c757d;">Step 1: Download the Contract</h4>
                            {f'<a href="{download_url}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Download Contract PDF</a>' if download_url else '<p style="color: #dc3545;">Contract PDF will be provided separately via email attachment.</p>'}
                        </div>
                        
                        <div style="margin: 15px 0;">
                            <h4 style="color: #6c757d;">Step 2: Print & Sign</h4>
                            <p>Print the contract and sign all required signature fields by hand.</p>
                        </div>
                        
                        <div style="margin: 15px 0;">
                            <h4 style="color: #6c757d;">Step 3: Upload Signed Contract</h4>
                            <a href="{upload_url}" 
                               style="background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                                Upload Signed Contract
                            </a>
                        </div>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                        <h4 style="margin-top: 0;">Important Information:</h4>
                        <p><strong>Upload Link Expires:</strong> {secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                        <p><strong>File Types:</strong> PDF, JPG, PNG (Max 10MB)</p>
                        <p><strong>Quality:</strong> Please ensure all signatures are clearly visible</p>
                    </div>
                    
                    <p>Once you upload the signed contract, you will receive a confirmation and our office will be notified for processing.</p>
                    
                    <p>If you have any questions or technical difficulties, please contact our office.</p>
                    
                    <p>Best regards,<br>
                    {student.division} Financial Office</p>
                </div>
                """
            
            # Send the email
            email_result = email_service.send_email(
                to_email=recipient_email,
                subject=subject,
                html_content=html_content
            )
            
            if email_result.get('success'):
                # Mark link as sent
                secure_link.sent_date = datetime.utcnow()
                db.session.commit()
                current_app.logger.info(f"Secure upload email sent successfully to {recipient_email} for student {student_id}")
            else:
                current_app.logger.error(f"Failed to send secure upload email: {email_result.get('error')}")
                
        except Exception as e:
            current_app.logger.error(f"Error sending secure upload email: {str(e)}")
            # Don't fail the entire process if email fails
        
        return secure_link
    
    def process_upload(self, token, uploaded_file, ip_address=None, user_agent=None, 
                      document_category=None, document_description=None):
        """Process uploaded form"""
        # Verify secure link
        secure_link = SecureFormLink.query.filter_by(token=token).first()
        if not secure_link or not secure_link.is_usable:
            raise ValueError("Invalid or expired upload link")
        
        # Validate file
        if not uploaded_file.filename:
            raise ValueError("No file selected")
        
        # Security checks
        allowed_extensions = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
        file_extension = uploaded_file.filename.rsplit('.', 1)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise ValueError("File type not allowed")
        
        # Check file size (max 10MB)
        uploaded_file.seek(0, 2)  # Seek to end
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)  # Reset to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise ValueError("File too large (max 10MB)")
        
        # Upload file using storage service
        upload_result = self.storage_service.upload_file(
            uploaded_file,
            uploaded_file.filename,
            folder='secure_forms',
            student_id=secure_link.student_id,
            form_type=secure_link.form_type
        )
        
        file_path = upload_result['path']
        stored_filename = upload_result['filename']
        file_hash = upload_result['file_hash']
        
        # Create upload log
        upload_log = FormUploadLog(
            secure_link_id=secure_link.id,
            student_id=secure_link.student_id,
            original_filename=upload_result['original_filename'],
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=upload_result['file_size'],
            mime_type=uploaded_file.content_type,
            file_hash=file_hash,
            upload_ip=ip_address,
            user_agent=user_agent,
            document_category=document_category or 'main_form',
            document_description=document_description
        )
        
        db.session.add(upload_log)
        
        # Mark secure link as uploaded (only if single file or last upload)
        if not secure_link.allow_multiple_files:
            secure_link.mark_uploaded(file_path, ip_address)
        else:
            # For multiple files, just increment usage
            secure_link.increment_usage()
        
        # Update related records
        self._update_related_records(secure_link, upload_log)
        
        db.session.commit()
        
        return upload_log
    
    def _update_related_records(self, secure_link, upload_log):
        """Update related financial records when form is uploaded"""
        if secure_link.form_type == 'financial_aid_app' and secure_link.form_id:
            application = FinancialAidApplication.query.get(secure_link.form_id)
            if application:
                application.application_status = 'Submitted'
                application.submission_date = datetime.utcnow()
                
            # Mark financial aid uploads as processed
            upload_log.processing_status = 'processed'
            upload_log.processed_at = datetime.utcnow()
        
        elif secure_link.form_type == 'tuition_contract' and secure_link.form_id:
            from models import FinancialRecord, AcademicYear
            
            contract = TuitionContract.query.get(secure_link.form_id)
            if contract:
                # Mark print upload as completed
                contract.print_upload_completed = True
                contract.print_upload_date = datetime.utcnow()
                contract.signed_contract_path = upload_log.file_path
                
                # Set receipt method tracking
                contract.receipt_method = 'secure_upload'
                contract.receipt_notes = f'Uploaded via secure link by {secure_link.student.student_name} family'
                
                # Update overall contract status
                if contract.is_fully_signed:
                    contract.contract_status = 'Signed'
                else:
                    contract.contract_status = 'Partially Signed'
                
                # ALSO UPDATE THE FINANCIAL RECORD
                # Find the corresponding FinancialRecord for this student/year
                financial_record = FinancialRecord.query.filter_by(
                    student_id=contract.student_id,
                    academic_year_id=contract.academic_year_id
                ).first()
                
                if financial_record:
                    # Update both enhanced and legacy fields for UI compatibility
                    financial_record.enhanced_contract_signed = True
                    financial_record.enhanced_contract_signed_date = datetime.utcnow()
                    financial_record.enrollment_contract_received = True
                    financial_record.enrollment_contract_received_date = datetime.utcnow()
                    current_app.logger.info(f"Updated FinancialRecord for student {contract.student_id} - marked contract as signed")
                else:
                    current_app.logger.warning(f"No FinancialRecord found for student {contract.student_id}, year {contract.academic_year_id}")
                
                # Mark tuition contract upload as processed
                upload_log.processing_status = 'processed'
                upload_log.processed_at = datetime.utcnow()
                upload_log.auto_processed = True
                
                current_app.logger.info(f"Tuition contract upload processed for student {contract.student_id}")
                
                # Note: Individual parent signatures would need to be handled separately
    
    @classmethod
    def fix_existing_tuition_contract_uploads(cls):
        """One-time fix to mark existing tuition contract uploads as processed"""
        try:
            # Find all tuition contract uploads that are still pending
            pending_tuition_uploads = FormUploadLog.query.join(
                SecureFormLink, FormUploadLog.secure_link_id == SecureFormLink.id
            ).filter(
                SecureFormLink.form_type == 'tuition_contract',
                FormUploadLog.processing_status == 'pending'
            ).all()
            
            updated_count = 0
            for upload_log in pending_tuition_uploads:
                upload_log.processing_status = 'processed'
                upload_log.processed_at = upload_log.uploaded_at  # Use upload time as processed time
                upload_log.auto_processed = True
                updated_count += 1
                
            if updated_count > 0:
                db.session.commit()
                current_app.logger.info(f"Fixed {updated_count} existing tuition contract uploads - marked as processed")
                
            return updated_count
            
        except Exception as e:
            current_app.logger.error(f"Error fixing existing tuition contract uploads: {str(e)}")
            db.session.rollback()
            return 0
    
    def _send_admin_notification(self, secure_link, upload_log):
        """Send notification to admin when form is uploaded"""
        try:
            email_service = EmailService()
            
            subject = f"Form Uploaded: {secure_link.form_title}"
            
            html_content = f"""
            <h3>Form Upload Notification</h3>
            
            <p><strong>Student:</strong> {secure_link.student.student_name}</p>
            <p><strong>Form Type:</strong> {secure_link.form_type.replace('_', ' ').title()}</p>
            <p><strong>Division:</strong> {secure_link.division}</p>
            <p><strong>Uploaded:</strong> {upload_log.uploaded_at.strftime('%B %d, %Y at %I:%M %p')}</p>
            <p><strong>File:</strong> {upload_log.original_filename}</p>
            <p><strong>Size:</strong> {upload_log.file_size_formatted}</p>
            
            <p>Please review the uploaded form in the admin panel.</p>
            """
            
            # Send to financial office
            admin_email = current_app.config.get('FINANCIAL_ADMIN_EMAIL', 'admin@school.edu')
            email_service.send_email(
                to_email=admin_email,
                subject=subject,
                html_content=html_content
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to send admin notification: {str(e)}") 