#!/usr/bin/env python3
"""
Email service for sending acceptance letters
"""

from flask import render_template_string, current_app
from flask_mail import Message
from extensions import mail
from models import Student, DivisionConfig
from datetime import datetime
import os

class EmailService:
    """Service for handling acceptance emails"""
    
    @staticmethod
    def get_email_template(division):
        """Get the appropriate email template for the division"""
        template_map = {
            'YZA': 'templates/email_templates/yza_acceptance_letter.html',
            'YOH': 'templates/email_templates/yoh_acceptance_letter.html'
        }
        
        template_path = template_map.get(division)
        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        # Default template if division-specific not found
        return """
        <h2>Acceptance Letter</h2>
        <p>Dear {{ student.student_first_name }} {{ student.student_last_name }},</p>
        <p>Congratulations! You have been accepted to {{ division }}.</p>
        <p>We look forward to welcoming you.</p>
        """
    
    @staticmethod
    def get_email_config(division):
        """Get email configuration for the division"""
        config = DivisionConfig.query.filter_by(division=division, is_active=True).first()
        
        if config:
            return {
                'from_email': config.email_from_address or current_app.config.get('MAIL_DEFAULT_SENDER'),
                'from_name': config.email_from_name or f'{division} Admissions',
                'reply_to': config.email_reply_to or config.email_from_address
            }
        
        # Default configuration
        return {
            'from_email': current_app.config.get('MAIL_DEFAULT_SENDER', 'admissions@yeshiva.edu'),
            'from_name': f'{division} Admissions Office',
            'reply_to': current_app.config.get('MAIL_DEFAULT_SENDER', 'admissions@yeshiva.edu')
        }
    
    @staticmethod
    def prepare_template_context(student):
        """Prepare the context variables for the email template"""
        current_year = datetime.now().year
        next_year = current_year + 1
        
        context = {
            'student': student,
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'academic_year': f'{current_year}-{next_year}',
            'start_date': 'September 1, ' + str(current_year if datetime.now().month < 7 else next_year),
            'orientation_date': 'August 28, ' + str(current_year if datetime.now().month < 7 else next_year),
            'registration_deadline': 'August 15, ' + str(current_year if datetime.now().month < 7 else next_year),
            'contact_email': 'admissions@yeshiva.edu',
            'contact_phone': '(555) 123-4567',
            'yeshiva_address': '123 Torah Way, Brooklyn, NY 11230',
            'yeshiva_phone': '(555) 123-4567',
            'yeshiva_email': 'info@yeshiva.edu'
        }
        
        # Add division-specific overrides
        if student.division == 'YOH':
            context.update({
                'contact_email': 'admissions@yoh.edu',
                'yeshiva_email': 'info@yoh.edu'
            })
        elif student.division == 'YZA':
            context.update({
                'contact_email': 'admissions@yza.edu',
                'yeshiva_email': 'info@yza.edu'
            })
        
        return context
    
    @staticmethod
    def send_acceptance_email(student_id, sent_by_user):
        """Send acceptance email with PDF attachment to a student"""
        try:
            # Get the student
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'message': 'Student not found'}
            
            # Check if already sent
            if student.acceptance_email_sent:
                return {
                    'success': False, 
                    'message': f'Acceptance email already sent on {student.acceptance_email_sent_date.strftime("%B %d, %Y") if student.acceptance_email_sent_date else "unknown date"}'
                }
            
            # Get email configuration
            email_config = EmailService.get_email_config(student.division)
            
            # Generate PDF acceptance letter
            from pdf_service import PDFService
            pdf_content = PDFService.generate_acceptance_letter_pdf(student)
            pdf_filename = PDFService.generate_filename(student)
            
            # Create simple email content (since the detailed letter is in the PDF)
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50; text-align: center;">{school_name}</h2>
                    
                    <p>Dear {student_name},</p>
                    
                    <p><strong>Congratulations!</strong> We are delighted to inform you that you have been accepted to {school_name}.</p>
                    
                    <p>Please find your official acceptance letter attached as a PDF document. This letter contains important information about your acceptance and next steps.</p>
                    
                    <p>We look forward to welcoming you to our Beis Medrash and are excited to have you join our Torah learning community.</p>
                    
                    <p>If you have any questions, please don't hesitate to contact our admissions office.</p>
                    
                    <p style="margin-top: 30px;">
                        Sincerely,<br>
                        <strong>Admissions Office</strong><br>
                        {school_name}
                    </p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666;">
                        <strong>Note:</strong> Your official acceptance letter is attached as a PDF document. 
                        Please save this document for your records.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Create the email message
            msg = Message(
                subject=f'Acceptance to {school_name} - Congratulations!',
                sender=(email_config['from_name'], email_config['from_email']),
                recipients=[student.email],
                html=html_content,
                reply_to=email_config['reply_to']
            )
            
            # Attach the PDF
            msg.attach(
                filename=pdf_filename,
                content_type='application/pdf',
                data=pdf_content
            )
            
            # Send the email
            mail.send(msg)
            
            # Save PDF to attachments folder for record keeping
            try:
                PDFService.save_pdf_to_file(pdf_content, pdf_filename)
                current_app.logger.info(f"✅ Saved acceptance letter PDF: {pdf_filename}")
            except Exception as save_error:
                current_app.logger.warning(f"⚠️ Could not save PDF to attachments folder: {save_error}")
            
            # Update the student record
            student.acceptance_email_sent = True
            student.acceptance_email_sent_date = datetime.utcnow()
            student.acceptance_email_sent_by = sent_by_user
            
            from extensions import db
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Acceptance email with PDF attachment successfully sent to {student.email}'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error sending acceptance email: {str(e)}')
            return {
                'success': False,
                'message': f'Error sending email: {str(e)}'
            }
    
    @staticmethod
    def send_custom_acceptance_email(student_id, sent_by_user, custom_subject, custom_body):
        """Send a custom acceptance email with PDF attachment"""
        try:
            # Get the student
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'message': 'Student not found'}
            
            # Get email configuration
            email_config = EmailService.get_email_config(student.division)
            
            # Generate PDF acceptance letter
            from pdf_service import PDFService
            pdf_content = PDFService.generate_acceptance_letter_pdf(student)
            pdf_filename = PDFService.generate_filename(student)
            
            # Use custom email content
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    {custom_body}
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666;">
                        <strong>Note:</strong> Your official acceptance letter is attached as a PDF document. 
                        Please save this document for your records.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Create the email message
            msg = Message(
                subject=custom_subject,
                sender=(email_config['from_name'], email_config['from_email']),
                recipients=[student.email],
                html=html_content,
                reply_to=email_config['reply_to']
            )
            
            # Attach the PDF
            msg.attach(
                filename=pdf_filename,
                content_type='application/pdf',
                data=pdf_content
            )
            
            # Send the email
            mail.send(msg)
            
            # Save PDF to attachments folder for record keeping
            try:
                PDFService.save_pdf_to_file(pdf_content, pdf_filename)
                current_app.logger.info(f"✅ Saved custom acceptance letter PDF: {pdf_filename}")
            except Exception as save_error:
                current_app.logger.warning(f"⚠️ Could not save PDF to attachments folder: {save_error}")
            
            # Update the student record
            student.acceptance_email_sent = True
            student.acceptance_email_sent_date = datetime.utcnow()
            student.acceptance_email_sent_by = sent_by_user
            
            from extensions import db
            db.session.commit()
            
            return {
                'success': True,
                'message': f'Custom acceptance email with PDF attachment successfully sent to {student.email}'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error sending custom acceptance email: {str(e)}')
            return {
                'success': False,
                'message': f'Error sending email: {str(e)}'
            }

    @staticmethod
    def preview_acceptance_email(student_id):
        """Generate a preview of the acceptance email (now shows PDF info)"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'message': 'Student not found'}
            
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            
            # Generate preview content
            preview_content = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50; text-align: center;">{school_name}</h2>
                
                <p>Dear {student_name},</p>
                
                <p><strong>Congratulations!</strong> We are delighted to inform you that you have been accepted to {school_name}.</p>
                
                <p>Please find your official acceptance letter attached as a PDF document. This letter contains important information about your acceptance and next steps.</p>
                
                <p>We look forward to welcoming you to our Beis Medrash and are excited to have you join our Torah learning community.</p>
                
                <p>If you have any questions, please don't hesitate to contact our admissions office.</p>
                
                <p style="margin-top: 30px;">
                    Sincerely,<br>
                    <strong>Admissions Office</strong><br>
                    {school_name}
                </p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px;">
                        <strong>📎 PDF Attachment:</strong> Official Acceptance Letter ({school_name.replace(' ', '_')}_Acceptance_Letter.pdf)
                    </p>
                </div>
            </div>
            """
            
            return {
                'success': True,
                'body': preview_content,
                'subject': f'Acceptance to {school_name} - Congratulations!'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error generating email preview: {str(e)}')
            return {'success': False, 'message': f'Error generating preview: {str(e)}'}

    @staticmethod
    def preview_acceptance_email_from_application(application):
        """Generate a preview of the acceptance email from application data"""
        try:
            division = application.division or 'YZA'
            school_name = "Yeshiva Zichron Aryeh" if division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = application.student_name or f"{application.student_first_name or ''} {application.student_last_name or ''}".strip()
            
            preview_content = f"""
            <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50; text-align: center;">{school_name}</h2>
                
                <p>Dear {student_name},</p>
                
                <p><strong>Congratulations!</strong> We are delighted to inform you that you have been accepted to {school_name}.</p>
                
                <p>Please find your official acceptance letter attached as a PDF document. This letter contains important information about your acceptance and next steps.</p>
                
                <p>We look forward to welcoming you to our Beis Medrash and are excited to have you join our Torah learning community.</p>
                
                <p>If you have any questions, please don't hesitate to contact our admissions office.</p>
                
                <p style="margin-top: 30px;">
                    Sincerely,<br>
                    <strong>Admissions Office</strong><br>
                    {school_name}
                </p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px;">
                        <strong>📎 PDF Attachment:</strong> Official Acceptance Letter (will be generated upon acceptance)
                    </p>
                </div>
            </div>
            """
            
            return {
                'success': True,
                'body': preview_content,
                'subject': f'Acceptance to {school_name} - Congratulations!'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error generating email preview from application: {str(e)}')
            return {'success': False, 'message': f'Error generating preview: {str(e)}'}

    @staticmethod
    def get_template_content_for_application(application):
        """Get template content for editing based on application data"""
        try:
            division = application.division or 'YZA'
            school_name = "Yeshiva Zichron Aryeh" if division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = application.student_name or f"{application.student_first_name or ''} {application.student_last_name or ''}".strip()
            
            subject = f'Acceptance to {school_name} - Congratulations!'
            
            body = f"""
            <h2 style="color: #2c3e50; text-align: center;">{school_name}</h2>
            
            <p>Dear {student_name},</p>
            
            <p><strong>Congratulations!</strong> We are delighted to inform you that you have been accepted to {school_name}.</p>
            
            <p>Please find your official acceptance letter attached as a PDF document. This letter contains important information about your acceptance and next steps.</p>
            
            <p>We look forward to welcoming you to our Beis Medrash and are excited to have you join our Torah learning community.</p>
            
            <p>If you have any questions, please don't hesitate to contact our admissions office.</p>
            
            <p style="margin-top: 30px;">
                Sincerely,<br>
                <strong>Admissions Office</strong><br>
                {school_name}
            </p>
            """
            
            return {
                'success': True,
                'subject': subject,
                'body': body
            }
            
        except Exception as e:
            current_app.logger.error(f'Error getting template content for application: {str(e)}')
            return {'success': False, 'message': f'Error loading template: {str(e)}'}

    @staticmethod
    def send_email_with_attachment(email_data):
        """
        Generic method to send email with attachment
        
        Args:
            email_data (dict): Dictionary containing:
                - recipients (list): List of email addresses
                - subject (str): Email subject
                - message (str): Email body (HTML or plain text)
                - attachment_path (str): Path to attachment file
                - attachment_name (str): Name for the attachment
                - from_email (str, optional): Sender email
                - from_name (str, optional): Sender name
                - reply_to (str, optional): Reply-to email
        
        Returns:
            dict: Success/error status and message
        """
        try:
            # Extract data from email_data
            recipients = email_data.get('recipients', [])
            subject = email_data.get('subject', '')
            message = email_data.get('message', '')
            attachment_path = email_data.get('attachment_path')
            attachment_name = email_data.get('attachment_name')
            from_email = email_data.get('from_email', current_app.config.get('MAIL_DEFAULT_SENDER'))
            from_name = email_data.get('from_name', 'System')
            reply_to = email_data.get('reply_to', from_email)
            
            # Validate required fields
            if not recipients:
                return {'success': False, 'error': 'No recipients specified'}
            if not subject:
                return {'success': False, 'error': 'Subject is required'}
            if not message:
                return {'success': False, 'error': 'Message is required'}
            
            # Create the email message
            msg = Message(
                subject=subject,
                sender=(from_name, from_email),
                recipients=recipients,
                html=message if '<' in message else None,  # HTML if contains tags
                body=message if '<' not in message else None,  # Plain text otherwise
                reply_to=reply_to
            )
            
            # Attach file if provided
            if attachment_path and attachment_name:
                if os.path.exists(attachment_path):
                    with open(attachment_path, 'rb') as attachment_file:
                        msg.attach(
                            filename=attachment_name,
                            content_type='application/pdf',
                            data=attachment_file.read()
                        )
                else:
                    return {'success': False, 'error': f'Attachment file not found: {attachment_path}'}
            
            # Send the email
            mail.send(msg)
            
            current_app.logger.info(f"✅ Email sent successfully to {recipients} with subject: {subject}")
            
            return {
                'success': True,
                'message': f'Email sent successfully to {len(recipients)} recipient(s)'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error sending email with attachment: {str(e)}')
            return {
                'success': False,
                'error': f'Failed to send email: {str(e)}'
            }

    @staticmethod
    def send_email(to_email, subject, html_content, from_email=None, from_name=None, reply_to=None):
        """
        Generic method to send a simple email without attachment
        
        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_content (str): HTML email body
            from_email (str, optional): Sender email
            from_name (str, optional): Sender name
            reply_to (str, optional): Reply-to email
        
        Returns:
            dict: Success/error status and message
        """
        try:
            # Use default sender if not provided
            if not from_email:
                from_email = current_app.config.get('MAIL_DEFAULT_SENDER')
            if not from_name:
                from_name = 'System'
            if not reply_to:
                reply_to = from_email
            
            # Create the email message
            msg = Message(
                subject=subject,
                sender=(from_name, from_email),
                recipients=[to_email],
                html=html_content if '<' in html_content else None,  # HTML if contains tags
                body=html_content if '<' not in html_content else None,  # Plain text otherwise
                reply_to=reply_to
            )
            
            # Send the email
            mail.send(msg)
            
            current_app.logger.info(f"✅ Email sent successfully to {to_email} with subject: {subject}")
            
            return {
                'success': True,
                'message': f'Email sent successfully to {to_email}'
            }
            
        except Exception as e:
            current_app.logger.error(f'Error sending email: {str(e)}')
            return {
                'success': False,
                'error': f'Failed to send email: {str(e)}'
            } 