from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required
from models import Application, Student, FileAttachment
from extensions import db
from utils.decorators import permission_required
from utils.helpers import verify_webhook_signature
import phpserialize
import json
import uuid
from datetime import datetime
import os
import requests
from urllib.parse import urlparse, unquote
import mimetypes

webhooks = Blueprint('webhooks', __name__)

# Store last received webhook data (for debugging)
last_webhook_data = None
last_webhook_error = None

def detect_division_from_data(data):
    """Detect division based on form data."""
    # Check division field directly
    if 'division' in data:
        division_value = data['division'].upper()
        if division_value in ['YZA', 'YOH', 'KOLLEL']:
            return division_value
    
    # Check form title/ID patterns
    if 'form_title' in data:
        form_title = data['form_title'].lower()
        if 'yza' in form_title:
            return 'YZA'
        elif 'yoh' in form_title:
            return 'YOH'
        elif 'kollel' in form_title:
            return 'KOLLEL'
    
    # Default to YZA if cannot detect
    return 'YZA'

def process_form_submission(data, division=None):
    """Process the form submission data and create an application."""
    global last_webhook_data, last_webhook_error
    
    try:
        # Detect division if not provided
        if not division:
            division = detect_division_from_data(data)
        
        # Helper function to safely get field values
        def get_field(field_id, default=''):
            """Get field value from data, handling both direct access and nested structures."""
            # Try direct access first
            if field_id in data:
                value = data[field_id]
                if isinstance(value, str):
                    return value.strip()
                return str(value).strip() if value else default
            
            # Try nested field ID format (e.g., "1" for field ID 1)
            if str(field_id) in data:
                value = data[str(field_id)]
                if isinstance(value, str):
                    return value.strip()
                return str(value).strip() if value else default
            
            return default
        
        # Helper function to get numeric fields
        def get_numeric_field(field_id, default=None):
            value = get_field(field_id, '')
            if value:
                try:
                    return float(value)
                except ValueError:
                    return default
            return default
        
        # Helper function for parsed list fields
        def format_parsed_list(parsed_list):
            """Format a parsed list for display."""
            if not parsed_list:
                return ''
            if isinstance(parsed_list, list):
                return ', '.join(str(item) for item in parsed_list if item)
            return str(parsed_list)
        
        # Helper function to parse tuition payment status
        def get_tuition_payment_status():
            """Extract tuition payment status from various possible field formats."""
            # Try different possible field IDs for tuition payment status
            possible_fields = ['tuition_payment_status', '47', 'payment_status', 'financial_status']
            
            for field in possible_fields:
                value = get_field(field, '')
                if value:
                    # Normalize the value
                    value_lower = value.lower()
                    if 'full' in value_lower:
                        return 'Full Payment'
                    elif 'financial' in value_lower and 'aid' in value_lower:
                        return 'Financial Aid'
                    elif 'scholarship' in value_lower:
                        return 'Financial Aid'
                    else:
                        return value
            
            return 'Not Specified'
        
        # Helper function to parse date fields
        def parse_date(date_str):
            """Parse date string in various formats."""
            if not date_str:
                return None
            
            # Try different date formats
            date_formats = [
                '%Y-%m-%d',
                '%m/%d/%Y',
                '%d/%m/%Y',
                '%Y/%m/%d',
                '%m-%d-%Y',
                '%d-%m-%Y'
            ]
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
            
            return None
        
        # Helper function to parse date fields with specific format patterns
        def parse_date_fields(field_prefix):
            """Parse date fields that might be split into year, month, day."""
            year = get_field(f'{field_prefix}_year', '')
            month = get_field(f'{field_prefix}_month', '')
            day = get_field(f'{field_prefix}_day', '')
            
            if year and month and day:
                try:
                    return datetime(int(year), int(month), int(day)).date()
                except ValueError:
                    pass
            
            # Try single field
            date_str = get_field(field_prefix, '')
            return parse_date(date_str)
        
        # Helper function to parse school info
        def parse_school_info_simple(school_text):
            """Simple parser for school information text."""
            if not school_text:
                return []
            
            # Split by common delimiters
            schools = []
            lines = school_text.replace(';', '\n').replace(',', '\n').split('\n')
            
            for line in lines:
                line = line.strip()
                if line and len(line) > 3:  # Ignore very short entries
                    schools.append(line)
            
            return schools[:3]  # Return up to 3 schools
        
        # Create application with all fields
        application = Application(
            id=str(uuid.uuid4()),
            division=division,
            student_name=get_field('student_name') or f"{get_field('student_first_name')} {get_field('student_last_name')}".strip(),
            student_first_name=get_field('student_first_name'),
            student_middle_name=get_field('student_middle_name'),
            student_last_name=get_field('student_last_name'),
            phone_number=get_field('phone_number') or get_field('phone'),
            email=get_field('email'),
            submitted_date=datetime.utcnow(),
            status='Pending',
            hebrew_name=get_field('hebrew_name'),
            informal_name=get_field('informal_name') or get_field('nickname'),
            social_security_number=get_field('social_security_number') or get_field('ssn'),
            date_of_birth=parse_date_fields('date_of_birth') or parse_date(get_field('dob')),
            citizenship=get_field('citizenship'),
            high_school_graduate=get_field('high_school_graduate') or get_field('graduated_high_school'),
            marital_status=get_field('marital_status'),
            spouse_name=get_field('spouse_name'),
            
            # Address fields
            address_line1=get_field('address_line1') or get_field('address'),
            address_line2=get_field('address_line2'),
            address_city=get_field('address_city') or get_field('city'),
            address_state=get_field('address_state') or get_field('state'),
            address_zip=get_field('address_zip') or get_field('zip'),
            address_country=get_field('address_country') or get_field('country'),
            
            # Alternate address
            alt_address_line1=get_field('alt_address_line1') or get_field('alternate_address'),
            alt_address_line2=get_field('alt_address_line2'),
            alt_address_city=get_field('alt_address_city'),
            alt_address_state=get_field('alt_address_state'),
            alt_address_zip=get_field('alt_address_zip'),
            alt_address_country=get_field('alt_address_country'),
            
            # Parent information
            father_title=get_field('father_title'),
            father_first_name=get_field('father_first_name'),
            father_last_name=get_field('father_last_name'),
            father_phone=get_field('father_phone'),
            father_email=get_field('father_email'),
            father_occupation=get_field('father_occupation'),
            mother_title=get_field('mother_title'),
            mother_first_name=get_field('mother_first_name'),
            mother_last_name=get_field('mother_last_name'),
            mother_phone=get_field('mother_phone'),
            mother_email=get_field('mother_email'),
            mother_occupation=get_field('mother_occupation'),
            
            # Grandparents
            paternal_grandfather_first_name=get_field('paternal_grandfather_first_name'),
            paternal_grandfather_last_name=get_field('paternal_grandfather_last_name'),
            paternal_grandfather_phone=get_field('paternal_grandfather_phone'),
            paternal_grandfather_email=get_field('paternal_grandfather_email'),
            paternal_grandfather_address_line1=get_field('paternal_grandfather_address_line1'),
            paternal_grandfather_address_city=get_field('paternal_grandfather_address_city'),
            paternal_grandfather_address_state=get_field('paternal_grandfather_address_state'),
            paternal_grandfather_address_zip=get_field('paternal_grandfather_address_zip'),
            
            maternal_grandfather_first_name=get_field('maternal_grandfather_first_name'),
            maternal_grandfather_last_name=get_field('maternal_grandfather_last_name'),
            maternal_grandfather_phone=get_field('maternal_grandfather_phone'),
            maternal_grandfather_email=get_field('maternal_grandfather_email'),
            maternal_grandfather_address_line1=get_field('maternal_grandfather_address_line1'),
            maternal_grandfather_address_city=get_field('maternal_grandfather_address_city'),
            maternal_grandfather_address_state=get_field('maternal_grandfather_address_state'),
            maternal_grandfather_address_zip=get_field('maternal_grandfather_address_zip'),
            
            # In-laws (if married)
            inlaws_first_name=get_field('inlaws_first_name'),
            inlaws_last_name=get_field('inlaws_last_name'),
            inlaws_phone=get_field('inlaws_phone'),
            inlaws_email=get_field('inlaws_email'),
            inlaws_address_line1=get_field('inlaws_address_line1'),
            inlaws_address_city=get_field('inlaws_address_city'),
            inlaws_address_state=get_field('inlaws_address_state'),
            inlaws_address_zip=get_field('inlaws_address_zip'),
            
            # Educational information
            high_school_info=get_field('high_school_info') or format_parsed_list(parse_school_info_simple(get_field('high_schools'))),
            seminary_info=get_field('seminary_info') or format_parsed_list(parse_school_info_simple(get_field('seminaries'))),
            college_attending=get_field('college_attending') or get_field('attending_college'),
            college_name=get_field('college_name'),
            college_major=get_field('college_major'),
            college_expected_graduation=get_field('college_expected_graduation'),
            
            # Learning information
            last_rebbe_name=get_field('last_rebbe_name') or get_field('rebbe_name'),
            last_rebbe_phone=get_field('last_rebbe_phone') or get_field('rebbe_phone'),
            gemora_sedorim_daily_count=get_field('gemora_sedorim_daily_count'),
            gemora_sedorim_length=get_field('gemora_sedorim_length'),
            learning_evaluation=get_field('learning_evaluation'),
            
            # Medical information
            medical_conditions=get_field('medical_conditions') or get_field('medical_history'),
            insurance_company=get_field('insurance_company'),
            blood_type=get_field('blood_type'),
            
            # Activities/work
            past_jobs=get_field('past_jobs') or get_field('work_history'),
            summer_activities=get_field('summer_activities'),
            
            # Financial aid
            tuition_payment_status=get_tuition_payment_status(),
            amount_can_pay=get_numeric_field('amount_can_pay') or get_numeric_field('tuition_amount'),
            scholarship_amount_requested=get_numeric_field('scholarship_amount_requested') or get_numeric_field('scholarship_amount'),
            
            # Other
            dormitory_meals_option=get_field('dormitory_meals_option') or get_field('housing_preference'),
            additional_info=get_field('additional_info') or get_field('comments') or get_field('notes')
        )
        
        db.session.add(application)
        
        # Process file uploads if present
        if 'files' in data:
            process_file_uploads(application.id, data['files'])
        
        db.session.commit()
        
        return application
        
    except Exception as e:
        db.session.rollback()
        last_webhook_error = str(e)
        current_app.logger.error(f"Error processing form submission: {str(e)}")
        raise

