"""
Student management routes
"""
from flask import Blueprint, jsonify, current_app, request, render_template, flash, redirect, url_for, send_file, abort
from flask_login import login_required, current_user
from extensions import db
from models import Student, Application
from utils.decorators import permission_required
from utils.helpers import parse_date, parse_decimal
from datetime import datetime
import uuid
import json
import os

students = Blueprint('students', __name__)


@students.route('/students')
@login_required
@permission_required('view_students')
def view_students():
    """Display the students page with division filtering."""
    try:
        # Get division filter from query parameters
        division_filter = request.args.get('division', 'all')
        
        # Query students from the database using the Student model
        if division_filter == 'all':
            students_from_db = Student.query.order_by(Student.accepted_date.desc()).all()
        else:
            students_from_db = Student.query.filter_by(division=division_filter.upper()).order_by(Student.accepted_date.desc()).all()
        
        # Convert database students to list format for the template
        student_list = []
        for student in students_from_db:
            student_data = {
                'id': student.id,
                'full_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
                'phone_number': student.phone_number or '',
                'hebrew_name': student.hebrew_name or '',
                'division': student.division or 'YZA',
                'status': student.status or 'Active',
                'status_color': 'success' if student.status == 'Active' else 'secondary',
                'accepted_date': student.accepted_date,
                'email': student.email or '',
                'citizenship': student.citizenship or '',
                'marital_status': student.marital_status or ''
            }
            student_list.append(student_data)
        
        # Get counts for each division
        yza_count = Student.query.filter_by(division='YZA').count()
        yoh_count = Student.query.filter_by(division='YOH').count()
        kollel_count = Student.query.filter_by(division='KOLLEL').count()
        total_count = Student.query.count()
        
        return render_template('students.html', 
                             students=student_list, 
                             current_filter=division_filter,
                             yza_count=yza_count,
                             yoh_count=yoh_count,
                             kollel_count=kollel_count,
                             total_count=total_count)
        
    except Exception as e:
        current_app.logger.error(f"Error loading students page: {e}")
        return render_template('students.html', 
                             students=[], 
                             current_filter='all',
                             yza_count=0,
                             yoh_count=0,
                             kollel_count=0,
                             total_count=0)


@students.route('/students/<student_id>')
@login_required
@permission_required('view_students')
def student_details(student_id):
    """Display student details."""
    try:
        from models import TuitionRecord, AcademicYear
        
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return render_template('404.html', message="Student not found"), 404
        
        # Get current academic year
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        # Get the current tuition record
        tuition_record = None
        if current_year:
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=current_year.id
            ).first()
        
        # Get TuitionContract information for uploaded contracts
        from models import TuitionContract, FormUploadLog
        tuition_contract = None
        uploaded_contract_file = None
        if current_year:
            tuition_contract = TuitionContract.query.filter_by(
                student_id=student_id,
                academic_year_id=current_year.id
            ).first()
            
            # Get uploaded contract file if exists
            if tuition_contract and tuition_contract.print_upload_completed:
                # Find the most recent uploaded contract file
                uploaded_contract_file = FormUploadLog.query.filter_by(
                    student_id=student_id,
                    document_category='tuition_contract'
                ).order_by(FormUploadLog.uploaded_at.desc()).first()
        
        # Create financial_aid object for template compatibility
        financial_aid = {
            'payment_status': 'Pending',
            'amount_can_pay': float(student.amount_can_pay or 0),
            'scholarship_requested': float(student.scholarship_amount_requested or 0),
            'financial_aid_type': tuition_record.financial_aid_type if tuition_record else 'Full Tuition',
            'financial_aid_app_sent': tuition_record.financial_aid_app_sent if tuition_record else False,
            'financial_aid_app_received': tuition_record.financial_aid_app_received if tuition_record else False,
            'tuition_determination': float(tuition_record.tuition_determination or 0) if tuition_record else 0,
            'tuition_determination_notes': tuition_record.tuition_determination_notes if tuition_record else '',
            'tuition_contract_generated': tuition_record.tuition_contract_generated if tuition_record else False,
            'tuition_contract_sent': tuition_record.tuition_contract_sent if tuition_record else False,
            'tuition_contract_signed': tuition_record.tuition_contract_signed if tuition_record else False,
            'tuition_contract_pdf_path': tuition_record.tuition_contract_pdf_path if tuition_record else None,
            'opensign_document_id': getattr(tuition_record, 'opensign_document_id', None) if tuition_record else None,
            'opensign_document_status': getattr(tuition_record, 'opensign_document_status', None) if tuition_record else None,
            'opensign_signed_url': getattr(tuition_record, 'opensign_signed_url', None) if tuition_record else None,
            'opensign_certificate_url': getattr(tuition_record, 'opensign_certificate_url', None) if tuition_record else None,
            'fafsa_eligible': tuition_record.fafsa_eligible if tuition_record else 'Unknown',
            'fafsa_required': tuition_record.fafsa_required if tuition_record else False,
            'fafsa_applied': tuition_record.fafsa_applied if tuition_record else False,
            'fafsa_status': tuition_record.fafsa_status if tuition_record else 'Pending',
            'fafsa_amount_awarded': float(tuition_record.fafsa_amount_awarded or 0) if tuition_record else 0,
            'fafsa_notes': tuition_record.fafsa_notes if tuition_record else '',
            # Add uploaded contract information
            'uploaded_contract_id': uploaded_contract_file.id if uploaded_contract_file else None,
            'uploaded_contract_filename': uploaded_contract_file.original_filename if uploaded_contract_file else None,
            'uploaded_contract_date': uploaded_contract_file.uploaded_at if uploaded_contract_file else None
        }
        
        # The student.financial_aid property will automatically return the financial aid data
        
        # Get student's file attachments
        attachments = student.attachments.all() if hasattr(student, 'attachments') else []
        
        return render_template('student_details.html', student=student, attachments=attachments)
        
    except Exception as e:
        current_app.logger.error(f"Error loading student {student_id}: {str(e)}")
        return render_template('404.html', message="Error loading student details"), 500


