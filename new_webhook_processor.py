#!/usr/bin/env python3
"""
New webhook processor that properly uses database field mappings
"""

from flask import current_app
from models import Application, DivisionConfig, FieldMapping, CustomField
from extensions import db
import uuid
import json
import re
from datetime import datetime
from blueprints.webhooks import process_file_uploads

def detect_division_from_data(data):
    """
    Detect division from webhook data by analyzing field patterns
    """
    # YOH-specific indicators
    yoh_indicators = 0
    yza_indicators = 0
    
    # Check for YOH-specific custom fields
    yoh_fields = [
        'father_birth_date', 'mother_birth_date', 
        'father_birth_country', 'mother_birth_country',
        'father_home_address', 'mother_home_address',
        'father_employer', 'mother_employer',
        'father_home_phone', 'mother_home_phone',
        'student_goals'
    ]
    
    for field in yoh_fields:
        if field in data and data[field]:
            yoh_indicators += 1
    
    # Check for YZA-specific field patterns (fields that YOH doesn't have)
    yza_fields = [
        '27', '28', '29', '30', '31', '32',  # In-laws
        '33', '34', '35', '36',              # Grandparents  
        '39', '40', '41', '42',              # College details
        '47', '48', '49', '50', '51',        # Insurance/medical
        '52', '53', '54',                    # Dormitory
        '55', '56', '57'                     # Gemara sedorim
    ]
    
    for field in yza_fields:
        if field in data and data[field]:
            yza_indicators += 1
    
    # Also check form_id if available
    form_id = data.get('form_id')
    if form_id:
        if str(form_id) == '4':
            yza_indicators += 5  # Strong indicator
        elif str(form_id) == '5':
            yoh_indicators += 5  # Strong indicator
    
    current_app.logger.info(f"Division detection: YZA={yza_indicators}, YOH={yoh_indicators}")
    
    if yoh_indicators > yza_indicators:
        return 'YOH'
    else:
        return 'YZA'  # Default to YZA

def get_field_value(data, field_id, default=''):
    """
    Get field value with multiple format support
    """
    # Try different field formats that Gravity Forms might use
    variations = [
        field_id,                    # Direct: "1.3"
        f"input_{field_id}",         # Prefixed: "input_1.3"
        f"field_{field_id}",         # Alternative prefix
        field_id.replace('.', '_')   # Underscore: "1_3"
    ]
    
    for variation in variations:
        if variation in data:
            value = data[variation]
            if value is not None and str(value).strip() != '':
                return str(value).strip()
    
    return default

def parse_date_value(date_str):
    """Parse date string in various formats"""
    if not date_str or str(date_str).strip() == '':
        return None
    
    try:
        # Try different date formats
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
            try:
                return datetime.strptime(str(date_str).strip(), fmt).date()
            except ValueError:
                continue
        return None
    except Exception:
        return None

def apply_field_mappings(data, division_config):
    """
    Apply database field mappings to extract data from webhook
    """
    current_app.logger.info(f"🗺️ Applying field mappings for division: {division_config.division}")
    
    # Get all field mappings for this division
    field_mappings = FieldMapping.query.filter_by(
        division_config_id=division_config.id,
        is_active=True
    ).all()
    
    current_app.logger.info(f"Found {len(field_mappings)} active field mappings")
    
    mapped_data = {}
    division_specific_data = {}
    
    for mapping in field_mappings:
        field_value = get_field_value(data, mapping.gravity_field_id)
        
        if field_value:
            current_app.logger.info(f"  {mapping.gravity_field_id} ({mapping.gravity_field_label}) = '{field_value}'")
            
            # Apply field type conversions
            if mapping.field_type == 'date':
                field_value = parse_date_value(field_value)
            elif mapping.field_type == 'number':
                try:
                    field_value = float(field_value) if field_value else None
                except ValueError:
                    field_value = None
            elif mapping.field_type == 'json':
                # Check if this JSON field should go to a specific database column
                if mapping.database_field != 'division_specific_data':
                    # Store JSON data in the specific database column (like high_school_info, seminary_info)
                    if isinstance(field_value, (dict, list)):
                        mapped_data[mapping.database_field] = json.dumps(field_value)
                    else:
                        mapped_data[mapping.database_field] = field_value
                else:
                    # Store complex data as JSON in division_specific_data
                    field_key = get_json_field_key(mapping.gravity_field_id, mapping.gravity_field_label)
                    division_specific_data[field_key] = field_value
                continue
            
            # Map to database field
            if mapping.database_table == 'applications' and mapping.database_field != 'division_specific_data':
                mapped_data[mapping.database_field] = field_value
    
    # Store division-specific data as JSON
    if division_specific_data:
        mapped_data['division_specific_data'] = json.dumps(division_specific_data)
        current_app.logger.info(f"Stored {len(division_specific_data)} fields in division_specific_data")
    
    return mapped_data

