#!/usr/bin/env python3
"""Email Templates Management Blueprint"""

from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, EmailTemplate, EmailTemplateVariable, EmailTemplateHistory, Student, DivisionConfig
from utils.decorators import permission_required
from datetime import datetime
import re

email_templates = Blueprint('email_templates', __name__)

# Common variables available in all email templates
COMMON_EMAIL_VARIABLES = {
    'student': {
        'student_name': 'Full student name',
        'student_first_name': 'Student first name',
        'student_last_name': 'Student last name',
        'student_email': 'Student email address',
        'student_phone': 'Student phone number',
        'student_division': 'Student division (YZA/YOH/KOLLEL)',
        'student_id': 'Student ID number',
        'hebrew_name': 'Student Hebrew name',
        'date_of_birth': 'Student date of birth'
    },
    'parents': {
        'father_title': 'Father title (Mr., Dr., Rabbi)',
        'father_name': 'Father full name',
        'father_email': 'Father email address',
        'father_phone': 'Father phone number',
        'mother_title': 'Mother title (Mrs., Ms., Dr.)',
        'mother_name': 'Mother full name',
        'mother_email': 'Mother email address',
        'mother_phone': 'Mother phone number'
    },
    'academic': {
        'academic_year': 'Current academic year',
        'start_date': 'Academic year start date',
        'orientation_date': 'Orientation date',
        'registration_deadline': 'Registration deadline'
    },
    'financial': {
        'tuition_amount': 'Total tuition amount',
        'financial_aid_amount': 'Financial aid amount',
        'final_amount': 'Final amount due',
        'payment_due_date': 'Payment due date',
        'payment_plan': 'Payment plan details'
    },
    'system': {
        'current_date': 'Current date',
        'school_name': 'School/division name',
        'school_address': 'School address',
        'school_phone': 'School phone',
        'school_email': 'School email',
        'portal_url': 'Student portal URL',
        'secure_upload_link': 'Secure upload URL',
        'opensign_link': 'OpenSign signature URL'
    }
}

@email_templates.route('/email-templates')
@login_required
@permission_required('manage_users')
def template_manager():
    """Email template management interface"""
    # Get template counts by category
    template_counts = db.session.query(
        EmailTemplate.category,
        db.func.count(EmailTemplate.id)
    ).filter_by(is_active=True).group_by(EmailTemplate.category).all()
    
    counts_dict = dict(template_counts)
    
    # Get all divisions
    divisions = ['YZA', 'YOH', 'KOLLEL']
    
    return render_template('email_templates/manager.html',
                         template_counts=counts_dict,
                         common_variables=COMMON_EMAIL_VARIABLES,
                         divisions=divisions)

@email_templates.route('/api/email-templates')
@login_required
@permission_required('manage_users')
def get_templates():
    """Get all email templates"""
    try:
        category = request.args.get('category')
        division = request.args.get('division')
        search = request.args.get('search')
        
        query = EmailTemplate.query
        
        if category:
            query = query.filter_by(category=category)
        if division:
            query = query.filter(db.or_(EmailTemplate.division == division, 
                                      EmailTemplate.division == None))
        if search:
            query = query.filter(db.or_(
                EmailTemplate.name.contains(search),
                EmailTemplate.subject_template.contains(search)
            ))
        
        templates = query.order_by(EmailTemplate.category, EmailTemplate.name).all()
        
        return jsonify({
            'success': True,
            'templates': [{
                'id': t.id,
                'name': t.name,
                'category': t.category,
                'division': t.division or 'Global',
                'subject': t.subject_template,
                'body_preview': t.body_template[:150] + '...' if len(t.body_template) > 150 else t.body_template,
                'is_active': t.is_active,
                'has_pdf': t.include_pdf_attachment,
                'pdf_template_name': t.pdf_template.name if t.pdf_template else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                'updated_by': t.updated_by,
                'version': t.version,
                'variables': t.get_variables()
            } for t in templates]
        })
    except Exception as e:
        current_app.logger.error(f'Error fetching email templates: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>')
