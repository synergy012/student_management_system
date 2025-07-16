from flask import current_app, url_for
from flask_mail import Message
from extensions import db, mail
from models import (Student, AcademicYear, EmailTemplate, SecureFormToken, 
                   StudentEnrollmentHistory)
from datetime import datetime, timedelta
import secrets
import uuid
from typing import List, Dict, Optional

class EnrollmentDecisionEmailService:
    """Service for managing enrollment decision emails and student responses"""
    
    def __init__(self):
        self.logger = current_app.logger
    
    def create_enrollment_decision_template(self, division: str = 'YZA') -> Dict:
        """Create default enrollment decision email template"""
        try:
            template_name = f"{division} Enrollment Decision Request"
            
            # Check if template already exists
            existing_template = EmailTemplate.query.filter_by(
                name=template_name,
                category='enrollment_decision',
                division=division
            ).first()
            
            if existing_template:
                return {
                    'success': True,
                    'template_id': existing_template.id,
                    'message': 'Template already exists'
                }
            
            # Create enrollment decision email template
            subject = f"🎓 Enrollment Decision Required for {division} - Academic Year {{{{academic_year}}}}"
            
            body_template = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 10px;">
    <div style="background: #007bff; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; margin: -30px -30px 20px -30px;">
        <h1>🎓 {division} Enrollment Decision</h1>
        <h2>Academic Year {{{{academic_year}}}}</h2>
    </div>
    
    <div style="background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px;">
        <p><strong>Dear {{{{student_name}}}},</strong></p>
        
        <p>We hope this message finds you well! As we prepare for the upcoming academic year {{{{academic_year}}}}, we need your enrollment decision.</p>
        
        <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; margin: 15px 0;">
            <h3>📅 Important Information:</h3>
            <ul>
                <li><strong>Academic Year:</strong> {{{{academic_year}}}}</li>
                <li><strong>Division:</strong> {division}</li>
                <li><strong>Response Deadline:</strong> <span style="color: #dc3545; font-weight: bold;">{{{{response_deadline}}}}</span></li>
                <li><strong>Current Status:</strong> Pending Decision</li>
            </ul>
        </div>
        
        <h3>Please Choose Your Enrollment Status:</h3>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{{{{enrollment_response_url}}}}" style="display: inline-block; background: #007bff; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 10px 5px;">
                📝 RESPOND TO ENROLLMENT DECISION
            </a>
        </div>
        
        <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; margin: 15px 0;">
            <h4>💡 Important Notes:</h4>
            <ul>
                <li>You must respond by <strong>{{{{response_deadline}}}}</strong></li>
                <li>If you don't respond by the deadline, your status will remain as "Pending"</li>
                <li>You can contact the office if you have any questions</li>
                <li>This link will expire after your response or on {{{{link_expiry_date}}}}</li>
            </ul>
        </div>
        
        <h3>Questions or Need Help?</h3>
        <p>If you have any questions about enrollment, tuition, or need assistance, please contact our office:</p>
        <ul>
            <li>📧 Email: {{{{office_email}}}}</li>
            <li>📞 Phone: {{{{office_phone}}}}</li>
            <li>🕐 Office Hours: {{{{office_hours}}}}</li>
        </ul>
    </div>
    
    <div style="text-align: center; color: #666; font-size: 0.9em; margin-top: 20px;">
        <p>This is an automated message from the {division} Student Management System.</p>
        <p>Please do not reply directly to this email. Use the buttons above or contact our office.</p>
        <p><small>Email sent on {{{{current_date}}}} | Link expires {{{{link_expiry_date}}}}</small></p>
    </div>