@students.route('/students/<student_id>/edit')
@login_required
@permission_required('edit_students')
def edit_student(student_id):
    """Display the student edit form."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        
        if not student:
            return render_template('404.html', message="Student not found"), 404
        
        return render_template('student_edit.html', student=student)
        
    except Exception as e:
        current_app.logger.error(f"Error loading student for edit {student_id}: {str(e)}")
        return render_template('404.html', message="Error loading student for editing"), 500


@students.route('/students/new', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def create_student():
    """Create a new student with comprehensive information."""
    if request.method == 'GET':
        return render_template('student_create.html')
    
    try:
        # Parse form data
        data = request.form.to_dict()
        
        # Generate student ID
        student_id = str(uuid.uuid4())
        
        # Construct student name from parts
        name_parts = [
            data.get('student_first_name', '').strip(),
            data.get('student_middle_name', '').strip(),
            data.get('student_last_name', '').strip()
        ]
        student_name = ' '.join(part for part in name_parts if part)
        
        # Parse date field
        date_of_birth = parse_date(data.get('date_of_birth'))
        
        # Create student record
        student_data = {
            'id': student_id,
            'student_name': student_name,
            'division': data.get('division', 'YZA'),
            'status': data.get('status', 'Active'),
            'accepted_date': datetime.now(),
            'date_of_birth': date_of_birth,
            'amount_can_pay': parse_decimal(data.get('amount_can_pay')),
            'scholarship_amount_requested': parse_decimal(data.get('scholarship_amount_requested')),
            # Add all other fields...
        }
        
        # Add remaining fields
        for field in ['student_first_name', 'student_middle_name', 'student_last_name', 
                     'hebrew_name', 'informal_name', 'phone_number', 'email', 
                     'marital_status', 'spouse_name', 'citizenship', 'social_security_number',
                     'high_school_graduate', 'address_line1', 'address_line2', 'address_city',
                     'address_state', 'address_zip', 'address_country']:
            if field in data:
                student_data[field] = data.get(field)
        
        # Custom fields for manual creation tracking
        student_data['custom_fields'] = json.dumps({
            'created_manually': True,
            'created_by': current_user.username,
            'created_at': datetime.now().isoformat()
        })
        
        # Create student
        student = Student(**student_data)
        db.session.add(student)
        db.session.commit()
        
        current_app.logger.info(f"Manual student created: {student_id} by {current_user.username}")
        
        flash('Student created successfully!', 'success')
        return redirect(url_for('students.student_details', student_id=student_id))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating manual student: {str(e)}")
        flash(f'Error creating student: {str(e)}', 'error')
        return redirect(url_for('students.create_student'))


# API Routes for Students
@students.route('/api/students/<student_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def update_student(student_id):
    """Update student information with comprehensive fields."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.json
        
        # Update student name if name parts changed
        if any(field in data for field in ['student_first_name', 'student_middle_name', 'student_last_name']):
            name_parts = [
                data.get('student_first_name', student.student_first_name or '').strip(),
                data.get('student_middle_name', student.student_middle_name or '').strip(),
                data.get('student_last_name', student.student_last_name or '').strip()
            ]
            student.student_name = ' '.join(part for part in name_parts if part)
        
        # Update all other fields
        for field, value in data.items():
            if hasattr(student, field):
                if field == 'date_of_birth':
                    setattr(student, field, parse_date(value))
                elif field in ['amount_can_pay', 'scholarship_amount_requested']:
                    setattr(student, field, parse_decimal(value))
                else:
                    setattr(student, field, value)
        
        # Update tracking metadata
        try:
            custom_data = json.loads(student.custom_fields) if student.custom_fields else {}
        except:
            custom_data = {}
        
        custom_data.update({
            'last_edited_by': current_user.username,
            'last_edited_at': datetime.now().isoformat()
        })
        
        student.custom_fields = json.dumps(custom_data)
        
        db.session.commit()
        
        current_app.logger.info(f"Student {student_id} updated by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'Student {student.student_name} updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating student {student_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating student: {str(e)}'
        }), 500


