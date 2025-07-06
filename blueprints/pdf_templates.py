from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from models import db, PDFTemplate, PDFTemplateVariable, DivisionTemplateAssignment
from utils.decorators import permission_required
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime

pdf_templates = Blueprint('pdf_templates', __name__)

ALLOWED_EXTENSIONS = {'pdf'}
TEMPLATE_CATEGORIES = {
    'financial_aid_form': 'Financial Aid Application',
    'tuition_contract': 'Tuition Contract',
    'acceptance_letter': 'Acceptance Letter',
    'enrollment_form': 'Enrollment Form',
    'custom': 'Custom Document'
}

DOCUMENT_TYPES = {
    'financial_aid_form': 'Financial Aid Form',
    'tuition_contract': 'Tuition Contract',
    'acceptance_letter': 'Acceptance Letter',
    'enrollment_form': 'Enrollment Form'
}

# Common variables available in all PDF templates
COMMON_PDF_VARIABLES = {
    'student': {
        'student_name': {'description': 'Full student name', 'example': 'John Smith'},
        'student_first_name': {'description': 'Student first name', 'example': 'John'},
        'student_last_name': {'description': 'Student last name', 'example': 'Smith'},
        'student_email': {'description': 'Student email address', 'example': 'john.smith@example.com'},
        'student_phone': {'description': 'Student phone number', 'example': '(555) 123-4567'},
        'student_division': {'description': 'Student division (YZA/YOH/KOLLEL)', 'example': 'YZA'},
        'student_id': {'description': 'Student ID number', 'example': '12345'},
        'hebrew_name': {'description': 'Student Hebrew name', 'example': 'יוחנן בן שמעון'},
        'date_of_birth': {'description': 'Student date of birth', 'example': '01/15/2005'}
    },
    'parents': {
        'father_title': {'description': 'Father title (Mr., Dr., Rabbi)', 'example': 'Mr.'},
        'father_name': {'description': 'Father full name', 'example': 'David Smith'},
        'father_email': {'description': 'Father email address', 'example': 'david.smith@email.com'},
        'father_phone': {'description': 'Father phone number', 'example': '(555) 987-6543'},
        'mother_title': {'description': 'Mother title (Mrs., Ms., Dr.)', 'example': 'Mrs.'},
        'mother_name': {'description': 'Mother full name', 'example': 'Sarah Smith'},
        'mother_email': {'description': 'Mother email address', 'example': 'sarah.smith@email.com'},
        'mother_phone': {'description': 'Mother phone number', 'example': '(555) 876-5432'},
        'parent_name': {'description': 'Primary parent/guardian name', 'example': 'David Smith'},
        'parent_email': {'description': 'Primary parent email', 'example': 'david.smith@email.com'},
        'parent_phone': {'description': 'Primary parent phone', 'example': '(555) 987-6543'},
        'parent_address': {'description': 'Parent address', 'example': '123 Main St, Brooklyn, NY 11201'}
    },
    'academic': {
        'academic_year': {'description': 'Current academic year', 'example': '2024-2025'},
        'start_date': {'description': 'Academic year start date', 'example': 'September 5, 2024'},
        'orientation_date': {'description': 'Orientation date', 'example': 'August 28, 2024'},
        'registration_deadline': {'description': 'Registration deadline', 'example': 'July 15, 2024'},
        'division': {'description': 'Student division (YZA/YOH/KOLLEL)', 'example': 'YZA'},
        'acceptance_date': {'description': 'Date of acceptance', 'example': 'March 15, 2024'},
        'current_date': {'description': 'Current date', 'example': 'June 25, 2024'},
        'school_year_start': {'description': 'School year start date', 'example': 'September 5, 2024'},
        'school_year_end': {'description': 'School year end date', 'example': 'June 15, 2025'}
    },
    'financial': {
        'tuition_amount': {'description': 'Total tuition amount', 'example': '$25,000.00'},
        'total_tuition': {'description': 'Alias for total tuition', 'example': '$25,000.00'},
        'registration_fee': {'description': 'Registration fee amount', 'example': '$500.00'},
        'registration_fee_option': {'description': 'How registration fee is handled (upfront or rolled_in)', 'example': 'upfront'},
        'room_amount': {'description': 'Room charge amount', 'example': '$3,500.00'},
        'board_amount': {'description': 'Board/meal charge amount', 'example': '$2,800.00'},
        'room_board': {'description': 'Combined room and board amount', 'example': '$6,300.00'},
        'financial_aid_amount': {'description': 'Financial aid amount awarded', 'example': '$5,000.00'},
        'final_amount': {'description': 'Final amount due after aid', 'example': '$20,000.00'},
        'balance_due': {'description': 'Outstanding balance due', 'example': '$18,750.00'},
        'total_amount': {'description': 'Total amount (formatted with $)', 'example': '$25,000.00'},
        'payment_due_date': {'description': 'Payment due date', 'example': 'August 1, 2024'}
    },
    'payment_methods': {
        'payment_plan': {'description': 'Selected payment plan', 'example': 'Monthly (10 payments)'},
        'payment_timing': {'description': 'Payment timing (upfront or monthly)', 'example': 'monthly'},
        'payment_method': {'description': 'Payment method (credit_card, ach, third_party)', 'example': 'credit_card'},
        'cc_holder_name': {'description': 'Credit card holder name', 'example': 'David Smith'},
        'cc_exp_date': {'description': 'Credit card expiration date', 'example': '12/2026'},
        'cc_zip': {'description': 'Billing zip code', 'example': '11201'},
        'cc_charge_date': {'description': 'Day of month to charge credit card', 'example': '1st'},
        'ach_account_holder_name': {'description': 'ACH account holder name', 'example': 'David Smith'},
        'ach_routing_number': {'description': 'Bank routing number', 'example': '021000021'},
        'ach_debit_date': {'description': 'Day of month to debit ACH', 'example': '1st'},
        'third_party_payer_name': {'description': 'Third party payer name', 'example': 'Abraham Cohen'},
        'third_party_payer_relationship': {'description': 'Relationship to student (parent, grandparent, sponsor)', 'example': 'grandfather'},
        'third_party_payer_contact': {'description': 'Third party contact information', 'example': 'abraham.cohen@email.com'}
    },
    'payment_schedule': {
        'payment_schedule_table': {'description': 'Complete payment schedule table (HTML)', 'example': '<table>...</table>'},
        'first_payment_date': {'description': 'First payment due date', 'example': 'September 1, 2024'},
        'final_payment_date': {'description': 'Final payment due date', 'example': 'June 1, 2025'},
        'last_payment_date': {'description': 'Last payment due date', 'example': 'June 1, 2025'},
        'monthly_payment_amount': {'description': 'Regular monthly payment amount', 'example': '$2,000.00'},
        'number_of_payments': {'description': 'Total number of payments', 'example': '10'},
        'upfront_amount_due': {'description': 'Amount due at contract signing', 'example': '$1,250.00'}
    },
    'system': {
        'current_date': {'description': 'Current date', 'example': 'June 25, 2024'},
        'school_name': {'description': 'School/division name', 'example': 'Yeshiva Zichron Aryeh'},
        'school_address': {'description': 'School address', 'example': '1234 Education Ave, Brooklyn, NY 11230'},
        'school_phone': {'description': 'School phone number', 'example': '(718) 555-0123'},
        'school_email': {'description': 'School email address', 'example': 'office@yeshiva.edu'},
        'portal_url': {'description': 'Student portal URL', 'example': 'https://portal.yeshiva.edu'}
    }
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@pdf_templates.route('/pdf-templates')
@login_required
@permission_required('manage_users')
def template_manager():
    """PDF Template Manager main page"""
    templates = PDFTemplate.query.filter_by(is_active=True).order_by(PDFTemplate.category, PDFTemplate.name).all()
    return render_template('pdf_templates/manager.html', 
                         templates=templates,
                         categories=TEMPLATE_CATEGORIES,
                         document_types=DOCUMENT_TYPES,
                         common_variables=COMMON_PDF_VARIABLES)

@pdf_templates.route('/api/pdf-templates', methods=['GET'])
@login_required
@permission_required('manage_users')
def get_templates():
    """Get all active PDF templates"""
    try:
        category = request.args.get('category')
        division = request.args.get('division')
        
        query = PDFTemplate.query.filter_by(is_active=True)
        
        if category:
            query = query.filter_by(category=category)
        
        if division:
            # Get templates that are global or allowed for this division
            query = query.filter(db.or_(
                PDFTemplate.is_global == True,
                PDFTemplate.allowed_divisions.contains([division])
            ))
        
        templates = query.order_by(PDFTemplate.name).all()
        
        result = []
        for template in templates:
            result.append({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'category': template.category,
                'template_type': template.template_type,
                'is_global': template.is_global,
                'allowed_divisions': template.allowed_divisions or [],
                'version': template.version,
                'created_at': template.created_at.isoformat(),
                'updated_by': template.updated_by,
                'variable_count': template.variables.count()
            })
        
        return jsonify({'success': True, 'templates': result})
    except Exception as e:
        current_app.logger.error(f"Error getting templates: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates/<int:template_id>', methods=['GET'])
@login_required
@permission_required('manage_users')
def get_template(template_id):
    """Get a specific template with its variables"""
    try:
        template = PDFTemplate.query.get_or_404(template_id)
        
        variables = []
        for var in template.variables:
            variables.append({
                'id': var.id,
                'variable_name': var.variable_name,
                'description': var.description,
                'default_value': var.default_value,
                'is_required': var.is_required,
                'variable_type': var.variable_type
            })
        
        return jsonify({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'category': template.category,
                'template_type': template.template_type,
                'content': template.content,
                'file_path': template.file_path,
                'is_global': template.is_global,
                'allowed_divisions': template.allowed_divisions or [],
                'version': template.version,
                'variables': variables
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error getting template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_template():
    """Create a new PDF template"""
    try:
        data = request.form
        
        # Validate required fields
        if not data.get('name') or not data.get('category'):
            return jsonify({'success': False, 'error': 'Name and category are required'}), 400
        
        # Handle file upload if template_type is uploaded_pdf
        file_path = None
        if data.get('template_type') == 'uploaded_pdf':
            if 'template_file' not in request.files:
                return jsonify({'success': False, 'error': 'PDF file is required for uploaded templates'}), 400
            
            file = request.files['template_file']
            if file and allowed_file(file.filename):
                # Create templates directory if it doesn't exist
                upload_dir = os.path.join('static', 'templates', 'pdf')
                os.makedirs(upload_dir, exist_ok=True)
                
                # Generate unique filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{secure_filename(file.filename)}"
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
            else:
                return jsonify({'success': False, 'error': 'Invalid file type. Only PDF files are allowed.'}), 400
        
        # Parse allowed divisions
        allowed_divisions = None
        if not data.get('is_global'):
            divisions = request.form.getlist('allowed_divisions[]')
            if divisions:
                allowed_divisions = divisions
        
        # Create template
        template = PDFTemplate(
            name=data['name'],
            description=data.get('description', ''),
            category=data['category'],
            template_type=data.get('template_type', 'html'),
            content=data.get('content', ''),
            file_path=file_path,
            is_global=data.get('is_global') == 'true',
            allowed_divisions=allowed_divisions,
            created_by=current_user.username,
            updated_by=current_user.username
        )
        
        db.session.add(template)
        db.session.flush()
        
        # Add variables if provided
        variables = json.loads(data.get('variables', '[]'))
        for var in variables:
            template_var = PDFTemplateVariable(
                template_id=template.id,
                variable_name=var['name'],
                description=var.get('description', ''),
                default_value=var.get('default_value', ''),
                is_required=var.get('is_required', True),
                variable_type=var.get('type', 'string')
            )
            db.session.add(template_var)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Template created successfully',
            'template_id': template.id
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates/<int:template_id>', methods=['PUT'])
@login_required
@permission_required('manage_users')
def update_template(template_id):
    """Update an existing template (creates new version)"""
    try:
        template = PDFTemplate.query.get_or_404(template_id)
        
        # Create new version
        new_version = template.create_new_version(current_user.username)
        
        data = request.get_json()
        
        # Update fields
        if 'name' in data:
            new_version.name = data['name']
        if 'description' in data:
            new_version.description = data['description']
        if 'content' in data:
            new_version.content = data['content']
        if 'is_global' in data:
            # Convert string boolean to actual boolean
            is_global_value = data['is_global']
            if isinstance(is_global_value, str):
                new_version.is_global = is_global_value.lower() == 'true'
            else:
                new_version.is_global = bool(is_global_value)
        if 'allowed_divisions' in data:
            new_version.allowed_divisions = data['allowed_divisions'] if not data.get('is_global') else None
        
        db.session.add(new_version)
        db.session.flush()  # This assigns the ID without committing
        
        # Update variables if provided
        if 'variables' in data:
            # Clear existing variables for new version
            variables_data = data['variables']
            if isinstance(variables_data, str):
                try:
                    import json
                    variables_data = json.loads(variables_data)
                except:
                    variables_data = []
            
            if isinstance(variables_data, list):
                for var_data in variables_data:
                    if isinstance(var_data, dict):
                        var = PDFTemplateVariable(
                            template_id=new_version.id,
                            variable_name=var_data.get('name', ''),
                            description=var_data.get('description', ''),
                            default_value=var_data.get('default_value', ''),
                            is_required=var_data.get('is_required', True),
                            variable_type=var_data.get('type', 'string')
                        )
                        db.session.add(var)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Template updated successfully (new version created)',
            'template_id': new_version.id,
            'version': new_version.version
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates/<int:template_id>', methods=['DELETE'])
@login_required
@permission_required('manage_users')
def delete_template(template_id):
    """Soft delete a template (mark as inactive)"""
    try:
        template = PDFTemplate.query.get_or_404(template_id)
        template.is_active = False
        template.updated_by = current_user.username
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Template deleted successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/division-template-assignments', methods=['GET'])
@login_required
@permission_required('view_students')
def get_division_assignments():
    """Get template assignments for divisions"""
    try:
        division = request.args.get('division')
        
        query = DivisionTemplateAssignment.query
        if division:
            query = query.filter_by(division=division)
        
        assignments = query.all()
        
        result = []
        for assignment in assignments:
            result.append({
                'id': assignment.id,
                'division': assignment.division,
                'document_type': assignment.document_type,
                'template_id': assignment.template_id,
                'template_name': assignment.template.name if assignment.template else None,
                'is_default': assignment.is_default
            })
        
        return jsonify({'success': True, 'assignments': result})
    except Exception as e:
        current_app.logger.error(f"Error getting assignments: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/division-template-assignments', methods=['POST'])
@login_required
@permission_required('manage_users')
def assign_template_to_division():
    """Assign a template to a division for a specific document type"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['division', 'document_type', 'template_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        # Check if template exists and is allowed for this division
        template = PDFTemplate.query.get(data['template_id'])
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        if not template.is_global and data['division'] not in (template.allowed_divisions or []):
            return jsonify({'success': False, 'error': 'Template not allowed for this division'}), 400
        
        # If marking as default, unset other defaults for this division/document type
        if data.get('is_default', True):
            DivisionTemplateAssignment.query.filter_by(
                division=data['division'],
                document_type=data['document_type'],
                is_default=True
            ).update({'is_default': False})
        
        # Create or update assignment
        assignment = DivisionTemplateAssignment.query.filter_by(
            division=data['division'],
            document_type=data['document_type'],
            template_id=data['template_id']
        ).first()
        
        if not assignment:
            assignment = DivisionTemplateAssignment(
                division=data['division'],
                document_type=data['document_type'],
                template_id=data['template_id'],
                is_default=data.get('is_default', True),
                assigned_by=current_user.username
            )
            db.session.add(assignment)
        else:
            assignment.is_default = data.get('is_default', True)
            assignment.assigned_by = current_user.username
            assignment.assigned_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Template assigned successfully',
            'assignment_id': assignment.id
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error assigning template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates/<int:template_id>/preview', methods=['POST'])
@login_required
@permission_required('manage_users')
def preview_template(template_id):
    """Preview a template with sample data"""
    try:
        template = PDFTemplate.query.get_or_404(template_id)
        sample_data = request.get_json()
        
        # For now, return a simple preview response
        # In the future, this would generate an actual PDF preview
        return jsonify({
            'success': True,
            'message': 'Preview functionality coming soon',
            'template_name': template.name,
            'sample_data': sample_data
        })
    except Exception as e:
        current_app.logger.error(f"Error previewing template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@pdf_templates.route('/api/pdf-templates/create-default-contract', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_default_contract_template():
    """Create a default comprehensive contract template"""
    try:
        data = request.get_json()
        division = data.get('division', 'YZA')
        
        # Default comprehensive contract template HTML
        default_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.4; margin: 0; padding: 20px; }
        .header-approval { text-align: right; font-size: 10pt; margin-bottom: 20px; }
        .academic-year { text-align: right; font-size: 16pt; font-weight: bold; margin-bottom: 10px; }
        .school-header { text-align: center; font-size: 14pt; font-weight: bold; margin-bottom: 5px; }
        .address { text-align: center; font-size: 10pt; margin-bottom: 20px; }
        .contract-title { text-align: center; font-size: 18pt; font-weight: bold; margin: 30px 0; }
        .student-info { margin-bottom: 20px; }
        .payment-section { margin: 15px 0; }
        .payment-header { font-size: 12pt; font-weight: bold; margin: 8px 0; }
        .payment-fields { margin: 10px 0; }
        .signature-section { margin-top: 40px; }
        .page-break { page-break-before: always; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid black; padding: 8px; text-align: left; }
        th { font-weight: bold; }
        .no-border { border: none; }
        .underline { border-bottom: 1px solid black; display: inline-block; min-width: 200px; }
    </style>
</head>
<body>
    <!-- PAGE 1: CONTRACT & PAYMENT METHODS -->
    <div class="header-approval">Approved By: YJ&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;TC</div>
    
    <div class="academic-year">{{academic_year}}</div>
    
    <div class="school-header">{{school_name}}</div>
    
    <div class="address">
        {{school_address}}<br/>
        Tel: {{school_phone}}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Fax: {{school_fax}}
    </div>
    
    <div class="contract-title">ENROLLMENT CONTRACT</div>
    
    <div class="student-info">
        <strong>Academic Year:</strong> {{academic_year}}<br/>
        <strong>Division:</strong> {{division}}<br/>
        <strong>Student Name:</strong> {{student_name}}<br/>
    </div>
    
    <div style="margin: 20px 0;">
        <strong>Total Amount Due:</strong> ${{total_tuition}}<br/>
        <em>(See Tuition Schedule on Page 2 for detailed breakdown)</em>
    </div>
    
    <div class="payment-section">
        <div class="payment-header">PAYMENT METHOD SELECTION</div>
        <p>Please select ONE payment method and complete all required fields:</p>
        
        <div class="payment-fields">
            <div class="payment-header">☐ Payment Method 1: Credit Card</div>
            <table class="no-border">
                <tr>
                    <td class="no-border">Credit Card Number:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                    <td class="no-border">Exp. Date:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">CVV:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                    <td class="no-border">Zip Code:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">Name on Credit Card:</td>
                    <td class="no-border" colspan="3"><span class="underline" style="min-width: 400px;">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">Day of Month to Charge:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                    <td class="no-border">(Enter 1-28)</td>
                    <td class="no-border"></td>
                </tr>
            </table>
        </div>
        
        <div class="payment-fields">
            <div class="payment-header">☐ Payment Method 2: ACH Debit</div>
            <table class="no-border">
                <tr>
                    <td class="no-border">Name on Account:</td>
                    <td class="no-border" colspan="3"><span class="underline" style="min-width: 400px;">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">Routing Number:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                    <td class="no-border">Account Number:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">Day of Month to Debit:</td>
                    <td class="no-border"><span class="underline">&nbsp;</span></td>
                    <td class="no-border">(Enter 1-28)</td>
                    <td class="no-border"></td>
                </tr>
            </table>
        </div>
        
        <div class="payment-fields">
            <div class="payment-header">☐ Payment Method 3: Post Dated Checks</div>
            <p>I will provide {{number_of_payments}} post-dated checks of ${{monthly_payment}} each</p>
        </div>
        
        <div class="payment-fields">
            <div class="payment-header">☐ Payment Method 4: Third Party Payment</div>
            <table class="no-border">
                <tr>
                    <td class="no-border">Name of Third Party:</td>
                    <td class="no-border"><span class="underline" style="min-width: 400px;">&nbsp;</span></td>
                </tr>
                <tr>
                    <td class="no-border">Relationship to Student:</td>
                    <td class="no-border"><span class="underline" style="min-width: 300px;">&nbsp;</span></td>
                </tr>
            </table>
        </div>
    </div>
    
    <div style="margin: 30px 0;">
        <p>I hereby enroll my son for the {{academic_year}} academic year in {{school_name}}. I understand that this is a binding obligation toward the Yeshiva and that I will be responsible for satisfaction of his tuition obligation as well as all costs incurred by my son, including damage caused to the Yeshiva property. With my signature I hereby accept the terms of this contract and authorize all payments required herein.</p>
    </div>
    
    <div class="signature-section">
        <table class="no-border">
            <tr>
                <td class="no-border">Signature: <span class="underline" style="min-width: 300px;">&nbsp;</span></td>
                <td class="no-border" style="text-align: right;">Date: <span class="underline">&nbsp;</span></td>
            </tr>
        </table>
    </div>
    
    <!-- PAGE 2: TUITION DETAIL & BILLING SCHEDULE -->
    <div class="page-break">
        <div class="contract-title">TUITION DETAIL & BILLING SCHEDULE</div>
        
        <div class="student-info">
            <strong>Student:</strong> {{student_name}}<br/>
            <strong>Academic Year:</strong> {{academic_year}}<br/>
        </div>
        
        <div class="payment-header">TUITION BREAKDOWN</div>
        <table>
            <tr>
                <th>Component</th>
                <th style="text-align: right;">Amount</th>
            </tr>
            {{#tuition_components}}
            <tr>
                <td>{{name}}</td>
                <td style="text-align: right;">${{amount}}</td>
            </tr>
            {{/tuition_components}}
            {{#if registration_fee}}
            <tr>
                <td>Registration Fee</td>
                <td style="text-align: right;">${{registration_fee}}</td>
            </tr>
            {{/if}}
            <tr style="border-top: 2px solid black;">
                <td><strong>TOTAL AMOUNT DUE</strong></td>
                <td style="text-align: right;"><strong>${{total_tuition}}</strong></td>
            </tr>
        </table>
        
        <div class="payment-header" style="margin-top: 30px;">PAYMENT SCHEDULE</div>
        <table>
            <tr>
                <th>Payment #</th>
                <th>Due Date</th>
                <th style="text-align: right;">Amount</th>
            </tr>
            {{#payment_schedule}}
            <tr>
                <td>{{payment_number}}</td>
                <td>{{due_date}}</td>
                <td style="text-align: right;">${{amount}}</td>
            </tr>
            {{/payment_schedule}}
        </table>
        
        <div class="payment-header" style="margin-top: 20px;">IMPORTANT NOTES:</div>
        <ul>
            <li>Late payments may incur additional fees</li>
            <li>Payment method changes must be submitted in writing 30 days in advance</li>
            <li>For questions regarding billing, contact the financial office</li>
            <li>This contract is binding for the full academic year</li>
        </ul>
    </div>
</body>
</html>
        """
        
        # Create the template
        template = PDFTemplate(
            name=f"Comprehensive Contract - {division}",
            template_type="contract",
            division=division,
            content=default_template,
            variables={
                "academic_year": "Academic year (e.g., 2025-2026)",
                "school_name": "School name",
                "school_address": "School address",
                "school_phone": "School phone number",
                "school_fax": "School fax number",
                "division": "Student division",
                "student_name": "Student full name",
                "total_tuition": "Total tuition amount",
                "monthly_payment": "Monthly payment amount",
                "number_of_payments": "Number of payments",
                "registration_fee": "Registration fee amount",
                "tuition_components": "Array of tuition components",
                "payment_schedule": "Array of payment schedule items"
            },
            is_active=True
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Default comprehensive contract template created for {division}',
            'template_id': template.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating default contract template: {str(e)}")
        return jsonify({'error': str(e)}), 500
 