def process_custom_fields(data, division_config):
    """
    Process custom fields for the division and return as dict for JSON storage
    """
    current_app.logger.info(f"🔧 Processing custom fields for {division_config.division}")
    
    # Get custom fields for this division
    custom_fields = CustomField.query.filter(
        CustomField.divisions.like(f'%"{division_config.division}"%'),
        CustomField.is_active == True
    ).all()
    
    current_app.logger.info(f"Found {len(custom_fields)} custom fields for {division_config.division}")
    
    custom_field_data = {}
    
    for custom_field in custom_fields:
        # Look for the field in the data
        field_value = get_field_value(data, custom_field.field_name)
        
        if field_value:
            current_app.logger.info(f"  Custom field {custom_field.field_name} = '{field_value}'")
            custom_field_data[custom_field.field_name] = field_value
    
    return custom_field_data

def get_json_field_key(field_id, field_label):
    """Generate appropriate JSON key for custom fields"""
    # Map specific YOH fields to meaningful keys
    field_key_mappings = {
        '169': 'home_phone',
        '170.6': 'country_of_birth',
        '183': 'father_home_phone',
        '184': 'mother_home_phone',
        '173': 'father_date_of_birth',
        '176': 'mother_date_of_birth',
        '178.6': 'father_country_of_birth',
        '179.6': 'mother_country_of_birth',
        '181.1': 'father_address_line1',
        '181.3': 'father_address_city',
        '181.4': 'father_address_state',
        '181.5': 'father_address_zip',
        '181.6': 'father_address_country',
        '182.1': 'mother_address_line1',
        '182.3': 'mother_address_city',
        '182.4': 'mother_address_state',
        '182.5': 'mother_address_zip',
        '182.6': 'mother_address_country',
        '171': 'father_employer',
        '172': 'mother_employer',
        '108': 'post_secondary_attendance',
        '148': 'referral_source',
    }
    
    if field_id in field_key_mappings:
        return field_key_mappings[field_id]
    
    # Default: convert field label to snake_case key
    if field_label:
        key = field_label.lower()
        key = re.sub(r'[^\w\s]', '', key)  # Remove punctuation
        key = re.sub(r'\s+', '_', key)     # Replace spaces with underscores
        return key
    
    # Fallback: use field_id
    return f'field_{field_id}'