@students.route('/api/students/<student_id>', methods=['DELETE'])
@login_required
@permission_required('edit_students')
def delete_student(student_id):
    """Delete a student."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        student_name = student.student_name
        db.session.delete(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Student {student_name} deleted successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error deleting student {student_id}: {str(e)}")
        return jsonify({'error': 'Error deleting student'}), 500


@students.route('/api/students/<student_id>/unaccept', methods=['POST'])
@login_required
@permission_required('process_applications')
def unaccept_student(student_id):
    """Unaccept a student - revert them back to application status."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        student_name = student.student_name
        
        # Find the original application for this student
        application = Application.query.filter_by(id=student_id).first()
        
        if application:
            # Update application status back to pending
            application.status = 'pending'
            current_app.logger.info(f"Student {student_id} unaccepted by {current_user.username} - application reverted to pending")
        
        # Delete the student record
        db.session.delete(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Student {student_name} has been unaccepted and their application is now pending'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error unaccepting student {student_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error unaccepting student: {str(e)}'
        }), 500


@students.route('/api/students/<student_id>/contact-info', methods=['GET'])
@login_required
@permission_required('view_students')
def get_student_contact_info(student_id):
    """Get student and family contact information for email recipient selection."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        emails = {
            'student': student.email,
            'father': student.father_email,
            'mother': student.mother_email
        }
        
        return jsonify({
            'success': True,
            'emails': emails,
            'student_name': student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting student contact info: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/api/students/<student_id>/email-preview/<email_type>', methods=['GET'])
@login_required
@permission_required('view_students')
def get_email_preview(student_id, email_type):
    """Get email preview for different email types."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Check if secure upload should be included
        include_secure_upload = request.args.get('include_secure_upload', '').lower() == 'true'
        
        # Helper function to enhance context with secure upload variables
        def enhance_with_secure_upload(context, form_type='general'):
            if include_secure_upload:
                try:
                    from secure_forms_service import SecureFormsService
                    from models import AcademicYear
                    
                    # Get or create secure upload link
                    academic_year = AcademicYear.query.filter_by(is_active=True).first()
                    if academic_year:
                        secure_link = SecureFormsService.create_secure_upload_link(
                            student_id=student_id,
                            form_type=form_type,
                            form_id=f'{form_type}_{student_id}',
                            division=student.division,
                            title=f'{form_type.replace("_", " ").title()} Upload',
                            description=f'Secure upload for {student.student_name or "student"}',
                            expires_hours=72
                        )
                        
                        if secure_link:
                            context.update({
                                'secure_upload_url': url_for('secure_forms.upload_form', token=secure_link.token, _external=True),
                                'secure_upload_expires': secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p'),
                                'secure_upload_token': secure_link.token,
                                'secure_upload_link': secure_link,
                                'has_secure_upload': True
                            })
                        else:
                            context['has_secure_upload'] = False
                    else:
                        context['has_secure_upload'] = False
                except Exception as e:
                    current_app.logger.error(f"Error creating secure upload link: {str(e)}")
                    context['has_secure_upload'] = False
            else:
                context['has_secure_upload'] = False
            
            return context
        
        # Helper function to enhance email content with secure upload instructions
        def enhance_email_content_with_secure_upload(subject, body, context):
            if include_secure_upload and context.get('has_secure_upload'):
                # Enhance subject if it doesn't already mention secure upload
                if 'secure' not in subject.lower() and 'upload' not in subject.lower():
                    subject = f"{subject} - Secure Upload Available"
                
                # Add secure upload section to email body if not already present
                if 'secure_upload_url' not in body and context.get('secure_upload_url'):
                    secure_upload_section = f'''
                    
                    <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin: 25px 0; border-left: 4px solid #0066cc;">
                        <h4 style="color: #004085; margin-top: 0;">🔒 Secure Document Upload Available</h4>
                        <p style="color: #004085; margin: 15px 0;">
                            For your convenience and security, you can upload completed forms and supporting documents using our secure portal:
                        </p>
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{context['secure_upload_url']}" 
                               style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block; font-weight: bold;">
                                🔒 Upload Documents Securely
                            </a>
                        </div>
                        <p style="font-size: 14px; color: #6c757d; margin: 0; text-align: center;">
                            <strong>Secure Link Expires:</strong> {context['secure_upload_expires']}
                        </p>
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #cce7ff;">
                            <h5 style="color: #004085; margin: 0 0 10px 0;">Benefits of Secure Upload:</h5>
                            <ul style="color: #004085; margin: 0; padding-left: 20px;">
                                <li>Fully encrypted and secure transmission</li>
                                <li>Instant confirmation of receipt</li>
                                <li>No need to mail or deliver documents</li>
                                <li>Available 24/7 for your convenience</li>
                            </ul>
                        </div>
                    </div>
                    '''
                    
                    # Insert before closing tags
                    if '</div>' in body:
                        body = body.replace('</div>', f'{secure_upload_section}</div>', 1)
                    else:
                        body += secure_upload_section
            
            return subject, body
        
        # Generate preview based on email type
        if email_type == 'acceptance':
            from email_service import EmailService
            preview = EmailService.preview_acceptance_email(student_id)
            if preview['success']:
                return jsonify({
                    'success': True,
                    'subject': preview['subject'],
                    'body': preview['body']
                })
            else:
                return jsonify({'error': preview['message']}), 500
                
        elif email_type == 'financial_aid':
            # Try to get email template from the email template system
            try:
                from models import EmailTemplate
                
                # Look for division-specific financial aid template first
                email_template = EmailTemplate.query.filter_by(
                    category='financial_aid',
                    division=student.division,
                    is_active=True
                ).first()
                
                # If no division-specific template, try global financial aid template
                if not email_template:
                    email_template = EmailTemplate.query.filter_by(
                        category='financial_aid',
                        division=None,
                        is_active=True
                    ).first()
                
                if email_template:
                    # Use email template system
                    school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
                    current_year = datetime.now().year
                    academic_year_label = f"{current_year}-{current_year + 1}"
                    
                    template_context = {
                        'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
                        'student_first_name': student.student_first_name or '',
                        'student_last_name': student.student_last_name or '',
                        'father_title': student.father_title or '',
                        'father_name': f"{student.father_first_name or ''} {student.father_last_name or ''}".strip(),
                        'father_email': student.father_email or '',
                        'mother_title': student.mother_title or '',
                        'mother_name': f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip(),
                        'mother_email': student.mother_email or '',
                        'academic_year': academic_year_label,
                        'school_name': school_name,
                        'division': student.division,
                        'current_date': datetime.now().strftime('%B %d, %Y'),
                        'portal_url': request.url_root.rstrip('/'),
                    }
                    
                    # Enhance with secure upload if requested
                    template_context = enhance_with_secure_upload(template_context, 'financial_aid')
                    
                    # Render template
                    rendered = email_template.render(template_context)
                    
                    # Enhance content with secure upload if requested  
                    subject, body = enhance_email_content_with_secure_upload(rendered['subject'], rendered['body'], template_context)
                    
                    return jsonify({
                        'success': True,
                        'subject': subject,
                        'body': body,
                        'template_used': email_template.name
                    })
            except Exception as e:
                current_app.logger.error(f"Error loading financial aid email template: {str(e)}")
            
            # Fall back to default content
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
            
            # Create context for secure upload enhancement
            fallback_context = {
                'student_name': student_name,
                'school_name': school_name,
                'division': student.division
            }
            
            # Enhance with secure upload if requested
            fallback_context = enhance_with_secure_upload(fallback_context, 'financial_aid')
            
            subject = f"Financial Aid Application - {school_name}"
            body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #0d6efd;">{school_name}</h2>
                <p>Dear {student_name},</p>
                <p>Your financial aid application form is ready for completion. Please use the secure link provided to submit your financial information.</p>
                <p>This secure form ensures your financial information is protected and encrypted.</p>
                <p>If you have any questions, please contact our financial aid office.</p>
                <p>Best regards,<br><strong>Financial Aid Office</strong><br>{school_name}</p>
            </div>
            """
            
            # Enhance content with secure upload if requested
            subject, body = enhance_email_content_with_secure_upload(subject, body, fallback_context)
            
            return jsonify({
                'success': True,
                'subject': subject,
                'body': body,
                'template_used': 'Default Content'
            })
            
        elif email_type == 'tuition_contract':
            # Generate tuition contract email preview
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
            
            subject = f"Tuition Contract for Academic Year - {school_name}"
            body = f"""
            <h2>{school_name}</h2>
            <p>Dear {student_name},</p>
            <p>Your tuition contract for the upcoming academic year is ready for your review and signature.</p>
            <p>Please review the contract carefully and sign it using the secure digital signature system.</p>
            <p>If you have any questions about the contract terms or tuition amounts, please contact our financial office.</p>
            <p>Best regards,<br><strong>Financial Office</strong><br>{school_name}</p>
            """
            
            return jsonify({
                'success': True,
                'subject': subject,
                'body': body
            })
            
        elif email_type == 'enhanced_contract':
            # Generate enhanced tuition contract email preview
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
            
            subject = f"Enhanced Tuition Contract for Academic Year - {school_name}"
            body = f"""
            <h2>{school_name}</h2>
            <p>Dear {student_name},</p>
            <p>Your enhanced tuition contract for the upcoming academic year is ready for your review and signature.</p>
            <p>This contract includes detailed tuition breakdowns, payment schedules, and all applicable fees.</p>
            <p>Please review the contract carefully and sign it using the secure digital signature system.</p>
            <p>If you have any questions about the contract terms, payment schedules, or tuition amounts, please contact our financial office.</p>
            <p>Best regards,<br><strong>Financial Office</strong><br>{school_name}</p>
            """
            
            return jsonify({
                'success': True,
                'subject': subject,
                'body': body
            })
            
        elif email_type == 'enrollment_contract':
            # Try to get email template from the email template system
            try:
                from models import EmailTemplate
                
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
                
                if email_template:
                    # Use email template system
                    school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
                    current_year = datetime.now().year
                    academic_year_label = f"{current_year}-{current_year + 1}"
                    
                    template_context = {
                        'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
                        'student_first_name': student.student_first_name or '',
                        'student_last_name': student.student_last_name or '',
                        'father_title': student.father_title or '',
                        'father_name': f"{student.father_first_name or ''} {student.father_last_name or ''}".strip(),
                        'father_email': student.father_email or '',
                        'mother_title': student.mother_title or '',
                        'mother_name': f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip(),
                        'mother_email': student.mother_email or '',
                        'academic_year': academic_year_label,
                        'school_name': school_name,
                        'division': student.division,
                        'current_date': datetime.now().strftime('%B %d, %Y'),
                        'portal_url': request.url_root.rstrip('/'),
                    }
                    
                    # Render template
                    rendered = email_template.render(template_context)
                    return jsonify({
                        'success': True,
                        'subject': rendered['subject'],
                        'body': rendered['body'],
                        'template_used': email_template.name
                    })
            except Exception as e:
                current_app.logger.error(f"Error loading enrollment contract email template: {str(e)}")
            
            # Fall back to default content
            school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
            student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
            
            subject = f"Enrollment Contract for Academic Year - {school_name}"
            body = f"""
            <h2>{school_name}</h2>
            <p>Dear {student_name},</p>
            <p>Your enrollment contract for the upcoming academic year is ready for your review and signature.</p>
            <p>Please review the contract carefully and sign it using our secure digital signature system.</p>
            <p>If you have any questions about the contract terms or enrollment requirements, please contact our admissions office.</p>
            <p>Best regards,<br><strong>Admissions Office</strong><br>{school_name}</p>
            """
            
            return jsonify({
                'success': True,
                'subject': subject,
                'body': body,
                'template_used': 'Default Content'
            })
            
        else:
            return jsonify({'error': 'Invalid email type'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error getting email preview: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/api/students/<student_id>/send-financial-aid-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_financial_aid_form_with_recipients(student_id):
    """Send financial aid form with selected recipients including secure upload link"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        recipients = data.get('recipients', [])
        
        if not recipients:
            return jsonify({'error': 'No recipients selected'}), 400
        
        # Get current academic year
        from models import AcademicYear, FinancialAidApplication
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not academic_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        # Create or get FinancialAidApplication record for secure upload
        financial_aid_app = FinancialAidApplication.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id,
            division=student.division
        ).first()
        
        if not financial_aid_app:
            financial_aid_app = FinancialAidApplication(
                student_id=student_id,
                academic_year_id=academic_year.id,
                division=student.division,
                application_status='Draft',
                application_type='New'
            )
            db.session.add(financial_aid_app)
            db.session.commit()
        
        # Create secure upload link
        from secure_forms_service import SecureFormsService
        secure_forms = SecureFormsService()
        secure_link = secure_forms._create_secure_link(
            student_id=student_id,
            form_type='financial_aid_app',
            form_id=financial_aid_app.id,
            expires_hours=72
        )
        
        # Get custom email content if provided
        custom_email_subject = data.get('customEmailSubject')
        custom_email_body = data.get('customEmailBody')
        
        # Try to get email template from the email template system
        email_template = None
        try:
            from models import EmailTemplate
            # Look for division-specific financial aid template first
            email_template = EmailTemplate.query.filter_by(
                category='financial_aid',
                division=student.division,
                is_active=True
            ).first()
            
            # If no division-specific template, try global financial aid template
            if not email_template:
                email_template = EmailTemplate.query.filter_by(
                    category='financial_aid',
                    division=None,
                    is_active=True
                ).first()
        except Exception as e:
            current_app.logger.warning(f"Error querying email template: {str(e)}")
        
        # Send emails to each recipient
        from email_service import EmailService
        email_service = EmailService()
        
        success_count = 0
        errors = []
        
        # Convert recipient types to actual email addresses
        recipient_emails = []
        for recipient_type in recipients:
            if recipient_type == 'student' and student.email:
                recipient_emails.append(student.email)
            elif recipient_type == 'father' and student.father_email:
                recipient_emails.append(student.father_email)
            elif recipient_type == 'mother' and student.mother_email:
                recipient_emails.append(student.mother_email)
        
        if not recipient_emails:
            return jsonify({'error': 'No valid email addresses found for selected recipients'}), 400
        
        current_app.logger.info(f"🔍 DEBUG: Financial aid - About to send to {len(recipient_emails)} recipients: {recipient_emails}")
        
        for recipient_email in recipient_emails:
            try:
                current_app.logger.info(f"🔍 DEBUG: Financial aid - Starting email to: {recipient_email}")
                
                # Get school name based on division
                school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
                student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
                
                current_app.logger.info(f"🔍 DEBUG: Financial aid - School: {school_name}, Student: {student_name}")
                
                # Use custom email content if provided, otherwise use template, otherwise fallback
                if custom_email_subject and custom_email_body:
                    subject = custom_email_subject
                    html_content = custom_email_body
                elif email_template:
                    # Use email template with variable substitution
                    template_vars = {
                        'student_name': student_name,
                        'student_first_name': student.student_first_name or '',
                        'student_last_name': student.student_last_name or '',
                        'father_title': student.father_title or '',
                        'father_name': f"{student.father_first_name or ''} {student.father_last_name or ''}".strip(),
                        'father_email': student.father_email or '',
                        'mother_title': student.mother_title or '',
                        'mother_name': f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip(),
                        'mother_email': student.mother_email or '',
                        'academic_year': academic_year.year_label,
                        'school_name': school_name,
                        'division': student.division,
                        'current_date': datetime.now().strftime('%B %d, %Y'),
                        'secure_upload_url': url_for('secure_forms.upload_form', token=secure_link.token, _external=True),
                        'secure_upload_expires': secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p')
                    }
                    
                    # Use the correct render method that returns a dictionary
                    rendered = email_template.render(template_vars)
                    subject = rendered['subject']
                    html_content = rendered['body']
                else:
                    # Fallback to hardcoded content
                    subject = f"Financial Aid Application - {school_name}"
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #0d6efd;">{school_name}</h2>
                        <h3>Financial Aid Application</h3>
                        
                        <p>Dear {student_name} Family,</p>
                        
                        <p>Thank you for your interest in financial aid for the {academic_year.year_label} academic year.</p>
                        
                        <p>Please find the financial aid application form attached to this email. You can either:</p>
                        
                        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <h4 style="color: #495057; margin-top: 0;">Option 1: Print & Mail</h4>
                            <ul style="color: #6c757d;">
                                <li>Print the attached PDF form</li>
                                <li>Complete it by hand</li>
                                <li>Mail or deliver to our office</li>
                            </ul>
                            
                            <h4 style="color: #495057;">Option 2: Secure Online Upload (Recommended)</h4>
                            <ul style="color: #6c757d;">
                                <li>Complete the attached form</li>
                                <li>Upload the completed form and supporting documents securely</li>
                                <li>Receive instant confirmation</li>
                            </ul>
                            
                            <div style="text-align: center; margin: 20px 0;">
                                <a href="{url_for('secure_forms.upload_form', token=secure_link.token, _external=True)}" 
                                   style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 16px; display: inline-block;">
                                    🔒 Upload Documents Securely
                                </a>
                            </div>
                        </div>
                        
                        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                            <h4 style="margin-top: 0;">Supporting Documents Needed:</h4>
                            <ul style="margin: 0;">
                                <li>Completed Financial Aid Application (attached)</li>
                                <li>Most recent tax returns</li>
                                <li>W-2 forms</li>
                                <li>Bank statements</li>
                                <li>Any other financial documentation</li>
                            </ul>
                            <p style="margin-bottom: 0;"><strong>Secure Upload Link Expires:</strong> {secure_link.expires_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                        </div>
                        
                        <p><strong>Important:</strong> The application deadline is approaching. Please complete and submit your 
                        application as soon as possible to ensure consideration for financial aid.</p>
                        
                        <p>If you have any questions about the financial aid process, please contact our financial aid office.</p>
                        
                        <p>Best regards,<br>
                        <strong>Financial Aid Office</strong><br>
                        {school_name}</p>
                    </div>
                    """
                
                # Get the appropriate financial aid form template for this division
                from pdf_template_service import PDFTemplateService
                template = PDFTemplateService.get_template_for_division(student.division, 'financial_aid_form')
                
                # Send email with or without attachment based on template availability
                if template and template.file_path and os.path.exists(template.file_path):
                    # Send with PDF attachment
                    email_data = {
                        'recipients': [recipient_email],
                        'subject': subject,
                        'message': html_content,
                        'attachment_path': template.file_path,
                        'attachment_name': f'Financial_Aid_Application_{student.division}.pdf'
                    }
                    
                    email_result = email_service.send_email_with_attachment(email_data)
                    if email_result.get('success'):
                        success_count += 1
                        current_app.logger.info(f"✅ Financial aid form sent with attachment to {recipient_email}")
                    else:
                        error_msg = email_result.get('error', 'Unknown error')
                        current_app.logger.error(f"❌ Failed to send email with attachment to {recipient_email}: {error_msg}")
                        raise Exception(f"Email sending failed: {error_msg}")
                else:
                    # Send without attachment (using basic email method like tuition contracts)
                    email_result = email_service.send_email(
                        to_email=recipient_email,
                        subject=subject,
                        html_content=html_content
                    )
                    if email_result.get('success'):
                        success_count += 1
                        current_app.logger.info(f"✅ Financial aid form sent (no PDF template available) to {recipient_email}")
                    else:
                        error_msg = email_result.get('error', 'Unknown error')
                        current_app.logger.error(f"❌ Failed to send email to {recipient_email}: {error_msg}")
                        raise Exception(f"Email sending failed: {error_msg}")
                
            except Exception as e:
                errors.append(f"Failed to send to {recipient_email}: {str(e)}")
        
        # Update student record and secure link
        if success_count > 0:
            # Mark secure link as sent
            secure_link.sent_date = datetime.utcnow()
            
            # Update financial aid status
            from models import TuitionRecord
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year.id
            ).first()
            
            if not tuition_record:
                tuition_record = TuitionRecord(
                    student_id=student_id,
                    academic_year_id=academic_year.id
                )
                db.session.add(tuition_record)
            
            tuition_record.financial_aid_app_sent = True
            tuition_record.financial_aid_app_sent_date = datetime.utcnow()
            tuition_record.updated_by = current_user.username
            
            db.session.commit()
        
        if errors:
            return jsonify({
                'success': True,
                'message': f'Financial aid form sent to {success_count} recipients',
                'warnings': errors
            })
        else:
            return jsonify({
                'success': True,
                'message': f'Financial aid form sent successfully to {success_count} recipients'
            })
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending financial aid form: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/api/students/<student_id>/resend-financial-aid-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def resend_financial_aid_form_with_recipients(student_id):
    """Resend financial aid form with selected recipients (includes secure upload link)"""
    try:
        # Use the same logic as send, but update the message
        result = send_financial_aid_form_with_recipients(student_id)
        
        if result[0].get_json().get('success'):
            # Update the message to indicate resend
            response_data = result[0].get_json()
            response_data['message'] = response_data['message'].replace('sent', 'resent')
            return jsonify(response_data)
        else:
            return result
            
    except Exception as e:
        current_app.logger.error(f"Error resending financial aid form: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/api/students/<student_id>/send-tuition-contract', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_tuition_contract_with_recipients(student_id):
    """Send tuition contract with selected recipients"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        recipients = data.get('recipients', [])
        
        if not recipients:
            return jsonify({'error': 'No recipients selected'}), 400
        
        # Get current academic year
        from models import AcademicYear
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not academic_year:
            return jsonify({'error': 'No active academic year'}), 400
        
        # First generate the contract if it doesn't exist
        from models import TuitionRecord
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id
        ).first()
        
        if not tuition_record:
            return jsonify({'error': 'No tuition record found. Please set tuition amount first.'}), 400
        
        # Generate contract PDF if not already generated
        if not tuition_record.tuition_contract_generated:
            # Call the existing contract generation logic
            from blueprints.financial import generate_tuition_contract
            contract_result = generate_tuition_contract(student_id)
            if contract_result[1] != 200:  # Check status code
                return contract_result
        
        # Send emails to each recipient
        from email_service import EmailService
        email_service = EmailService()
        
        success_count = 0
        errors = []
        
        for recipient_email in recipients:
            try:
                # Get school name based on division
                school_name = "Yeshiva Zichron Aryeh" if student.division == 'YZA' else "Yeshiva Ohr Hatzafon"
                student_name = student.student_name or f"{student.student_first_name} {student.student_last_name}".strip()
                
                subject = f"Tuition Contract for {academic_year.year_label} - {school_name}"
                
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #0d6efd;">{school_name}</h2>
                    <h3>Tuition Contract</h3>
                    
                    <p>Dear {student_name} Family,</p>
                    
                    <p>Your tuition contract for the {academic_year.year_label} academic year is ready for your review and signature.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h4 style="color: #495057; margin-top: 0;">Contract Details:</h4>
                        <ul style="color: #6c757d;">
                            <li><strong>Student:</strong> {student_name}</li>
                            <li><strong>Division:</strong> {student.division}</li>
                            <li><strong>Academic Year:</strong> {academic_year.year_label}</li>
                        </ul>
                    </div>
                    
                    <p>Please review the contract carefully and sign it using our secure digital signature system. 
                    You will receive a separate email with the signing instructions and secure link.</p>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                        <p style="margin: 0;"><strong>Important:</strong> Please complete the contract signing process 
                        within 14 days to secure your enrollment for the upcoming academic year.</p>
                    </div>
                    
                    <p>If you have any questions about the contract terms or tuition amounts, please contact our financial office.</p>
                    
                    <p>Best regards,<br>
                    <strong>Financial Office</strong><br>
                    {school_name}</p>
                </div>
                """
                
                email_result = email_service.send_email(
                    to_email=recipient_email,
                    subject=subject,
                    html_content=html_content
                )
                if email_result.get('success'):
                    success_count += 1
                else:
                    current_app.logger.error(f"❌ Failed to send tuition contract email: {email_result.get('error', 'Unknown error')}")
                    raise Exception(email_result.get('error', 'Email sending failed'))
                
            except Exception as e:
                errors.append(f"Failed to send to {recipient_email}: {str(e)}")
        
        # Update tuition record
        if success_count > 0:
            tuition_record.tuition_contract_sent = True
            tuition_record.tuition_contract_sent_date = datetime.utcnow()
            tuition_record.updated_by = current_user.username
            
            db.session.commit()
        
        if errors:
            return jsonify({
                'success': True,
                'message': f'Tuition contract sent to {success_count} recipients',
                'warnings': errors,
                'fallback': False,
                'document_id': getattr(tuition_record, 'opensign_document_id', None)
            })
        else:
            return jsonify({
                'success': True,
                'message': f'Tuition contract sent successfully to {success_count} recipients',
                'fallback': False,
                'document_id': getattr(tuition_record, 'opensign_document_id', None)
            })
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending tuition contract: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/api/students/<student_id>/send-acceptance-email', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_acceptance_email_with_recipients(student_id):
    """Send acceptance email to specified recipients."""
    try:
        data = request.get_json() or {}
        recipients = data.get('recipients', ['student'])
        
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get recipient email addresses
        recipient_emails = []
        if 'student' in recipients and student.email:
            recipient_emails.append(student.email)
        if 'father' in recipients and student.father_email:
            recipient_emails.append(student.father_email)
        if 'mother' in recipients and student.mother_email:
            recipient_emails.append(student.mother_email)
        
        if not recipient_emails:
            return jsonify({'error': 'No valid email addresses found for selected recipients'}), 400
        
        # Send email using existing email service
        from email_service import EmailService
        result = EmailService.send_acceptance_email(student_id, current_user.username)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Acceptance email sent to: {', '.join(recipient_emails)}",
                'recipients': recipients
            })
        else:
            return jsonify({'error': result['message']}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error sending acceptance email: {str(e)}")
        return jsonify({'error': str(e)}), 500


@students.route('/students/<student_id>/view-uploaded-contract')
@login_required
@permission_required('view_students')
def view_uploaded_contract(student_id):
    """View/download uploaded signed contract for a student"""
    try:
        # Get student
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            current_app.logger.error(f"Student not found: {student_id}")
            abort(404)
        
        # Import required models
        from models import FormUploadLog, SecureFormLink, FinancialRecord, AcademicYear
        
        # Get the most recent contract document using the unified approach
        # First, try to get the student's financial record to use the latest_contract_document property
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        financial_record = None
        
        if current_year:
            financial_record = FinancialRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=current_year.id
            ).first()
        
        # Use the unified latest contract document property if available
        uploaded_contract_file = None
        if financial_record:
            latest_contract = financial_record.latest_contract_document
            if latest_contract:
                uploaded_contract_file = latest_contract
                current_app.logger.info(f"Found contract via FinancialRecord: {latest_contract['source']}")
        
        # Fallback to direct queries if no financial record or latest contract
        if not uploaded_contract_file:
            # Try secure uploads first (tuition contracts)
            try:
                secure_upload = db.session.query(FormUploadLog).join(
                    SecureFormLink, 
                    FormUploadLog.secure_link_id == SecureFormLink.id
                ).filter(
                    FormUploadLog.student_id == student_id,
                    SecureFormLink.form_type == 'tuition_contract',
                    FormUploadLog.processing_status == 'processed'
                ).order_by(FormUploadLog.uploaded_at.desc()).first()
                
                if secure_upload:
                    uploaded_contract_file = {
                        'id': secure_upload.id,
                        'type': 'secure',
                        'filename': secure_upload.original_filename,
                        'file_path': secure_upload.file_path,
                        'uploaded_at': secure_upload.uploaded_at,
                        'source': 'Secure Upload'
                    }
            except Exception as e:
                current_app.logger.warning(f"Secure upload query failed: {str(e)}")
        
        # Final fallback - any processed upload for this student
        if not uploaded_contract_file:
            try:
                any_upload = FormUploadLog.query.filter_by(
                    student_id=student_id,
                    processing_status='processed'
                ).order_by(FormUploadLog.uploaded_at.desc()).first()
                
                if any_upload:
                    uploaded_contract_file = {
                        'id': any_upload.id,
                        'type': 'secure',
                        'filename': any_upload.original_filename,
                        'file_path': any_upload.file_path,
                        'uploaded_at': any_upload.uploaded_at,
                        'source': 'Secure Upload'
                    }
            except Exception as e:
                current_app.logger.warning(f"Fallback query failed: {str(e)}")
        
        if not uploaded_contract_file:
            current_app.logger.error(f"No uploaded contract file found for student {student_id}")
            abort(404)
        
        # Check if file exists on disk - try multiple possible paths
        file_path = uploaded_contract_file.get('file_path') if isinstance(uploaded_contract_file, dict) else uploaded_contract_file.file_path
        if not file_path:
            current_app.logger.error(f"No file path for uploaded contract: {uploaded_contract_file.id}")
            abort(404)
        
        # Try different possible file locations
        possible_paths = []
        
        # 1. Use the path as stored in database
        possible_paths.append(file_path)
        
        # 2. Try with uploads/ prefix if not already present
        if not file_path.startswith('uploads/'):
            possible_paths.append(f"uploads/{file_path}")
        
        # 3. Try relative to current working directory
        if not os.path.isabs(file_path):
            possible_paths.append(os.path.join(os.getcwd(), file_path))
            possible_paths.append(os.path.join(os.getcwd(), 'uploads', file_path))
        
        # Find the first path that exists
        actual_file_path = None
        for test_path in possible_paths:
            current_app.logger.info(f"Checking file path: {test_path}")
            if os.path.exists(test_path):
                actual_file_path = test_path
                current_app.logger.info(f"Found file at: {actual_file_path}")
                break
        
        if not actual_file_path:
            current_app.logger.error(f"Contract file not found at any of these locations: {possible_paths}")
            abort(404)
        
        # Generate appropriate filename
        student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
        if not student_name:
            student_name = f"Student_{student_id[:8]}"
        
        # Clean filename for download
        safe_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        uploaded_date = uploaded_contract_file.get('uploaded_at') if isinstance(uploaded_contract_file, dict) else uploaded_contract_file.uploaded_at
        download_filename = f"Signed_Contract_{safe_name}_{uploaded_date.strftime('%Y%m%d')}.pdf"
        
        current_app.logger.info(f"Serving uploaded contract for student {student_id}: {actual_file_path}")
        
        return send_file(
            actual_file_path,
            as_attachment=False,  # View in browser
            download_name=download_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error serving uploaded contract for student {student_id}: {str(e)}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        abort(500)