@login_required
@permission_required('manage_users')
def get_template(template_id):
    """Get a specific email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        
        return jsonify({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'category': template.category,
                'division': template.division,
                'subject_template': template.subject_template,
                'body_template': template.body_template,
                'body_format': template.body_format,
                'include_pdf_attachment': template.include_pdf_attachment,
                'pdf_template_id': template.pdf_template_id,
                'cc_addresses': template.cc_addresses,
                'bcc_addresses': template.bcc_addresses,
                'reply_to_address': template.reply_to_address,
                'description': template.description,
                'is_active': template.is_active,
                'variables': template.get_variables()
            }
        })
    except Exception as e:
        current_app.logger.error(f'Error fetching template: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_template():
    """Create a new email template"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('category') or not data.get('subject_template'):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Check for duplicate name
        existing = EmailTemplate.query.filter_by(
            name=data['name'],
            category=data['category'],
            division=data.get('division')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Template with this name already exists'}), 400
        
        # Create new template
        template = EmailTemplate(
            name=data['name'],
            category=data['category'],
            division=data.get('division'),
            subject_template=data['subject_template'],
            body_template=data.get('body_template', ''),
            body_format=data.get('body_format', 'html'),
            include_pdf_attachment=data.get('include_pdf_attachment', False),
            pdf_template_id=data.get('pdf_template_id'),
            cc_addresses=data.get('cc_addresses'),
            bcc_addresses=data.get('bcc_addresses'),
            reply_to_address=data.get('reply_to_address'),
            description=data.get('description'),
            is_active=data.get('is_active', True),
            created_by=current_user.username,
            updated_by=current_user.username
        )
        
        db.session.add(template)
        db.session.commit()
        
        # Create history entry
        history = EmailTemplateHistory(
            template_id=template.id,
            version=1,
            subject_template=template.subject_template,
            body_template=template.body_template,
            changed_by=current_user.username,
            change_description='Template created'
        )
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email template created successfully',
            'template_id': template.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating template: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>', methods=['PUT'])
@login_required
@permission_required('manage_users')
def update_template(template_id):
    """Update an email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        data = request.get_json()
        
        # Store old values for history
        old_subject = template.subject_template
        old_body = template.body_template
        
        # Update fields
        template.name = data.get('name', template.name)
        template.category = data.get('category', template.category)
        template.division = data.get('division', template.division)
        template.subject_template = data.get('subject_template', template.subject_template)
        template.body_template = data.get('body_template', template.body_template)
        template.body_format = data.get('body_format', template.body_format)
        template.include_pdf_attachment = data.get('include_pdf_attachment', template.include_pdf_attachment)
        template.pdf_template_id = data.get('pdf_template_id', template.pdf_template_id)
        template.cc_addresses = data.get('cc_addresses', template.cc_addresses)
        template.bcc_addresses = data.get('bcc_addresses', template.bcc_addresses)
        template.reply_to_address = data.get('reply_to_address', template.reply_to_address)
        template.description = data.get('description', template.description)
        template.is_active = data.get('is_active', template.is_active)
        template.updated_by = current_user.username
        template.updated_at = datetime.utcnow()
        template.version += 1
        
        # Create history entry if content changed
        if old_subject != template.subject_template or old_body != template.body_template:
            history = EmailTemplateHistory(
                template_id=template.id,
                version=template.version,
                subject_template=template.subject_template,
                body_template=template.body_template,
                changed_by=current_user.username,
                change_description=f'Template updated by {current_user.username}'
            )
            db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email template updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error updating template: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>', methods=['DELETE'])
@login_required
@permission_required('manage_users')
def delete_template(template_id):
    """Delete an email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        
        # Don't actually delete, just mark as inactive
        template.is_active = False
        template.updated_by = current_user.username
        template.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email template deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting template: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>/preview', methods=['POST'])
@login_required
@permission_required('manage_users')
def preview_template(template_id):
    """Preview an email template with sample data"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        data = request.get_json()
        
        # Get sample student or use provided student_id
        student_id = data.get('student_id')
        if student_id:
            student = Student.query.get(student_id)
        else:
            # Get a sample student for preview
            student = Student.query.filter_by(division=template.division or 'YZA').first()
        
        if not student:
            # Create mock student data
            context = {
                'student_name': 'John Doe',
                'student_first_name': 'John',
                'student_last_name': 'Doe',
                'student_email': 'john.doe@example.com',
                'student_phone': '(555) 123-4567',
                'student_division': template.division or 'YZA',
                'student_id': '12345',
                'hebrew_name': 'יוחנן בן יעקב',
                'date_of_birth': 'January 1, 2000',
                'father_title': 'Mr.',
                'father_name': 'James Doe',
                'father_email': 'james.doe@example.com',
                'mother_title': 'Mrs.',
                'mother_name': 'Jane Doe',
                'mother_email': 'jane.doe@example.com',
                'academic_year': '2024-2025',
                'current_date': datetime.now().strftime('%B %d, %Y'),
                'school_name': 'Yeshiva Zichron Aryeh' if template.division == 'YZA' else 'Yeshiva Ohr Hatzafon',
                'tuition_amount': '$4,260',
                'secure_upload_link': 'https://portal.school.edu/secure/upload/abc123',
                'opensign_link': 'https://opensign.school.edu/sign/xyz789'
            }
        else:
            # Build context from actual student data
            context = {
                'student_name': student.student_name or f"{student.student_first_name} {student.student_last_name}",
                'student_first_name': student.student_first_name or '',
                'student_last_name': student.student_last_name or '',
                'student_email': student.email or '',
                'student_phone': student.phone_number or '',
                'student_division': student.division,
                'student_id': str(student.id),
                'hebrew_name': student.hebrew_name or '',
                'date_of_birth': student.date_of_birth.strftime('%B %d, %Y') if student.date_of_birth else '',
                'father_title': student.father_title or '',
                'father_name': f"{student.father_first_name or ''} {student.father_last_name or ''}".strip(),
                'father_email': student.father_email or '',
                'mother_title': student.mother_title or '',
                'mother_name': f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip(),
                'mother_email': student.mother_email or '',
                'academic_year': '2024-2025',
                'current_date': datetime.now().strftime('%B %d, %Y'),
                'school_name': 'Yeshiva Zichron Aryeh' if student.division == 'YZA' else 'Yeshiva Ohr Hatzafon'
            }
        
        # Add any custom context from request
        if data.get('context'):
            context.update(data['context'])
        
        # Render the template
        rendered = template.render(context)
        
        return jsonify({
            'success': True,
            'preview': {
                'subject': rendered['subject'],
                'body': rendered['body'],
                'format': rendered['format'],
                'context_used': context
            }
        })
        
    except Exception as e:
        current_app.logger.error(f'Error previewing template: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>/send-test', methods=['POST'])
@login_required
@permission_required('manage_users')
def send_test_email(template_id):
    """Send a test email using the template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        data = request.get_json()
        
        test_email = data.get('email', current_user.email)
        if not test_email:
            return jsonify({'success': False, 'error': 'No test email address provided'}), 400
        
        # Generate preview with test data
        preview_response = preview_template(template_id)
        preview_data = preview_response.get_json()
        
        if not preview_data['success']:
            return jsonify({'success': False, 'error': 'Failed to generate preview'}), 500
        
        # Send test email
        from email_service import EmailService
        from flask_mail import Message
        from extensions import mail
        
        preview = preview_data['preview']
        
        # Get email config for division
        email_config = EmailService.get_email_config(template.division or 'YZA')
        
        msg = Message(
            subject=f"[TEST] {preview['subject']}",
            sender=(email_config['from_name'], email_config['from_email']),
            recipients=[test_email],
            html=preview['body'] if preview['format'] == 'html' else None,
            body=preview['body'] if preview['format'] == 'plain' else None,
            reply_to=template.reply_to_address or email_config['reply_to']
        )
        
        # Add CC/BCC if specified
        if template.cc_addresses:
            msg.cc = [addr.strip() for addr in template.cc_addresses.split(',')]
        if template.bcc_addresses:
            msg.bcc = [addr.strip() for addr in template.bcc_addresses.split(',')]
        
        mail.send(msg)
        
        return jsonify({
            'success': True,
            'message': f'Test email sent successfully to {test_email}'
        })
        
    except Exception as e:
        current_app.logger.error(f'Error sending test email: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/create-defaults', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_default_templates():
    """Create default email templates for all divisions"""
    try:
        created_count = 0
        
        # Default templates to create
        default_templates = [
            # Acceptance letters
            {
                'name': 'YZA Acceptance Letter',
                'category': 'acceptance',
                'division': 'YZA',
                'subject_template': 'Acceptance to Yeshiva Zichron Aryeh - Congratulations!',
                'body_template': '<h2>Yeshiva Zichron Aryeh</h2><p>Dear {{student_name}},</p><p><strong>Congratulations!</strong> We are delighted to inform you that you have been accepted to Yeshiva Zichron Aryeh.</p>',
                'include_pdf_attachment': True
            },
            {
                'name': 'YOH Acceptance Letter',
                'category': 'acceptance',
                'division': 'YOH',
                'subject_template': 'Acceptance to Yeshiva Ohr Hatzafon - Congratulations!',
                'body_template': '<h2>Yeshiva Ohr Hatzafon</h2><p>Dear {{student_name}},</p><p><strong>Congratulations!</strong> We are pleased to inform you of your acceptance to Yeshiva Ohr Hatzafon.</p>',
                'include_pdf_attachment': True
            },
            # Enrollment contracts
            {
                'name': 'YZA Enrollment Contract Email',
                'category': 'enrollment_contract',
                'division': 'YZA',
                'subject_template': 'Enrollment Contract for {{academic_year}} - Action Required',
                'body_template': '<p>Dear {{student_name}},</p><p>Your enrollment contract for the {{academic_year}} academic year is ready for your review and signature.</p>',
                'include_pdf_attachment': True
            },
            {
                'name': 'YOH Enrollment Contract Email',
                'category': 'enrollment_contract',
                'division': 'YOH',
                'subject_template': 'Enrollment Contract for {{academic_year}} - Action Required',
                'body_template': '<p>Dear {{student_name}},</p><p>Your enrollment contract for the {{academic_year}} academic year is ready for your review and signature.</p>',
                'include_pdf_attachment': True
            },
            # Financial aid applications
            {
                'name': 'YZA Financial Aid Application',
                'category': 'financial_aid',
                'division': 'YZA',
                'subject_template': 'Financial Aid Application for {{academic_year}}',
                'body_template': '<p>Dear {{student_name}},</p><p>Thank you for your interest in financial aid. Please complete the attached application.</p>',
                'include_pdf_attachment': True
            },
            {
                'name': 'YOH Financial Aid Application',
                'category': 'financial_aid',
                'division': 'YOH',
                'subject_template': 'Financial Aid Application for {{academic_year}}',
                'body_template': '<p>Dear {{student_name}},</p><p>Thank you for your interest in financial aid. Please complete the attached application.</p>',
                'include_pdf_attachment': True
            }
        ]
        
        for template_data in default_templates:
            # Check if template already exists
            existing = EmailTemplate.query.filter_by(
                name=template_data['name'],
                category=template_data['category']
            ).first()
            
            if not existing:
                template = EmailTemplate(
                    created_by=current_user.username,
                    updated_by=current_user.username,
                    **template_data
                )
                db.session.add(template)
                created_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Created {created_count} default email templates'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating default templates: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>/history')
@login_required
@permission_required('manage_users')
def get_template_history(template_id):
    """Get version history for an email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        
        history = EmailTemplateHistory.query.filter_by(
            template_id=template_id
        ).order_by(EmailTemplateHistory.version.desc()).all()
        
        return jsonify({
            'success': True,
            'history': [{
                'id': h.id,
                'version': h.version,
                'subject_template': h.subject_template,
                'body_template': h.body_template,
                'changed_by': h.changed_by,
                'changed_at': h.changed_at.isoformat() if h.changed_at else None,
                'change_description': h.change_description
            } for h in history]
        })
        
    except Exception as e:
        current_app.logger.error(f'Error fetching template history: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500

@email_templates.route('/api/email-templates/<int:template_id>/restore/<int:history_id>', methods=['POST'])
@login_required
@permission_required('manage_users')
def restore_template_version(template_id, history_id):
    """Restore a template to a previous version"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        history_record = EmailTemplateHistory.query.get_or_404(history_id)
        
        if history_record.template_id != template_id:
            return jsonify({'success': False, 'error': 'History record does not belong to this template'}), 400
        
        # Save current version to history before restoring
        current_history = EmailTemplateHistory(
            template_id=template.id,
            version=template.version,
            subject_template=template.subject_template,
            body_template=template.body_template,
            changed_by=current_user.username,
            change_description=f'Backup before restoring to version {history_record.version}'
        )
        db.session.add(current_history)
        
        # Restore template to the selected version
        template.subject_template = history_record.subject_template
        template.body_template = history_record.body_template
        template.version += 1
        template.updated_by = current_user.username
        template.updated_at = datetime.utcnow()
        
        # Create new history entry for the restoration
        restore_history = EmailTemplateHistory(
            template_id=template.id,
            version=template.version,
            subject_template=template.subject_template,
            body_template=template.body_template,
            changed_by=current_user.username,
            change_description=f'Restored to version {history_record.version}'
        )
        db.session.add(restore_history)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Template restored to version {history_record.version} successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error restoring template version: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500 