def new_process_form_submission(data, division=None):
    """
    New webhook processor that uses database field mappings
    """
    try:
        current_app.logger.info("🚀 NEW WEBHOOK PROCESSOR START")
        current_app.logger.info(f"Raw data keys: {list(data.keys())}")
        
        # Detect division if not provided
        if division is None:
            division = detect_division_from_data(data)
            current_app.logger.info(f"🎯 Auto-detected division: {division}")
        else:
            current_app.logger.info(f"✅ Division provided: {division}")
        
        # Get division configuration
        division_config = DivisionConfig.query.filter_by(
            division=division,
            is_active=True
        ).first()
        
        if not division_config:
            current_app.logger.error(f"❌ No division config found for: {division}")
            return {'status': 'error', 'message': f'No configuration found for division: {division}'}
        
        current_app.logger.info(f"📋 Using division config: {division_config.division} (form_id: {division_config.form_id})")
        
        # Apply field mappings
        mapped_data = apply_field_mappings(data, division_config)
        
        # Create base application data
        application_data = {
            'id': str(uuid.uuid4()),
            'division': division,
            'submitted_date': datetime.now(),
            'status': 'pending'
        }
        
        # Merge mapped data
        application_data.update(mapped_data)
        
        # Construct student_name from first and last name if not already set
        if 'student_name' not in application_data or not application_data['student_name']:
            first_name = application_data.get('student_first_name', '')
            middle_name = application_data.get('student_middle_name', '')
            last_name = application_data.get('student_last_name', '')
            
            # Build full name
            name_parts = [first_name, middle_name, last_name]
            full_name = ' '.join(part for part in name_parts if part and part.strip())
            
            if full_name:
                application_data['student_name'] = full_name
                current_app.logger.info(f"📝 Constructed student_name: '{full_name}'")
        
        current_app.logger.info(f"💾 Creating application with {len(mapped_data)} mapped fields")
        
        # Process custom fields
        custom_field_data = process_custom_fields(data, division_config)
        
        # Merge custom fields into division_specific_data
        if custom_field_data:
            existing_data = {}
            if 'division_specific_data' in application_data and application_data['division_specific_data']:
                existing_data = json.loads(application_data['division_specific_data'])
            
            existing_data.update(custom_field_data)
            application_data['division_specific_data'] = json.dumps(existing_data)
            current_app.logger.info(f"Added {len(custom_field_data)} custom fields to division_specific_data")
        
        # Create application
        application = Application(**application_data)
        db.session.add(application)
        
        # Commit everything
        db.session.commit()
        
        current_app.logger.info(f"✅ SUCCESS: Created application {application.id}")
        current_app.logger.info(f"   Division: {application.division}")
        current_app.logger.info(f"   Name: {getattr(application, 'student_first_name', 'N/A')} {getattr(application, 'student_last_name', 'N/A')}")
        current_app.logger.info(f"   Email: {getattr(application, 'email', 'N/A')}")
        current_app.logger.info(f"   Custom fields: {len(custom_field_data)}")
        
        # Process file attachments after the application is saved (non-blocking)
        try:
            current_app.logger.info(f"🔄 Starting file processing for application {application.id}")
            attachments = process_file_uploads(application.id, data)
            if attachments:
                current_app.logger.info(f"✅ Processed {len(attachments)} file attachments for application {application.id}")
            else:
                current_app.logger.info(f"📎 No file attachments found for application {application.id}")
        except Exception as e:
            current_app.logger.error(f"❌ Error processing file attachments: {str(e)}")
            current_app.logger.error(f"📎 File processing failed but application was saved successfully")
            # Don't fail the entire submission if file processing fails - this is now non-blocking
        
        return {
            'status': 'success',
            'message': 'Application submitted successfully',
            'application_id': application.id
        }
        
    except Exception as e:
        current_app.logger.error(f"❌ ERROR in new_process_form_submission: {e}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        
        db.session.rollback()
        return {'status': 'error', 'message': str(e)}

# Test function to compare old vs new processing
def test_new_processor():
    """Test the new processor with sample data"""
    
    # Sample YZA data
    yza_data = {
        "form_id": "4",
        "1.3": "Yaakov",
        "1.6": "Goldstein", 
        "2": "yaakov@example.com",
        "3": "555-123-4567",
        "10": "1995-03-15",
        "12": "Single",
        "27": "Father-in-law Name"  # YZA specific
    }
    
    # Sample YOH data
    yoh_data = {
        "form_id": "5", 
        "1.3": "Shmuel",
        "1.6": "Schwartz",
        "2": "shmuel@example.com",
        "father_birth_date": "1965-05-10",  # YOH specific
        "student_goals": "Torah learning"
    }
    
    print("Testing new processor with YZA data...")
    result1 = new_process_form_submission(yza_data, "YZA")
    print(f"YZA Result: {result1}")
    
    print("\nTesting new processor with YOH data...")
    result2 = new_process_form_submission(yoh_data, "YOH")
    print(f"YOH Result: {result2}")

if __name__ == "__main__":
    test_new_processor() 