def process_file_uploads(application_id, file_data):
    """Process file upload data from webhook."""
    try:
        # Handle different file data formats
        files_to_process = []
        
        if isinstance(file_data, list):
            files_to_process = file_data
        elif isinstance(file_data, dict):
            # If it's a dict, it might be a single file or multiple files with keys
            if 'url' in file_data:
                # Single file
                files_to_process = [file_data]
            else:
                # Multiple files with keys like '0', '1', etc.
                files_to_process = [file_data[key] for key in sorted(file_data.keys()) if isinstance(file_data[key], dict)]
        elif isinstance(file_data, str):
            # It might be a JSON string
            try:
                parsed = json.loads(file_data)
                if isinstance(parsed, list):
                    files_to_process = parsed
                elif isinstance(parsed, dict):
                    files_to_process = [parsed]
            except:
                # If it's just a URL string
                files_to_process = [{'url': file_data}]
        
        for file_info in files_to_process:
            if not isinstance(file_info, dict):
                continue
                
            file_url = file_info.get('url', '')
            if not file_url:
                continue
            
            # Parse the URL to get the filename
            parsed_url = urlparse(file_url)
            filename = os.path.basename(unquote(parsed_url.path))
            
            # If no filename from URL, use a default
            if not filename:
                filename = f"attachment_{uuid.uuid4().hex[:8]}"
            
            # Determine file type from extension
            file_extension = os.path.splitext(filename)[1].lower()
            file_type = 'document'
            
            # Create a safe filename
            safe_filename = f"{uuid.uuid4().hex}_{filename}"
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, safe_filename)
            
            # Download the file
            try:
                response = requests.get(file_url, timeout=30)
                response.raise_for_status()
                
                # Save the file
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                # Get file type from content-type if available
                content_type = response.headers.get('content-type', '')
                if 'image' in content_type:
                    file_type = 'image'
                elif 'pdf' in content_type:
                    file_type = 'pdf'
                
                # Create the attachment record
                attachment = FileAttachment(
                    application_id=application_id,
                    filename=filename,
                    file_path=file_path,
                    file_type=file_type,
                    uploaded_date=datetime.utcnow()
                )
                db.session.add(attachment)
                
            except Exception as e:
                current_app.logger.error(f"Error downloading file {file_url}: {str(e)}")
                continue
        
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Error processing file uploads: {str(e)}")
        # Don't raise here - we don't want file upload errors to break the whole submission

