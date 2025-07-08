"""
PDF Template Service
Handles template selection and PDF generation using the template management system
"""

import os
from flask import current_app
from models import db, PDFTemplate, DivisionTemplateAssignment, DivisionConfig
from pdf_service import PDFService
from storage_service import StorageService

class PDFTemplateService:
    """Service for managing PDF template selection and generation"""
    
    @staticmethod
    def get_template_for_division(division, document_type):
        """
        Get the assigned template for a division and document type
        
        Args:
            division: Division code (YZA, YOH, KOLLEL)
            document_type: Type of document (financial_aid_form, tuition_contract, etc.)
            
        Returns:
            PDFTemplate object or None
        """
        # First check for division-specific assignment
        assignment = DivisionTemplateAssignment.query.filter_by(
            division=division,
            document_type=document_type,
            is_default=True
        ).first()
        
        if assignment and assignment.template and assignment.template.is_active:
            return assignment.template
        
        # If no assignment, check legacy division config (for backward compatibility)
        config = DivisionConfig.query.filter_by(division=division).first()
        if config:
            if document_type == 'financial_aid_form' and config.financial_aid_form_path:
                # Create a virtual template object for legacy forms
                template = PDFTemplate()
                template.name = f"{division} Financial Aid Form (Legacy)"
                template.template_type = 'uploaded_pdf'
                template.file_path = config.financial_aid_form_path
                return template
            elif document_type == 'tuition_contract' and config.tuition_contract_form_path:
                # Create a virtual template object for legacy forms
                template = PDFTemplate()
                template.name = f"{division} Tuition Contract (Legacy)"
                template.template_type = 'uploaded_pdf'
                template.file_path = config.tuition_contract_form_path
                return template
        
        return None
    
    @staticmethod
    def get_available_templates_for_division(division, document_type=None):
        """
        Get all templates available for a division
        
        Args:
            division: Division code
            document_type: Optional filter by document type
            
        Returns:
            List of PDFTemplate objects
        """
        query = PDFTemplate.query.filter_by(is_active=True)
        
        # Get templates that are global or allowed for this division
        query = query.filter(db.or_(
            PDFTemplate.is_global == True,
            PDFTemplate.allowed_divisions.contains([division])
        ))
        
        if document_type:
            query = query.filter_by(category=document_type)
        
        return query.order_by(PDFTemplate.name).all()
    
    @staticmethod
    def generate_pdf_from_template(template, data, output_path=None):
        """
        Generate a PDF from a template with the provided data
        
        Args:
            template: PDFTemplate object
            data: Dictionary of variables to replace in template
            output_path: Optional path to save the PDF
            
        Returns:
            Path to generated PDF or bytes if no output_path specified
        """
        if template.template_type == 'uploaded_pdf':
            # For uploaded PDFs, fill the form fields with data
            if os.path.exists(template.file_path):
                return PDFTemplateService._fill_pdf_form(template.file_path, data, output_path)
            else:
                raise FileNotFoundError(f"Template file not found: {template.file_path}")
                
        elif template.template_type == 'html':
            # For HTML templates, render and convert to PDF
            # TODO: Implement HTML to PDF conversion
            raise NotImplementedError("HTML template generation not yet implemented")
        
        else:
            raise ValueError(f"Unknown template type: {template.template_type}")
    
    @staticmethod
    def _fill_pdf_form(template_path, data, output_path=None):
        """Fill PDF form fields with data using multiple fallback methods"""
        current_app.logger.info(f"Filling PDF form: {template_path}")
        current_app.logger.info(f"Form data keys: {list(data.keys())}")
        
        try:
            import pdfrw
            from pdfrw import PdfReader, PdfWriter
            import io
            
            current_app.logger.info("Using pdfrw for form filling")
            
            # Read the template PDF
            template = PdfReader(template_path)
            
            # Inspect the PDF first
            inspection_results = PDFTemplateService.inspect_pdf_form_fields(template_path)
            current_app.logger.info(f"PDF inspection results: {inspection_results['field_count']} fields found")
            
            # If no form fields found, return the original PDF as-is for static templates
            if inspection_results['field_count'] == 0:
                current_app.logger.info("No form fields found - treating as static template, returning original PDF")
                
                # Read original PDF and return it
                with open(template_path, 'rb') as f:
                    original_pdf_bytes = f.read()
                
                if output_path:
                    # Copy original to output path
                    with open(output_path, 'wb') as f:
                        f.write(original_pdf_bytes)
                    current_app.logger.info(f"Static PDF copied to: {output_path}")
                    return output_path
                else:
                    current_app.logger.info(f"Returning static PDF, size: {len(original_pdf_bytes)} bytes")
                    return original_pdf_bytes
            
            # If we have form fields, try to fill them
            current_app.logger.info(f"PDF has {len(template.pages)} pages")
            
            # Try to fill form fields
            fields_filled = 0
            
            def fill_form_fields(obj, data):
                """Recursively fill form fields"""
                nonlocal fields_filled
                
                if obj is None:
                    return
                
                # Handle different types of PDF objects
                if hasattr(obj, '__iter__') and not isinstance(obj, str):
                    for item in obj:
                        fill_form_fields(item, data)
                elif hasattr(obj, 'items'):
                    for key, value in obj.items():
                        fill_form_fields(value, data)
                elif hasattr(obj, '__dict__'):
                    # Check if this is a form field
                    if hasattr(obj, 'T') and obj.T:  # T is the field name
                        field_name = str(obj.T).strip('()')
                        if field_name in data:
                            try:
                                field_value = str(data[field_name]) if data[field_name] is not None else ""
                                obj.V = f'({field_value})'
                                obj.AP = ''  # Clear appearance stream to force regeneration
                                current_app.logger.info(f"Filled field: {field_name} = {field_value}")
                                fields_filled += 1
                            except Exception as e:
                                current_app.logger.warning(f"Error filling field {field_name}: {str(e)}")
                    
                    # Continue searching in sub-objects
                    for attr_name in dir(obj):
                        if not attr_name.startswith('_'):
                            try:
                                attr_value = getattr(obj, attr_name)
                                fill_form_fields(attr_value, data)
                            except:
                                pass
            
            # Fill the form fields
            fill_form_fields(template.Root, data)
            current_app.logger.info(f"Filled {fields_filled} form fields")
            
            # If no fields were filled, try alternative detection method
            if fields_filled == 0:
                current_app.logger.warning("No form fields filled - trying alternative detection method")
                
                def find_all_form_fields(obj, depth=0):
                    """More aggressive form field detection"""
                    nonlocal fields_filled
                    
                    if depth > 10:  # Prevent infinite recursion
                        return
                    
                    if obj is None:
                        return
                    
                    # Check if this object has form field properties
                    if hasattr(obj, 'FT') or hasattr(obj, 'T'):
                        field_name = None
                        if hasattr(obj, 'T') and obj.T:
                            field_name = str(obj.T).strip('()')
                        elif hasattr(obj, 'FT'):
                            field_name = f"field_{depth}"
                        
                        if field_name and field_name in data:
                            try:
                                field_value = str(data[field_name]) if data[field_name] is not None else ""
                                obj.V = f'({field_value})'
                                if hasattr(obj, 'AP'):
                                    obj.AP = ''
                                current_app.logger.info(f"Alternative method filled field: {field_name} = {field_value}")
                                fields_filled += 1
                            except Exception as e:
                                current_app.logger.warning(f"Error filling field {field_name}: {str(e)}")
                    
                    # Recursively search all attributes
                    for attr_name in dir(obj):
                        if not attr_name.startswith('_'):
                            try:
                                attr_value = getattr(obj, attr_name)
                                if hasattr(attr_value, '__iter__') and not isinstance(attr_value, str):
                                    for item in attr_value:
                                        find_all_form_fields(item, depth + 1)
                                else:
                                    find_all_form_fields(attr_value, depth + 1)
                            except:
                                pass
                
                # Try alternative detection
                find_all_form_fields(template.Root, 0)
                current_app.logger.info(f"Alternative method filled {fields_filled} total fields")
            
            # Write the filled PDF
            if output_path:
                writer = PdfWriter(output_path, template)
                current_app.logger.info(f"PDF saved to: {output_path}")
                return output_path
            else:
                # Write to memory buffer
                output_buffer = io.BytesIO()
                writer = PdfWriter(output_buffer, template)
                output_buffer.seek(0)
                pdf_bytes = output_buffer.getvalue()
                current_app.logger.info(f"Generated PDF size: {len(pdf_bytes)} bytes")
                
                # If still no fields were filled and we have a very small PDF, return original
                if fields_filled == 0 and len(pdf_bytes) < 1000:
                    current_app.logger.warning("No fields filled and small output - returning original PDF")
                    with open(template_path, 'rb') as f:
                        original_pdf_bytes = f.read()
                    current_app.logger.info(f"Returning original PDF, size: {len(original_pdf_bytes)} bytes")
                    return original_pdf_bytes
                
                return pdf_bytes
                
        except ImportError as e:
            current_app.logger.warning(f"pdfrw not available, trying PyPDF2: {str(e)}")
            
            # Fallback to PyPDF2
            try:
                import PyPDF2
                import io
                
                current_app.logger.info("Using PyPDF2 fallback")
                
                # Read the template PDF
                with open(template_path, 'rb') as template_file:
                    pdf_reader = PyPDF2.PdfReader(template_file)
                    pdf_writer = PyPDF2.PdfWriter()
                    
                    current_app.logger.info(f"PDF has {len(pdf_reader.pages)} pages")
                    
                    # Check if this is a form PDF
                    has_form = False
                    if hasattr(pdf_reader, 'get_form_text_fields'):
                        form_fields = pdf_reader.get_form_text_fields()
                        if form_fields:
                            has_form = True
                            current_app.logger.info(f"Found form fields: {list(form_fields.keys())}")
                    
                    # If no form fields, just return the original PDF
                    if not has_form:
                        current_app.logger.info("No form fields found - returning original PDF")
                        with open(template_path, 'rb') as f:
                            original_pdf_bytes = f.read()
                        
                        if output_path:
                            with open(output_path, 'wb') as f:
                                f.write(original_pdf_bytes)
                            return output_path
                        else:
                            return original_pdf_bytes
                    
                    # Process each page
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        pdf_writer.add_page(page)
                    
                    # Fill form fields using the writer
                    current_app.logger.info("Attempting to fill form fields")
                    try:
                        # PyPDF2 3.x way to fill forms
                        if hasattr(pdf_writer, 'update_page_form_field_values'):
                            # This method might exist in some versions
                            for page_num in range(len(pdf_writer.pages)):
                                pdf_writer.update_page_form_field_values(pdf_writer.pages[page_num], data)
                        elif hasattr(pdf_writer, 'updatePageFormFieldValues'):
                            # Legacy method name
                            for page_num in range(len(pdf_writer.pages)):
                                pdf_writer.updatePageFormFieldValues(pdf_writer.pages[page_num], data)
                        else:
                            # Try direct field manipulation
                            current_app.logger.info("Using direct field manipulation")
                            for field_name, field_value in data.items():
                                try:
                                    # Convert value to string
                                    str_value = str(field_value) if field_value is not None else ""
                                    
                                    # Try to find and update the field
                                    for page_num in range(len(pdf_writer.pages)):
                                        page = pdf_writer.pages[page_num]
                                        if '/Annots' in page:
                                            for annot_ref in page['/Annots']:
                                                annot = annot_ref.get_object()
                                                if '/T' in annot and annot['/T'] == field_name:
                                                    annot.update({'/V': str_value})
                                                    current_app.logger.info(f"Updated field {field_name} = {str_value}")
                                except Exception as field_error:
                                    current_app.logger.warning(f"Could not update field {field_name}: {str(field_error)}")
                    except Exception as form_error:
                        current_app.logger.error(f"Form filling error: {str(form_error)}")
                    
                    # Create output
                    output_buffer = io.BytesIO()
                    pdf_writer.write(output_buffer)
                    output_buffer.seek(0)
                    
                    current_app.logger.info(f"Generated PDF size: {len(output_buffer.getvalue())} bytes")
                    
                    if output_path:
                        # Save to file
                        with open(output_path, 'wb') as output_file:
                            output_file.write(output_buffer.getvalue())
                        current_app.logger.info(f"PDF saved to: {output_path}")
                        return output_path
                    else:
                        # Return bytes
                        return output_buffer.getvalue()
                        
            except ImportError as e2:
                current_app.logger.error(f"Neither pdfrw nor PyPDF2 available: {str(e2)}")
                # Final fallback - just return the original PDF
                current_app.logger.info("Final fallback - returning original PDF")
                with open(template_path, 'rb') as f:
                    original_pdf_bytes = f.read()
                
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(original_pdf_bytes)
                    return output_path
                else:
                    return original_pdf_bytes
        
        except Exception as e:
            current_app.logger.error(f"Error filling PDF form: {str(e)}", exc_info=True)
            # Last resort - return original PDF
            current_app.logger.info("Exception occurred - returning original PDF as last resort")
            try:
                with open(template_path, 'rb') as f:
                    original_pdf_bytes = f.read()
                
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(original_pdf_bytes)
                    return output_path
                else:
                    return original_pdf_bytes
            except Exception as final_error:
                raise Exception(f"Could not process PDF template: {str(final_error)}")
    
    @staticmethod
    def replace_template_variables(template_content, data):
        """
        Replace variables in template content with actual data
        
        Args:
            template_content: Template string with {{variables}}
            data: Dictionary of variable values
            
        Returns:
            String with variables replaced
        """
        import re
        
        # Simple variable replacement for now
        # In the future, could use Jinja2 or more sophisticated templating
        for key, value in data.items():
            pattern = r'\{\{' + key + r'\}\}'
            template_content = re.sub(pattern, str(value), template_content)
        
        return template_content
    
    @staticmethod
    def validate_template_data(template, data):
        """
        Validate that all required variables are provided
        
        Args:
            template: PDFTemplate object
            data: Dictionary of variable values
            
        Returns:
            tuple (is_valid, missing_variables)
        """
        missing_vars = []
        
        for var in template.variables:
            if var.is_required and var.variable_name not in data:
                if not var.default_value:
                    missing_vars.append(var.variable_name)
        
        return len(missing_vars) == 0, missing_vars
    
    @staticmethod
    def prepare_template_data(student, additional_data=None):
        """
        Prepare common template data from student and other sources
        
        Args:
            student: Student object
            additional_data: Additional data to merge
            
        Returns:
            Dictionary of template variables
        """
        from datetime import datetime
        from models import AcademicYear, DivisionConfig
        
        # Get current academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        academic_year = f"{active_year.start_date.year}-{active_year.end_date.year}" if active_year else "2024-2025"
        
        # Get division config for school information
        division_config = DivisionConfig.query.filter_by(division=student.division).first()
        
        # Determine school information based on division
        if student.division == 'YOH':
            school_name = "Yeshiva Ohr Hatzafon"
            school_address = "PO Box 486 Cedarhurst, NY 11516"
            school_phone = "(347) 619-9074"
        else:  # YZA or default
            school_name = "Yeshiva Zichron Aryeh"
            school_address = "PO Box 486 Cedarhurst, NY 11516"
            school_phone = "(347) 619-9074"
        
        data = {
            # Student information
            'student_name': student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip(),
            'student_first_name': student.student_first_name or '',
            'student_last_name': student.student_last_name or '',
            'hebrew_name': getattr(student, 'hebrew_name', '') or '',
            'student_email': getattr(student, 'email', '') or '',
            'student_phone': getattr(student, 'phone_number', '') or '',
            'student_id': student.id,
            
            # Academic information
            'division': student.division,
            'academic_year': academic_year,
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'acceptance_date': student.accepted_date.strftime('%B %d, %Y') if hasattr(student, 'accepted_date') and student.accepted_date else '',
            
            # School information
            'school_name': school_name,
            'school_address': school_address,
            'school_phone': school_phone,
            
            # Financial information (defaults - will be overridden by additional_data)
            'total_tuition': '$0.00',
            'tuition_amount': '$0.00',
            'registration_fee': '$0.00',
            'registration_fee_option': 'upfront',
            'room_amount': '$0.00',
            'board_amount': '$0.00',
            'room_board': '$0.00',
            'financial_aid_amount': '$0.00',
            'payment_plan': 'Monthly',
            'monthly_payment': '$0.00',
            'number_of_payments': '10',
            
            # Payment schedule information
            'payment_start_month': 'September',
            'payment_start_year': str(active_year.start_date.year if active_year else 2024),
            'payment_end_month': 'June',
            'payment_end_year': str(active_year.end_date.year if active_year else 2025),
            
            # Payment schedule details (will be populated if contract_terms provided)
            'payment_1_date': '',
            'payment_1_amount': '',
            'payment_2_date': '',
            'payment_2_amount': '',
            'payment_3_date': '',
            'payment_3_amount': '',
            'payment_4_date': '',
            'payment_4_amount': '',
            'payment_5_date': '',
            'payment_5_amount': '',
            'payment_6_date': '',
            'payment_6_amount': '',
            'payment_7_date': '',
            'payment_7_amount': '',
            'payment_8_date': '',
            'payment_8_amount': '',
            'payment_9_date': '',
            'payment_9_amount': '',
            'payment_10_date': '',
            'payment_10_amount': '',
        }
        
        # Merge additional data first
        if additional_data:
            data.update(additional_data)
            
            # Format financial amounts properly
            if 'total_tuition' in additional_data:
                data['total_tuition'] = f"${additional_data['total_tuition']:,.2f}"
                data['tuition_amount'] = data['total_tuition']  # Alias
            
            if 'registration_fee' in additional_data:
                data['registration_fee'] = f"${additional_data['registration_fee']:,.2f}"
            
            if 'monthly_payment' in additional_data:
                data['monthly_payment'] = f"${additional_data['monthly_payment']:,.2f}"
            
            # Populate payment schedule if available
            if 'payment_schedule' in additional_data:
                for i, payment in enumerate(additional_data['payment_schedule'][:10], 1):
                    data[f'payment_{i}_date'] = payment.get('due_date', '')
                    data[f'payment_{i}_amount'] = f"${payment.get('amount', 0):,.2f}"
        
        return data
    
    @staticmethod
    def assign_template_to_division(division, document_type, template_id, user=None):
        """
        Assign a template to a division for a specific document type
        
        Args:
            division: Division code
            document_type: Document type
            template_id: Template ID to assign
            user: User making the assignment
            
        Returns:
            DivisionTemplateAssignment object
        """
        # Validate template exists and is allowed for division
        template = PDFTemplate.query.get(template_id)
        if not template:
            raise ValueError("Template not found")
        
        if not template.is_global and division not in (template.allowed_divisions or []):
            raise ValueError("Template not allowed for this division")
        
        # Unset any existing default
        DivisionTemplateAssignment.query.filter_by(
            division=division,
            document_type=document_type,
            is_default=True
        ).update({'is_default': False})
        
        # Create or update assignment
        assignment = DivisionTemplateAssignment.query.filter_by(
            division=division,
            document_type=document_type,
            template_id=template_id
        ).first()
        
        if not assignment:
            assignment = DivisionTemplateAssignment(
                division=division,
                document_type=document_type,
                template_id=template_id,
                is_default=True,
                assigned_by=user.username if user else 'system'
            )
            db.session.add(assignment)
        else:
            assignment.is_default = True
            assignment.assigned_by = user.username if user else 'system'
            assignment.assigned_at = datetime.utcnow()
        
        db.session.commit()
        return assignment
    
    @staticmethod
    def inspect_pdf_form_fields(template_path):
        """
        Inspect a PDF to see what form fields are available
        
        Args:
            template_path: Path to the PDF template file
            
        Returns:
            Dictionary with form field information
        """
        try:
            from pdfrw import PdfReader
            
            template = PdfReader(template_path)
            form_info = {
                'has_acroform': False,
                'field_count': 0,
                'fields': [],
                'pages': len(template.pages) if template.pages else 0
            }
            
            current_app.logger.info(f"Inspecting PDF: {template_path}")
            current_app.logger.info(f"PDF has {form_info['pages']} pages")
            
            # Check for AcroForm
            if hasattr(template.Root, 'AcroForm') and template.Root.AcroForm is not None:
                form_info['has_acroform'] = True
                current_app.logger.info("PDF has AcroForm")
                
                # Recursively find all form fields
                def find_fields(obj, path=""):
                    if obj is None:
                        return
                    
                    # Check if this is a form field
                    if hasattr(obj, 'T') and obj.T is not None:
                        field_name = str(obj.T).strip('()')
                        field_type = "Unknown"
                        field_value = ""
                        
                        if hasattr(obj, 'FT'):
                            field_type = str(obj.FT).strip('()')
                        if hasattr(obj, 'V'):
                            field_value = str(obj.V).strip('()')
                        
                        field_info = {
                            'name': field_name,
                            'type': field_type,
                            'value': field_value,
                            'path': path
                        }
                        form_info['fields'].append(field_info)
                        form_info['field_count'] += 1
                        current_app.logger.info(f"Found field: {field_name} (type: {field_type})")
                    
                    # Recursively process children
                    if hasattr(obj, 'Kids') and obj.Kids is not None:
                        for i, kid in enumerate(obj.Kids):
                            find_fields(kid, f"{path}/Kids[{i}]")
                
                find_fields(template.Root.AcroForm, "AcroForm")
            else:
                current_app.logger.info("PDF does not have AcroForm")
            
            # Also check page annotations
            for page_num, page in enumerate(template.pages):
                if hasattr(page, 'Annots') and page.Annots is not None:
                    for annot_num, annot in enumerate(page.Annots):
                        if hasattr(annot, 'T') and annot.T is not None:
                            field_name = str(annot.T).strip('()')
                            field_info = {
                                'name': field_name,
                                'type': 'Annotation',
                                'value': '',
                                'path': f"Page[{page_num}]/Annots[{annot_num}]"
                            }
                            form_info['fields'].append(field_info)
                            form_info['field_count'] += 1
                            current_app.logger.info(f"Found annotation field: {field_name}")
            
            current_app.logger.info(f"Total fields found: {form_info['field_count']}")
            return form_info
            
        except Exception as e:
            current_app.logger.error(f"Error inspecting PDF form fields: {str(e)}")
            return {
                'error': str(e),
                'has_acroform': False,
                'field_count': 0,
                'fields': [],
                'pages': 0
            } 