</div>"""
            
            # Create the template
            template = EmailTemplate(
                name=template_name,
                category='enrollment_decision',
                division=division,
                subject_template=subject,
                body_template=body_template,
                body_format='html',
                is_active=True,
                created_by='System',
                updated_by='System',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.session.add(template)
            db.session.commit()
            
            self.logger.info(f"Created enrollment decision email template for {division}")
            
            return {
                'success': True,
                'template_id': template.id,
                'message': f'Enrollment decision template created for {division}'
            }
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error creating enrollment decision template: {str(e)}")
            raise
    
    def send_enrollment_decision_email(self, student_id: str, academic_year_id: int = None, 
                                     response_deadline: datetime = None) -> Dict:
        """Send enrollment decision email to a specific student"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {'success': False, 'error': 'Student not found'}
            
            # Use current academic year if not specified
            if not academic_year_id:
                from models import AcademicYear
                academic_year = AcademicYear.query.filter_by(is_active=True).first()
                if not academic_year:
                    return {'success': False, 'error': 'No active academic year found'}
                academic_year_id = academic_year.id
            else:
                from models import AcademicYear
                academic_year = AcademicYear.query.get(academic_year_id)
                if not academic_year:
                    return {'success': False, 'error': 'Academic year not found'}
            
            # Get or create email template for this division
            template_result = self.create_enrollment_decision_template(student.division)
            template = EmailTemplate.query.get(template_result['template_id'])
            
            # Set default response deadline (30 days from now)
            if not response_deadline:
                response_deadline = datetime.utcnow() + timedelta(days=30)
            
            # Create secure response token
            token_data = self._create_enrollment_response_token(
                student_id, academic_year_id, response_deadline
            )
            
            # Get email variables
            email_vars = self._get_email_variables(student, academic_year, token_data, response_deadline)
            
            # Render email content using template's render method
            rendered = template.render(email_vars)
            rendered_subject = rendered['subject']
            rendered_html = rendered['body']
            
            # Determine recipients
            recipients = self._get_email_recipients(student)
            
            # Send email
            msg = Message(
                subject=rendered_subject,
                recipients=recipients,
                html=rendered_html if rendered['format'] == 'html' else None,
                body=rendered_html if rendered['format'] == 'plain' else None
            )
            
            mail.send(msg)
            
            # Log the email sending
            self.logger.info(f"Enrollment decision email sent to {student.student_name} for {academic_year.year_label}")
            
            return {
                'success': True,
                'student_name': student.student_name,
                'recipients': recipients,
                'token': token_data['token'],
                'expires_at': token_data['expires_at']
            }
            
        except Exception as e:
            self.logger.error(f"Error sending enrollment decision email: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def send_bulk_enrollment_decision_emails(self, student_ids: List[str], academic_year_id: int,
                                           response_deadline: datetime = None) -> Dict:
        """Send enrollment decision emails to multiple students"""
        try:
            results = {
                'success': True,
                'sent_count': 0,
                'failed_count': 0,
                'results': []
            }
            
            for student_id in student_ids:
                result = self.send_enrollment_decision_email(student_id, academic_year_id, response_deadline)
                
                if result['success']:
                    results['sent_count'] += 1
                else:
                    results['failed_count'] += 1
                
                results['results'].append({
                    'student_id': student_id,
                    'success': result['success'],
                    'student_name': result.get('student_name', 'Unknown'),
                    'error': result.get('error')
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in bulk enrollment email sending: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def process_student_enrollment_response(self, token: str, decision: str) -> Dict:
        """Process student response to enrollment decision email"""
        try:
            # Validate token
            token_data = SecureFormToken.query.filter_by(token=token, is_used=False).first()
            
            if not token_data:
                return {'success': False, 'error': 'Invalid or expired response link'}
            
            if token_data.expires_at < datetime.utcnow():
                return {'success': False, 'error': 'Response link has expired'}
            
            # Validate decision
            valid_decisions = ['enrolled', 'withdrawn']
            if decision not in valid_decisions:
                return {'success': False, 'error': 'Invalid enrollment decision'}
            
            # Parse token metadata
            token_metadata = token_data.token_metadata or {}
            student_id = token_metadata.get('student_id')
            academic_year_id = token_metadata.get('academic_year_id')
            
            if not student_id or not academic_year_id:
                return {'success': False, 'error': 'Invalid token data'}
            
            # Update student enrollment status
            from services.academic_year_service import AcademicYearTransitionService
            transition_service = AcademicYearTransitionService()
            
            enrollment_status = 'Enrolled' if decision == 'enrolled' else 'Withdrawn'
            
            result = transition_service.update_student_enrollment(
                student_id=student_id,
                academic_year_id=academic_year_id,
                enrollment_status=enrollment_status,
                decision_by='Student (Email Response)',
                decision_reason=f'Student responded via enrollment decision email with: {decision}'
            )
            
            if result['success']:
                # Mark token as used
                token_data.is_used = True
                token_data.used_at = datetime.utcnow()
                db.session.commit()
                
                return {
                    'success': True,
                    'student_name': result['student_name'],
                    'enrollment_status': enrollment_status,
                    'message': f'Enrollment decision recorded: {enrollment_status}'
                }
            else:
                return {'success': False, 'error': result['error']}
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Error processing enrollment response: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _create_enrollment_response_token(self, student_id: str, academic_year_id: int, 
                                        expires_at: datetime) -> Dict:
        """Create secure token for student response"""
        token = secrets.token_urlsafe(32)
        
        # Create token record
        token_record = SecureFormToken(
            token=token,
            form_type='enrollment_decision',
            expires_at=expires_at,
            token_metadata={
                'student_id': student_id,
                'academic_year_id': academic_year_id,
                'created_for': 'enrollment_decision_response'
            },
            created_at=datetime.utcnow()
        )
        
        db.session.add(token_record)
        db.session.commit()
        
        return {
            'token': token,
            'expires_at': expires_at,
            'response_url': url_for('enrollment_email.student_response_form', token=token, _external=True)
        }
    
    def _get_email_variables(self, student: Student, academic_year: AcademicYear, 
                           token_data: Dict, response_deadline: datetime) -> Dict:
        """Get variables for email template rendering"""
        return {
            'student_name': student.student_name,
            'academic_year': academic_year.year_label,
            'response_deadline': response_deadline.strftime('%B %d, %Y'),
            'link_expiry_date': token_data['expires_at'].strftime('%B %d, %Y'),
            'enrollment_response_url': token_data['response_url'],
            'current_date': datetime.utcnow().strftime('%B %d, %Y'),
            'office_email': current_app.config.get('OFFICE_EMAIL', 'office@school.edu'),
            'office_phone': current_app.config.get('OFFICE_PHONE', '(555) 123-4567'),
            'office_hours': current_app.config.get('OFFICE_HOURS', 'Monday-Friday 9:00 AM - 5:00 PM')
        }
    
    def _get_email_recipients(self, student: Student) -> List[str]:
        """Get email recipients for student (student only - not parents)"""
        recipients = []
        
        # Add student email only
        if student.email:
            recipients.append(student.email)
        
        # Note: Parent emails are intentionally excluded for enrollment decisions
        # Students should respond to their own enrollment decisions
        
        return recipients
    
    def _render_template_content(self, content: str, variables: Dict) -> str:
        """Render template content with variables"""
        try:
            # Simple template variable replacement
            rendered_content = content
            for key, value in variables.items():
                placeholder = f"{{{{ {key} }}}}"
                rendered_content = rendered_content.replace(placeholder, str(value))
            
            return rendered_content
        except Exception as e:
            self.logger.error(f"Error rendering template content: {str(e)}")
            return content
    
    def get_enrollment_email_statistics(self, academic_year_id: int) -> Dict:
        """Get statistics about enrollment decision emails for an academic year"""
        try:
            # Get all tokens for enrollment decisions for this academic year
            tokens = SecureFormToken.query.filter_by(form_type='enrollment_decision').all()
            
            stats = {
                'total_sent': 0,
                'responses_received': 0,
                'enrolled_responses': 0,
                'withdrawn_responses': 0,
                'expired_tokens': 0,
                'pending_responses': 0
            }
            
            current_time = datetime.utcnow()
            
            for token in tokens:
                if token.token_metadata and token.token_metadata.get('academic_year_id') == academic_year_id:
                    stats['total_sent'] += 1
                    
                    if token.is_used:
                        stats['responses_received'] += 1
                        # Would need to check enrollment history to see what decision was made
                    elif token.expires_at < current_time:
                        stats['expired_tokens'] += 1
                    else:
                        stats['pending_responses'] += 1
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting enrollment email statistics: {str(e)}")
            return {} 