@webhooks.route('/api/gravity-forms/webhook', methods=['POST'])
def gravity_forms_webhook():
    """Handle Gravity Forms webhook without division specification."""
    return handle_webhook_request()

@webhooks.route('/api/gravity-forms/webhook/yza', methods=['POST'])
def gravity_forms_webhook_yza():
    """Handle Gravity Forms webhook for YZA division."""
    return handle_webhook_request(division='YZA')

@webhooks.route('/api/gravity-forms/webhook/yoh', methods=['POST'])
def gravity_forms_webhook_yoh():
    """Handle Gravity Forms webhook for YOH division."""
    return handle_webhook_request(division='YOH')

def handle_webhook_request(division=None):
    """Common handler for all webhook requests."""
    global last_webhook_data, last_webhook_error
    
    try:
        # Get raw data for signature verification
        raw_data = request.get_data()
        
        # Verify webhook signature if secret is configured
        webhook_secret = current_app.config.get('FORMS_WEBHOOK_SECRET')
        if webhook_secret:
            signature = request.headers.get('X-Webhook-Signature', '')
            if not verify_webhook_signature(raw_data, signature, webhook_secret):
                current_app.logger.warning("Invalid webhook signature")
                return jsonify({'error': 'Invalid signature'}), 401
        
        # Parse the webhook data
        if request.content_type == 'application/x-www-form-urlencoded':
            # URL-encoded form data
            form_data = request.form.to_dict()
            
            # Check if there's a JSON payload in the form data
            if 'payload' in form_data:
                webhook_data = json.loads(form_data['payload'])
            else:
                webhook_data = form_data
        else:
            # JSON data
            webhook_data = request.get_json()
        
        # Store for debugging
        last_webhook_data = webhook_data
        last_webhook_error = None
        
        # Log the webhook data for debugging
        current_app.logger.info(f"Received webhook data: {json.dumps(webhook_data, indent=2)}")
        
        # Process the form submission
        application = process_form_submission(webhook_data, division)
        
        return jsonify({
            'success': True,
            'application_id': application.id,
            'message': 'Application created successfully'
        }), 200
        
    except Exception as e:
        last_webhook_error = str(e)
        current_app.logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'error': str(e)}), 500

