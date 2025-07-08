"""
Enhanced Contract Structure Service - 2-Page Contract with Improved Layout and Fillable Fields
Addresses new formatting requirements:
1. 2-page contract with tuition breakdown and payment schedule on page 2
2. Payment terms with checkbox options and tuition total note
3. Updated payment method text and third party payer layout
4. Simple signature section with just signature line and date
5. ADDED: Fillable AcroForm fields for dynamic data entry
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas
from datetime import datetime
import os

# AcroForm field classes for fillable PDFs
class FormTextField(Flowable):
    """Fillable text field for PDFs"""
    def __init__(self, name, value="", width=150, height=20, **kwargs):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.name = name
        self.value = str(value) if value else ""
        self.kwargs = kwargs

    def draw(self):
        # Draw a very faint blue background for subtle visual indication
        self.canv.setFillColor(colors.Color(0.95, 0.97, 1.0, alpha=0.3))  # Very light blue with transparency
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        # Draw a subtle bottom line for visual guidance when printed
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(0.5)
        self.canv.line(0, 0, self.width, 0)  # Bottom line only
        
        # Create the form field with minimal styling
        form = self.canv.acroForm
        form.textfieldRelative(
            name=self.name,
            value=self.value,
            width=self.width,
            height=self.height,
            forceBorder=False,  # Remove visible border
            borderStyle='solid',
            borderWidth=0,  # No border width
            borderColor=None,  # No border color
            fillColor=colors.Color(0.95, 0.97, 1.0, alpha=0.2),  # Very faint blue
            fontSize=10,
            **self.kwargs
        )

class FormCheckbox(Flowable):
    """Fillable checkbox for PDFs"""
    def __init__(self, name, checked=False, size=12, **kwargs):
        Flowable.__init__(self)
        self.width = size
        self.height = size
        self.name = name
        self.checked = checked
        self.kwargs = kwargs

    def draw(self):
        # Draw a very faint blue background for subtle visual indication
        self.canv.setFillColor(colors.Color(0.95, 0.97, 1.0, alpha=0.3))
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        # Draw a subtle square border for visual guidance when printed
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(0.5)
        self.canv.rect(0, 0, self.width, self.height, fill=0)  # Empty square border
        
        # Create the form field with minimal styling
        form = self.canv.acroForm
        form.checkboxRelative(
            name=self.name,
            checked=self.checked,
            size=self.width,
            forceBorder=False,  # Remove visible border
            borderWidth=0,  # No border width
            borderColor=None,  # No border color
            fillColor=colors.Color(0.95, 0.97, 1.0, alpha=0.2),  # Very faint blue
            **self.kwargs
        )

class CheckboxWithText(Flowable):
    """Flowable that combines a checkbox with text, positioned at left margin"""
    def __init__(self, checkbox_name, text, checked=False, size=12, text_style=None):
        Flowable.__init__(self)
        self.checkbox_name = checkbox_name
        self.text = text
        self.checked = checked
        self.size = size
        self.text_style = text_style
        self.width = 6*inch  # Full width
        self.height = 16  # Height for the line
        
    def draw(self):
        # Draw a very faint blue background for the checkbox only
        self.canv.setFillColor(colors.Color(0.95, 0.97, 1.0, alpha=0.3))
        self.canv.rect(0, 2, self.size, self.size, fill=1, stroke=0)
        
        # Draw a subtle checkbox square for visual guidance when printed
        self.canv.setStrokeColor(colors.black)
        self.canv.setLineWidth(0.5)
        self.canv.rect(0, 2, self.size, self.size, fill=0)  # Empty square border
        
        # Draw the text next to the checkbox in bold (BEFORE creating form field)
        self.canv.setFillColor(colors.black)  # Ensure text is black
        self.canv.setStrokeColor(colors.black)  # Ensure stroke is black
        self.canv.setFont('Helvetica-Bold', 10)
        self.canv.drawString(self.size + 6, 4, self.text)  # Slightly adjusted position
        
        # Draw the checkbox form field at the very left (no offset)
        form = self.canv.acroForm
        form.checkboxRelative(
            name=self.checkbox_name,
            checked=self.checked,
            size=self.size,
            forceBorder=False,  # Remove visible border
            borderWidth=0,  # No border width
            borderColor=None,  # No border color
            fillColor=colors.Color(0.95, 0.97, 1.0, alpha=0.2)  # Very faint blue
        )

class ContractStructureService:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='ContractTitle',
            parent=self.styles['Title'],
            fontSize=16,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=12,
            fontName='Helvetica-Bold',
            spaceAfter=6,
            spaceBefore=12
        ))
        
        # Compact text style for tight spacing
        self.styles.add(ParagraphStyle(
            name='CompactText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=3,
            spaceBefore=0
        ))
        
        # Form field style
        self.styles.add(ParagraphStyle(
            name='FormField',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=2,
            spaceBefore=2
        ))
        
        # Small text style for agreement
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            spaceAfter=2,
            spaceBefore=0
        ))

    def format_currency(self, amount):
        """Format currency with comma separators, no dollar sign in individual fields"""
        if isinstance(amount, (int, float)):
            return f"{amount:,.2f}".rstrip('0').rstrip('.')
        return str(amount)

    def format_currency_with_dollar(self, amount):
        """Format currency with dollar sign for totals"""
        if isinstance(amount, (int, float)):
            formatted = f"{amount:,.2f}".rstrip('0').rstrip('.')
            return f"${formatted}"
        return f"${amount}"

    def create_yza_contract(self, data, output_path=None, fillable=True):
        """Create YZA enrollment contract with improved formatting and optional fillable fields"""
        try:
            # Generate filename
            student_name = data.get('student_name', 'Unknown_Student')
            clean_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if output_path:
                # Use provided output path
                filepath = output_path
                # Ensure directory exists if not in current directory
                dirname = os.path.dirname(filepath)
                if dirname and dirname != '':
                    os.makedirs(dirname, exist_ok=True)
            else:
                # Generate default path
                filename = f"tuition_contract_{clean_name}_{timestamp}.pdf"
                contracts_dir = "contracts"
                os.makedirs(contracts_dir, exist_ok=True)
                filepath = os.path.join(contracts_dir, filename)
            
            # Create PDF document
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )
            
            # Build content
            story = []
        
            # PAGE 1 - Contract Terms and Payment Information
            story.extend(self._create_page1_content(data, fillable=fillable))
            
            # PAGE BREAK
            story.append(PageBreak())
        
            # PAGE 2 - Tuition Breakdown and Payment Schedule
            story.extend(self._create_page2_content(data, fillable=fillable))
        
            # Build PDF
            doc.build(story)
            
            print(f"✅ Enhanced YZA Contract created ({'fillable' if fillable else 'static'}): {os.path.abspath(filepath)}")
            return filepath
            
        except Exception as e:
            print(f"❌ Error creating contract: {str(e)}")
            raise

    def _create_page1_content(self, data, fillable=True):
        """Create Page 1 content - Contract terms and payment info"""
        content = []
        
        # Header - Dynamic based on division
        division = data.get('division', 'YZA')
        if division == 'YOH':
            school_name = "YESHIVA OHR HATZAFON"
        elif division == 'KOLLEL':
            school_name = "KOLLEL NER YEHOSHUA"
        else:  # YZA or default
            school_name = "YESHIVA ZICHRON ARYEH"
        
        content.append(Paragraph(school_name, self.styles['ContractTitle']))
        content.append(Paragraph("ENROLLMENT CONTRACT", self.styles['ContractTitle']))
        content.append(Spacer(1, 8))
        
        # Student name and academic year aligned with section headers
        student_name = data.get('student_name', '_' * 40)
        academic_year = data.get('academic_year', '2024-2025')
        
        # Use Paragraph elements to match section header alignment exactly
        # Make Student Name line bigger with font size 12
        content.append(Paragraph(f'<font size="12"><b>Student Name:</b> {student_name}</font>', self.styles['CompactText']))
        content.append(Spacer(1, 4))
        content.append(Paragraph(f"<b>Academic Year:</b> {academic_year}", self.styles['CompactText']))
        content.append(Spacer(1, 8))
        
        # Payment Terms Section
        content.append(Paragraph("PAYMENT TERMS", self.styles['SectionHeader']))
        
        # Get registration fee option and payment details
        registration_option = data.get('registration_fee_option', 'upfront')
        registration_rolled_in = data.get('registration_rolled_in', False) or registration_option == 'rolled'
        
        # Format total_amount with comma separators
        total_amount = data.get('total_amount', '$0.00')
        if isinstance(total_amount, (int, float)):
            total_amount = f"${total_amount:,.2f}"
        elif isinstance(total_amount, str):
            # If it's a string, extract the numeric value and reformat with commas
            try:
                # Remove $ and commas, convert to float, then reformat
                numeric_value = float(total_amount.replace('$', '').replace(',', ''))
                total_amount = f"${numeric_value:,.2f}"
            except (ValueError, TypeError):
                # If conversion fails, keep original value
                pass
        
        # Payment terms with checkboxes (fillable or static)
        if fillable:
            # Create fillable checkboxes for payment terms
            if registration_rolled_in:
                # When registration fee is rolled in, only show the rolled-in message
                payment_terms_data = [
                    [FormCheckbox(name='reg_fee_rolled', checked=True, size=12), 
                     "Registration Fee: ROLLED INTO TUITION PAYMENTS"]
                ]
                payment_table = Table(payment_terms_data, colWidths=[0.3*inch, 5.7*inch])
                payment_table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                content.append(payment_table)
            else:
                # Registration fee should be static, not fillable - align with field labels
                reg_fee_data = [
                    ["Registration Fee:", data.get('registration_fee', '$750.00'), "- Due at contract signing", ""]
                ]
                reg_fee_table = Table(reg_fee_data, colWidths=[1.3*inch, 2.2*inch, 1*inch, 1.5*inch])
                reg_fee_table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                content.append(reg_fee_table)
                
                # Add payment method checkboxes only when registration fee is NOT rolled in
                payment_terms_data = [
                    [FormCheckbox(name='payment_method_below', size=12), 
                     "Use payment method below", 
                     FormCheckbox(name='check_enclosed', size=12), 
                     "Check enclosed"]
                ]
                payment_table = Table(payment_terms_data, colWidths=[0.3*inch, 2.5*inch, 0.3*inch, 2*inch])
                payment_table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                content.append(payment_table)
        else:
            # Static version
            if registration_rolled_in:
                # When registration fee is rolled in, only show the rolled-in message
                payment_terms_text = "☐ Registration Fee: ROLLED INTO TUITION PAYMENTS"
                content.append(Paragraph(payment_terms_text, self.styles['CompactText']))
            else:
                # Create separate paragraphs to prevent overlapping
                reg_fee_text = f"Registration Fee: {data.get('registration_fee', '$750.00')} - Due at contract signing"
                content.append(Paragraph(reg_fee_text, self.styles['CompactText']))
                # Add payment method checkboxes only when registration fee is NOT rolled in
                payment_terms_text = "☐ Use payment method below ☐ Check enclosed"
                content.append(Paragraph(payment_terms_text, self.styles['CompactText']))
        
        content.append(Spacer(1, 6))
        
        # Tuition Total with note (should be static, not fillable)
        content.append(Paragraph(f"<b>TUITION TOTAL: {total_amount}</b>", self.styles['CompactText']))
        content.append(Paragraph("<i>See payment schedule and breakdown details on page 2</i>", self.styles['CompactText']))
        content.append(Spacer(1, 8))
        
        # Payment Method Section
        content.append(Paragraph("PAYMENT METHOD", self.styles['SectionHeader']))
        
        # Calculate dynamic values for check payment option
        num_payments = len(data.get('payment_schedule', []))
        if num_payments == 0:
            num_payments = 10  # default
        
        # Calculate monthly payment amount
        try:
            if isinstance(total_amount, str):
                # Remove $ and commas, convert to float
                total_numeric = float(total_amount.replace('$', '').replace(',', ''))
            else:
                total_numeric = float(total_amount)
            monthly_amount = total_numeric / num_payments if num_payments > 0 else 0
            monthly_amount_str = f"${monthly_amount:,.2f}"
        except (ValueError, TypeError):
            monthly_amount_str = "$0.00"
        
        if fillable:
            # Fillable Payment Method Section
            
            # Credit Card Section with checkbox aligned to left margin
            content.append(CheckboxWithText('payment_method_credit_card', 'Credit Card', size=12))
            content.append(Spacer(1, 4))
            
            cc_data = [
                ["Card Number:", FormTextField(name='cc_number', value=data.get('cc_number', ''), width=150, height=16), 
                 "Exp Date:", FormTextField(name='cc_exp_date', value=data.get('cc_exp_date', ''), width=60, height=16)],
                ["Cardholder Name:", FormTextField(name='cc_holder_name', value=data.get('cc_holder_name', ''), width=150, height=16), 
                 "CVV:", FormTextField(name='cc_cvv', value=data.get('cc_cvv', ''), width=40, height=16)],
                ["Billing ZIP:", FormTextField(name='cc_zip', value=data.get('cc_zip', ''), width=80, height=16), 
                 "Charge Date:", FormTextField(name='cc_charge_date', value=data.get('cc_charge_date', ''), width=80, height=16)]
            ]
            cc_table = Table(cc_data, colWidths=[1.3*inch, 2.5*inch, 0.8*inch, 1.4*inch])
            cc_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(cc_table)
            content.append(Spacer(1, 6))
            
            # ACH/Bank Transfer Section with checkbox aligned to left margin
            content.append(CheckboxWithText('payment_method_ach', 'ACH/Bank Transfer', size=12))
            content.append(Spacer(1, 3))
            
            ach_data = [
                ["Routing Number:", FormTextField(name='ach_routing_number', value=data.get('ach_routing_number', ''), width=120, height=16), 
                 "Account Number:", FormTextField(name='ach_account_number', value=data.get('ach_account_number', ''), width=150, height=16)],
                ["Account Holder:", FormTextField(name='ach_account_holder_name', value=data.get('ach_account_holder_name', ''), width=120, height=16), 
                 "Debit Date:", FormTextField(name='ach_debit_date', value=data.get('ach_debit_date', ''), width=80, height=16)]
            ]
            ach_table = Table(ach_data, colWidths=[1.2*inch, 1.8*inch, 1.1*inch, 2.4*inch])
            ach_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(ach_table)
            content.append(Spacer(1, 6))
            
            # Check Payment Section with checkbox aligned to left margin
            content.append(CheckboxWithText('payment_method_checks', 'Check', size=12))
            content.append(Spacer(1, 3))
            check_text = f"I will mail {num_payments} post-dated checks in the amount of {monthly_amount_str} each"
            check_data = [
                [check_text]
            ]
            check_table = Table(check_data, colWidths=[6*inch])
            check_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(check_table)
            content.append(Spacer(1, 6))
            
            # Third Party Payer Section with checkbox aligned to left margin
            content.append(CheckboxWithText('payment_method_third_party', 'Third Party Payer', size=12))
            content.append(Spacer(1, 3))
            
            tp_data = [
                ["Name:", FormTextField(name='third_party_payer_name', value=data.get('third_party_payer_name', ''), width=250, height=16)],
                ["Relationship:", FormTextField(name='third_party_payer_relationship', value=data.get('third_party_payer_relationship', ''), width=200, height=16)],
                ["Contact Information:", FormTextField(name='third_party_payer_contact', value=data.get('third_party_payer_contact', ''), width=280, height=16)]
            ]
            tp_table = Table(tp_data, colWidths=[1.5*inch, 4.5*inch])
            tp_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(tp_table)
            
        else:
            # Static Payment Method Section
            
            # Credit Card Section
            content.append(Paragraph("<b>☐ Credit Card</b>", self.styles['CompactText']))
            content.append(Spacer(1, 4))
            cc_data = [
                ["Card Number:", '_' * 25, "Exp Date:", '_' * 10],
                ["Cardholder Name:", '_' * 25, "CVV:", '_' * 8],
                ["Billing ZIP:", '_' * 15, "Charge Date:", '_' * 15]
            ]
            cc_table = Table(cc_data, colWidths=[1.3*inch, 2.5*inch, 0.8*inch, 1.4*inch])
            cc_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(cc_table)
            content.append(Spacer(1, 6))
            
            # ACH/Bank Transfer Section
            content.append(Paragraph("<b>☐ ACH/Bank Transfer</b>", self.styles['CompactText']))
            content.append(Spacer(1, 3))
            ach_data = [
                ["Routing Number:", '_' * 20, "Account Number:", '_' * 25],
                ["Account Holder:", '_' * 20, "Debit Date:", '_' * 15]
            ]
            ach_table = Table(ach_data, colWidths=[1.2*inch, 1.8*inch, 1.1*inch, 2.4*inch])
            ach_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(ach_table)
            content.append(Spacer(1, 6))
            
            # Check Payment Section with bold header and dynamic text on separate lines
            content.append(Paragraph("<b>☐ Check</b>", self.styles['CompactText']))
            content.append(Spacer(1, 3))
            check_text = f"I will mail {num_payments} post-dated checks in the amount of {monthly_amount_str} each"
            check_data = [
                [check_text]
            ]
            check_table = Table(check_data, colWidths=[6*inch])
            check_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(check_table)
            content.append(Spacer(1, 8))
            
            # Third Party Payer Section
            content.append(Paragraph("<b>☐ Third Party Payer</b>", self.styles['CompactText']))
            content.append(Spacer(1, 4))
            tp_data = [
                ["Name:", '_' * 45],
                ["Relationship:", '_' * 35],
                ["Contact Information:", '_' * 50]
            ]
            tp_table = Table(tp_data, colWidths=[1.5*inch, 4.5*inch])
            tp_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            content.append(tp_table)
        
        content.append(Spacer(1, 12))
        
        # Simple Signature Section
        content.append(Paragraph("AGREEMENT", self.styles['SectionHeader']))
        
        # Dynamic agreement message
        current_year = datetime.now().year
        academic_year_display = f"{current_year}-{current_year + 1}"
        
        # Get division name from data and set school name for agreement text
        student_division = data.get('division', 'YZA')
        if student_division == 'YOH':
            division_name = "Yeshiva Ohr Hatzafon"
        elif student_division == 'KOLLEL':
            division_name = "Kollel Ner Yehoshua"
        else:  # YZA or default
            division_name = "Yeshiva Zichron Aryeh"
        
        agreement_text = f"""I hereby enroll my son for the {academic_year_display} academic year in {division_name}. 
        I understand that this is a binding obligation toward the Yeshiva and that I will be responsible for 
        satisfaction of his tuition obligation as well as all costs incurred by my son, including damage caused 
        to the Yeshiva property. With my signature I hereby accept the terms of this contract and authorize 
        all payments required herein."""
        
        content.append(Paragraph(agreement_text, self.styles['SmallText']))
        content.append(Spacer(1, 12))
        
        # Signature lines (fillable or static)
        if fillable:
            sig_data = [
                ["Parent/Guardian Signature:", FormTextField(name='parent_signature', width=180, height=20), 
                 "Date:", FormTextField(name='signature_date', value=datetime.now().strftime('%m/%d/%Y'), width=80, height=20)]
            ]
        else:
            sig_data = [
                ["Parent/Guardian Signature:", '_' * 35, "Date:", '_' * 15]
            ]
        
        sig_table = Table(sig_data, colWidths=[2*inch, 2.5*inch, 0.7*inch, 1.3*inch])
        sig_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(sig_table)
        
        return content
    
    def _create_page2_content(self, data, fillable=True):
        """Create Page 2 content - Tuition breakdown and payment schedule"""
        content = []
        
        # Page 2 Header
        content.append(Paragraph("TUITION BREAKDOWN & PAYMENT SCHEDULE", self.styles['ContractTitle']))
        content.append(Spacer(1, 12))
        
        # Student name for reference
        student_name = data.get('student_name', 'Student')
        content.append(Paragraph(f"Student: {student_name}", self.styles['CompactText']))
        content.append(Spacer(1, 12))
        
        # Tuition Components Breakdown
        content.append(Paragraph("TUITION COMPONENTS", self.styles['SectionHeader']))
        
        # Get tuition components
        components = data.get('tuition_components', [])
        
        if components:
            breakdown_data = [["Component", "Amount"]]
            total_components = 0
            
            for component in components:
                if component.get('is_enabled', True):
                    name = component.get('name', '')
                    amount = component.get('final_amount', 0)
                    if isinstance(amount, (int, float)):
                        amount_str = f"{amount:,.2f}"
                        total_components += amount
                    else:
                        amount_str = str(amount)
                    breakdown_data.append([name, amount_str])
            
            # Add total row
            breakdown_data.append(["TOTAL", f"{total_components:,.2f}"])
            
            breakdown_table = Table(breakdown_data, colWidths=[3*inch, 2*inch])
            breakdown_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ]))
            content.append(breakdown_table)
        else:
            content.append(Paragraph("No tuition components available.", self.styles['CompactText']))
        
        content.append(Spacer(1, 20))
        
        # Payment Schedule
        content.append(Paragraph("PAYMENT SCHEDULE", self.styles['SectionHeader']))
        
        # Get payment schedule and registration fee info
        payment_schedule = data.get('payment_schedule', [])
        registration_option = data.get('registration_fee_option', 'upfront')
        registration_rolled_in = data.get('registration_rolled_in', False) or registration_option == 'rolled'
        registration_fee = data.get('registration_fee', '$750.00')
        
        if payment_schedule:
            schedule_data = [["Payment #", "Due Date", "Amount"]]
            
            # Add registration fee as first line item if being charged upfront
            if not registration_rolled_in:
                # Format registration fee amount
                if isinstance(registration_fee, str):
                    try:
                        reg_fee_numeric = float(registration_fee.replace('$', '').replace(',', ''))
                        reg_fee_str = f"{reg_fee_numeric:,.2f}"
                    except (ValueError, TypeError):
                        reg_fee_str = registration_fee.replace('$', '')
                else:
                    reg_fee_str = f"{registration_fee:,.2f}"
                
                schedule_data.append(["Registration", "At Contract Signing", reg_fee_str])
            
            # Add regular payment schedule
            for payment in payment_schedule:
                payment_num = payment.get('payment_number', '')
                due_date = payment.get('due_date', '')
                # Format due date to show only month and year
                if due_date and ',' in due_date:
                    try:
                        # Parse "September 1, 2025" and convert to "September 2025"
                        parts = due_date.split(',')
                        month_day = parts[0].strip()
                        year = parts[1].strip()
                        month = month_day.split(' ')[0]
                        due_date = f"{month} {year}"
                    except:
                        pass  # Keep original format if parsing fails
                
                amount = payment.get('amount', 0)
                if isinstance(amount, (int, float)):
                    amount_str = f"{amount:,.2f}"
                else:
                    amount_str = str(amount)
                
                schedule_data.append([str(payment_num), due_date, amount_str])
            
            schedule_table = Table(schedule_data, colWidths=[1*inch, 2.5*inch, 1.5*inch])
            schedule_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            content.append(schedule_table)
        else:
            content.append(Paragraph("No payment schedule available.", self.styles['CompactText']))
        
        content.append(Spacer(1, 20))
        
        # Important Notes
        content.append(Paragraph("IMPORTANT NOTES", self.styles['SectionHeader']))
        
        # Get division name dynamically for notes section
        student_division = data.get('division', 'YZA')
        if student_division == 'YOH':
            division_name = "Yeshiva Ohr Hatzafon"
        elif student_division == 'KOLLEL':
            division_name = "Kollel Ner Yehoshua"
        else:  # YZA or default
            division_name = "Yeshiva Zichron Aryeh"
        
        notes_text = f"""
        • Please do not modify this contract in any way<br/>
        • If you have any questions or concerns please contact the financial office<br/>
        • Checks should be mailed to {division_name}, PO Box 486, Cedarhurst, NY 11516
        """
        content.append(Paragraph(notes_text, self.styles['CompactText']))
        
        return content

# Test the service if run directly
if __name__ == "__main__":
    # Test data
    test_data = {
        'student_name': 'Test Student',
        'academic_year': '2024-2025',
        'registration_fee': '$750.00',
        'registration_fee_option': 'upfront',
        'total_amount': '$17,525.00',
        'tuition_components': [
            {'name': 'Registration Fee', 'final_amount': 750.0, 'is_enabled': True},
            {'name': 'Tuition', 'final_amount': 8775.0, 'is_enabled': True},
            {'name': 'Room', 'final_amount': 4000.0, 'is_enabled': True},
            {'name': 'Board', 'final_amount': 4000.0, 'is_enabled': True}
        ],
        'payment_schedule': [
            {'payment_number': 1, 'due_date': 'September 1, 2025', 'amount': 1677.5},
            {'payment_number': 2, 'due_date': 'October 1, 2025', 'amount': 1677.5},
            {'payment_number': 3, 'due_date': 'November 1, 2025', 'amount': 1677.5}
        ]
    }
    
    service = ContractStructureService()
    service.create_yza_contract(test_data) 