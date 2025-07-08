"""
Fillable PDF Filler Service - Fills fillable PDF forms with actual data
Uses PyPDF2/pypdf to fill AcroForm fields in existing fillable PDFs
"""

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, IndirectObject
import os
from datetime import datetime, date
from decimal import Decimal

class FillablePDFFiller:
    """Service for filling fillable PDF forms with data"""
    
    def __init__(self):
        pass
    
    def fill_contract_form(self, template_path, student_data, contract_data, output_path):
        """
        Fill a fillable PDF contract template with student and contract data
        
        Args:
            template_path (str): Path to the fillable PDF template
            student_data (dict): Student information data
            contract_data (dict): Contract and financial data
            output_path (str): Path where to save the filled PDF
            
        Returns:
            str: Path to the filled PDF file
        """
        try:
            # Read the fillable PDF template
            reader = PdfReader(template_path)
            writer = PdfWriter()
            
            # Prepare the field data
            field_data = self._prepare_field_data(student_data, contract_data)
            
            # Fill the form fields
            if "/AcroForm" in reader.trailer["/Root"]:
                writer.clone_reader_document_root(reader)
                
                # Update form fields
                if "/AcroForm" in writer._root_object:
                    self._fill_form_fields(writer, field_data)
                    
            else:
                print("⚠️  PDF template does not contain form fields")
                # Copy pages without form filling
                for page in reader.pages:
                    writer.add_page(page)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save the filled PDF
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            print(f"✅ Filled contract saved: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"❌ Error filling PDF form: {str(e)}")
            raise
    
    def _prepare_field_data(self, student_data, contract_data):
        """
        Prepare field data from student and contract information
        
        Args:
            student_data (dict): Student information
            contract_data (dict): Contract and financial information
            
        Returns:
            dict: Field name to value mapping
        """
        # Get current date
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Prepare the field mapping
        field_data = {
            # Student Information
            'student_name': student_data.get('student_name', ''),
            'academic_year': contract_data.get('academic_year', ''),
            'division': student_data.get('division', ''),
            'current_date': current_date,
            
            # Financial Information
            'total_tuition': self._format_currency(contract_data.get('total_tuition', 0)),
            'registration_fee': self._format_currency(contract_data.get('registration_fee', 0)),
            'room_amount': self._format_currency(contract_data.get('room_amount', 0)),
            'board_amount': self._format_currency(contract_data.get('board_amount', 0)),
            'financial_aid_amount': self._format_currency(contract_data.get('financial_aid_amount', 0)),
            'final_amount': self._format_currency(contract_data.get('final_amount', 0)),
            
            # Registration Fee Options
            'registration_fee_upfront': contract_data.get('registration_fee_option') == 'upfront',
            'registration_fee_rolled': contract_data.get('registration_fee_option') == 'rolled_in',
            
            # Payment Method
            'payment_method_cc': contract_data.get('payment_method') == 'credit_card',
            'payment_method_ach': contract_data.get('payment_method') == 'ach',
            'payment_method_third': contract_data.get('payment_method') == 'third_party',
            
            # Credit Card Information
            'cc_holder_name': contract_data.get('cc_holder_name', ''),
            'cc_exp_date': contract_data.get('cc_exp_date', ''),
            'cc_zip': contract_data.get('cc_zip', ''),
            'cc_charge_date': str(contract_data.get('cc_charge_date', '')) if contract_data.get('cc_charge_date') else '',
            
            # ACH Information
            'ach_account_holder_name': contract_data.get('ach_account_holder_name', ''),
            'ach_routing_number': contract_data.get('ach_routing_number', ''),
            'ach_debit_date': str(contract_data.get('ach_debit_date', '')) if contract_data.get('ach_debit_date') else '',
            
            # Third Party Information
            'third_party_payer_name': contract_data.get('third_party_payer_name', ''),
            'third_party_payer_relationship': contract_data.get('third_party_payer_relationship', ''),
            'third_party_payer_contact': contract_data.get('third_party_payer_contact', ''),
            
            # Payment Schedule Information
            'payment_plan': contract_data.get('payment_plan', ''),
            'first_payment_date': self._format_date(contract_data.get('first_payment_date')),
            'final_payment_date': self._format_date(contract_data.get('final_payment_date')),
            'number_of_payments': str(contract_data.get('number_of_payments', '')) if contract_data.get('number_of_payments') else '',
            'monthly_payment_amount': self._format_currency(contract_data.get('monthly_payment_amount', 0)),
            
            # Signature Information
            'parent_signature': '',  # Will be filled manually or digitally
            'signature_date': '',
            'parent_name': student_data.get('parent_name', ''),
            'school_rep_signature': '',
            'school_date': '',
        }
        
        return field_data
    
    def _fill_form_fields(self, writer, field_data):
        """
        Fill the form fields in the PDF writer
        
        Args:
            writer (PdfWriter): PDF writer object
            field_data (dict): Field data to fill
        """
        try:
            # Get the form fields
            if "/AcroForm" in writer._root_object:
                acro_form = writer._root_object["/AcroForm"]
                
                if "/Fields" in acro_form:
                    fields = acro_form["/Fields"]
                    
                    # Iterate through fields and fill them
                    for field_ref in fields:
                        if isinstance(field_ref, IndirectObject):
                            field = field_ref.get_object()
                            
                            # Get field name
                            if "/T" in field:
                                field_name = field["/T"]
                                
                                # Fill field if we have data for it
                                if field_name in field_data:
                                    field_value = field_data[field_name]
                                    
                                    # Handle different field types
                                    if "/FT" in field:
                                        field_type = field["/FT"]
                                        
                                        if field_type == "/Tx":  # Text field
                                            field.update({NameObject("/V"): field_value})
                                            
                                        elif field_type == "/Btn":  # Button/Checkbox field
                                            if isinstance(field_value, bool):
                                                if field_value:
                                                    field.update({NameObject("/V"): NameObject("/Yes")})
                                                    field.update({NameObject("/AS"): NameObject("/Yes")})
                                                else:
                                                    field.update({NameObject("/V"): NameObject("/Off")})
                                                    field.update({NameObject("/AS"): NameObject("/Off")})
                                    
                                    # Update appearance
                                    if "/AP" in field:
                                        field.update({NameObject("/AS"): NameObject("/Yes" if field_value else "/Off")})
                                        
        except Exception as e:
            print(f"⚠️  Error filling form fields: {str(e)}")
    
    def _format_currency(self, amount):
        """Format a numeric amount as currency"""
        if amount is None:
            return "$0.00"
        
        if isinstance(amount, (int, float, Decimal)):
            return f"${amount:,.2f}"
        
        try:
            return f"${float(amount):,.2f}"
        except (ValueError, TypeError):
            return str(amount)
    
    def _format_date(self, date_value):
        """Format a date value for display"""
        if date_value is None:
            return ""
        
        if isinstance(date_value, str):
            try:
                # Try to parse string date
                parsed_date = datetime.strptime(date_value, "%Y-%m-%d")
                return parsed_date.strftime("%B %d, %Y")
            except ValueError:
                return date_value
        
        if isinstance(date_value, (date, datetime)):
            return date_value.strftime("%B %d, %Y")
        
        return str(date_value)
    
    def create_filled_contract(self, student, contract_data, template_division=None):
        """
        Create a filled contract from student and contract data
        
        Args:
            student: Student model instance
            contract_data (dict): Contract data dictionary
            template_division (str): Division for template selection
            
        Returns:
            str: Path to the filled contract PDF
        """
        # Determine division
        division = template_division or student.division or 'YZA'
        
        # Find the fillable template
        template_path = f"static/templates/pdf/fillable_contract_{division.lower()}_template.pdf"
        
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Fillable template not found: {template_path}")
        
        # Prepare student data
        student_data = {
            'student_name': student.student_name or '',
            'division': student.division or '',
            'parent_name': f"{student.father_first_name or ''} {student.father_last_name or ''}".strip() or 
                          f"{student.mother_first_name or ''} {student.mother_last_name or ''}".strip()
        }
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in student.student_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        
        output_path = f"contracts/filled_contract_{safe_name}_{timestamp}.pdf"
        
        # Fill the contract
        return self.fill_contract_form(template_path, student_data, contract_data, output_path)


# Integration function for use with existing contract generation
def generate_fillable_contract(student, tuition_contract, academic_year):
    """
    Generate a filled contract PDF from student and tuition contract data
    
    Args:
        student: Student model instance
        tuition_contract: TuitionContract model instance
        academic_year: AcademicYear model instance
        
    Returns:
        str: Path to the generated contract PDF
    """
    filler = FillablePDFFiller()
    
    # Prepare contract data
    contract_data = {
        'academic_year': academic_year.year_label if academic_year else '',
        'total_tuition': tuition_contract.tuition_amount,
        'registration_fee': tuition_contract.registration_fee or 0,
        'registration_fee_option': tuition_contract.registration_fee_option or 'upfront',
        'room_amount': 0,  # Would need to be calculated from components
        'board_amount': 0,  # Would need to be calculated from components
        'financial_aid_amount': tuition_contract.financial_aid_amount or 0,
        'final_amount': tuition_contract.final_tuition_amount,
        'payment_plan': tuition_contract.payment_plan,
        'payment_method': tuition_contract.payment_method,
        'payment_timing': tuition_contract.payment_timing,
        
        # Credit card info
        'cc_holder_name': tuition_contract.cc_holder_name,
        'cc_exp_date': tuition_contract.cc_exp_date,
        'cc_zip': tuition_contract.cc_zip,
        'cc_charge_date': tuition_contract.cc_charge_date,
        
        # ACH info
        'ach_account_holder_name': tuition_contract.ach_account_holder_name,
        'ach_routing_number': tuition_contract.ach_routing_number,
        'ach_debit_date': tuition_contract.ach_debit_date,
        
        # Third party info
        'third_party_payer_name': tuition_contract.third_party_payer_name,
        'third_party_payer_relationship': tuition_contract.third_party_payer_relationship,
        'third_party_payer_contact': tuition_contract.third_party_payer_contact,
        
        # Payment schedule
        'first_payment_date': tuition_contract.first_payment_due,
        'final_payment_date': tuition_contract.final_payment_due,
        'number_of_payments': len(tuition_contract.payment_schedule) if tuition_contract.payment_schedule else 0,
        'monthly_payment_amount': tuition_contract.final_tuition_amount / 10 if tuition_contract.payment_plan == 'Monthly' else tuition_contract.final_tuition_amount,
    }
    
    # Generate the filled contract
    return filler.create_filled_contract(student, contract_data, student.division)


# Testing function
def test_fillable_pdf():
    """Test the fillable PDF functionality"""
    
    # Sample student data
    student_data = {
        'student_name': 'John Doe',
        'division': 'YZA',
        'parent_name': 'Parent Name'
    }
    
    # Sample contract data
    contract_data = {
        'academic_year': '2024-2025',
        'total_tuition': 9010.00,
        'registration_fee': 550.00,
        'registration_fee_option': 'upfront',
        'room_amount': 2100.00,
        'board_amount': 2100.00,
        'financial_aid_amount': 2000.00,
        'final_amount': 7010.00,
        'payment_plan': 'Monthly',
        'payment_method': 'credit_card',
        'cc_holder_name': 'John Doe',
        'cc_exp_date': '12/2026',
        'cc_zip': '12345',
        'cc_charge_date': 15,
        'first_payment_date': '2024-09-01',
        'final_payment_date': '2025-06-01',
        'number_of_payments': 10,
        'monthly_payment_amount': 701.00,
    }
    
    filler = FillablePDFFiller()
    
    template_path = "static/templates/pdf/fillable_contract_yza_template.pdf"
    output_path = "contracts/test_filled_contract.pdf"
    
    try:
        result = filler.fill_contract_form(template_path, student_data, contract_data, output_path)
        print(f"✅ Test contract created: {result}")
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")

if __name__ == "__main__":
    test_fillable_pdf() 