@webhooks.route('/webhook-debug')
@login_required
@permission_required('view_applications')
def webhook_debug():
    """Display webhook debugging information."""
    return render_template('webhook_debug.html', 
                         last_webhook_data=last_webhook_data,
                         last_webhook_error=last_webhook_error)

@webhooks.route('/api/gravity-forms/webhook-debug', methods=['POST'])
def gravity_forms_webhook_debug():
    """Debug endpoint to see raw webhook data."""
    try:
        # Get all possible data formats
        debug_info = {
            'headers': dict(request.headers),
            'content_type': request.content_type,
            'method': request.method,
            'url': request.url,
            'args': request.args.to_dict(),
            'form': request.form.to_dict(),
            'json': request.get_json(silent=True),
            'data': request.get_data(as_text=True)
        }
        
        # Log it
        current_app.logger.info(f"Webhook debug info: {json.dumps(debug_info, indent=2)}")
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error in webhook debug: {str(e)}")
        return jsonify({'error': str(e)}), 500

@webhooks.route('/api/opensign/webhook', methods=['POST'])
def opensign_webhook():
    """Handle OpenSign webhook notifications."""
    try:
        data = request.get_json()
        
        # Log the webhook data
        current_app.logger.info(f"OpenSign webhook received: {json.dumps(data, indent=2)}")
        
        # Extract event type and document info
        event_type = data.get('event')
        document_id = data.get('documentId')
        
        if event_type == 'document.completed':
            # Find the tuition contract associated with this document
            from models import TuitionContract, Student, FinancialRecord, AcademicYear
            
            # Look for the contract with this OpenSign document ID
            contract = TuitionContract.query.filter_by(opensign_document_id=document_id).first()
            
            if contract:
                # Update contract status
                contract.opensign_status = 'completed'
                contract.opensign_signed_date = datetime.utcnow()
                contract.contract_status = 'Signed'
                
                # Set receipt method tracking
                contract.receipt_method = 'opensign'
                contract.receipt_notes = 'Signed digitally via OpenSign'
                
                # Store the signed document URL if provided
                if 'signedDocumentUrl' in data:
                    contract.opensign_signed_url = data['signedDocumentUrl']
                
                # Also update FinancialRecord for backwards compatibility
                current_year = AcademicYear.query.filter_by(is_active=True).first()
                if current_year:
                    financial_record = FinancialRecord.query.filter_by(
                        student_id=contract.student_id,
                        academic_year_id=current_year.id
                    ).first()
                    
                    if financial_record:
                        # Update both enhanced and legacy fields for UI compatibility
                        financial_record.enhanced_contract_signed = True
                        financial_record.enhanced_contract_signed_date = datetime.utcnow()
                        financial_record.enrollment_contract_received = True
                        financial_record.enrollment_contract_received_date = datetime.utcnow()
                
                # Also check for old Student model reference and update if exists
                student = Student.query.filter_by(opensign_document_id=document_id).first()
                if student:
                    student.tuition_contract_signed = True
                    student.tuition_contract_signed_date = datetime.utcnow()
                    if 'signedDocumentUrl' in data:
                        student.opensign_signed_url = data['signedDocumentUrl']
                
                db.session.commit()
                
                current_app.logger.info(f"Updated contract {contract.id} for student {contract.student_id} with signed status via OpenSign")
            else:
                # Fallback to old Student model lookup for backwards compatibility
                student = Student.query.filter_by(opensign_document_id=document_id).first()
                if student:
                    student.tuition_contract_signed = True
                    student.tuition_contract_signed_date = datetime.utcnow()
                    
                    if 'signedDocumentUrl' in data:
                        student.opensign_signed_url = data['signedDocumentUrl']
                    
                    db.session.commit()
                    
                    current_app.logger.info(f"Updated student {student.id} with signed contract (legacy method)")
                else:
                    current_app.logger.warning(f"No contract or student found for OpenSign document ID: {document_id}")
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error processing OpenSign webhook: {str(e)}")
        return jsonify({'error': str(e)}), 500 