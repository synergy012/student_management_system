"""
Simple Fillable PDF Service - Creates fillable PDF forms for tuition contracts
Uses ReportLab for layout and PyPDF2 for form field creation
"""

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from datetime import datetime
import os

class SimpleFillablePDFService:
    """Service for creating fillable PDF forms"""
    
    # School information by division
    SCHOOL_INFO = {
        'YZA': 'Yeshiva Zichron Aryeh',
        'YOH': 'Yeshiva Ohr Hatzafon', 
        'KOLLEL': 'Kollel Ner Yehoshua'
    }
    
    SCHOOL_ADDRESS = "PO Box 486 Cedarhurst, NY 11516"
    SCHOOL_PHONE = "Tel: (347) 619-9074"
    SCHOOL_FAX = "Fax: (516) 295-5737"
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='ContractTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.black
        ))
        
        # School header style
        self.styles.add(ParagraphStyle(
            name='SchoolHeader',
            parent=self.styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.black
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.black
        ))
        
        # Contract text style
        self.styles.add(ParagraphStyle(
            name='ContractText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceBefore=6,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
            textColor=colors.black
        ))
        
        # Small text style
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.black
        ))

    def create_contract_template(self, division='YZA', output_path=None):
        """
        Create a PDF contract template for the specified division
        
        Args:
            division (str): Division code (YZA, YOH, KOLLEL)
            output_path (str): Path where to save the PDF
            
        Returns:
            str: Path to the created PDF file
        """
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"static/templates/pdf/contract_template_{division.lower()}_{timestamp}.pdf"
            
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create the PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Build the document content
        story = []
        
        # Add school header
        school_name = self.SCHOOL_INFO.get(division, 'Yeshiva Zichron Aryeh')
        story.extend(self._create_header_section(school_name))
        
        # Add contract title
        story.append(Paragraph("TUITION CONTRACT", self.styles['ContractTitle']))
        story.append(Spacer(1, 20))
        
        # Add form sections
        story.extend(self._create_student_info_section())
        story.extend(self._create_financial_info_section())
        story.extend(self._create_payment_method_section())
        story.extend(self._create_payment_schedule_section())
        story.extend(self._create_contract_terms_section())
        story.extend(self._create_signature_section())
        
        # Build the PDF
        doc.build(story)
        
        print(f"✅ Contract template created: {output_path}")
        return output_path
    
    def _create_header_section(self, school_name):
        """Create the school header section"""
        content = []
        
        # School name
        content.append(Paragraph(f"<b>{school_name}</b>", self.styles['SchoolHeader']))
        
        # Address and contact info
        content.append(Paragraph(self.SCHOOL_ADDRESS, self.styles['SchoolHeader']))
        content.append(Paragraph(f"{self.SCHOOL_PHONE} {self.SCHOOL_FAX}", self.styles['SchoolHeader']))
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_student_info_section(self):
        """Create student information section with form fields"""
        content = []
        
        content.append(Paragraph("STUDENT INFORMATION", self.styles['SectionHeader']))
        
        # Create table for student info fields with underlines for filling
        student_data = [
            ['Student Name:', '_' * 40, 'Academic Year:', '_' * 15],
            ['Division:', '_' * 15, 'Date:', '_' * 20],
        ]
        
        student_table = Table(student_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 2*inch])
        student_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        content.append(student_table)
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_financial_info_section(self):
        """Create financial information section"""
        content = []
        
        content.append(Paragraph("FINANCIAL INFORMATION", self.styles['SectionHeader']))
        
        # Financial breakdown table
        financial_data = [
            ['Tuition Amount:', '$_____________', 'Registration Fee:', '$_____________'],
            ['Room Charge:', '$_____________', 'Board Charge:', '$_____________'],
            ['Financial Aid:', '$_____________', 'Final Amount:', '$_____________'],
        ]
        
        financial_table = Table(financial_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
        financial_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        content.append(financial_table)
        content.append(Spacer(1, 15))
        
        # Registration fee option
        content.append(Paragraph("Registration Fee: ☐ Upfront  ☐ Rolled into monthly payments", self.styles['ContractText']))
        content.append(Spacer(1, 15))
        
        return content
    
    def _create_payment_method_section(self):
        """Create payment method section"""
        content = []
        
        content.append(Paragraph("PAYMENT METHOD", self.styles['SectionHeader']))
        
        # Payment method selection
        content.append(Paragraph("Payment Method: ☐ Credit Card  ☐ ACH/Bank  ☐ Third Party", self.styles['ContractText']))
        content.append(Spacer(1, 10))
        
        # Credit Card Section
        content.append(Paragraph("<b>Credit Card Information (if selected):</b>", self.styles['ContractText']))
        
        cc_data = [
            ['Cardholder Name:', '_' * 35],
            ['Expiration Date:', '_' * 10, 'Billing Zip:', '_' * 10],
            ['Charge Date (day of month):', '_' * 5],
        ]
        
        cc_table = Table(cc_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
        cc_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        content.append(cc_table)
        content.append(Spacer(1, 15))
        
        # ACH Section
        content.append(Paragraph("<b>ACH/Bank Information (if selected):</b>", self.styles['ContractText']))
        
        ach_data = [
            ['Account Holder Name:', '_' * 35],
            ['Routing Number:', '_' * 15, 'Debit Date:', '_' * 5],
        ]
        
        ach_table = Table(ach_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
        ach_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        content.append(ach_table)
        content.append(Spacer(1, 15))
        
        # Third Party Section
        content.append(Paragraph("<b>Third Party Payer Information (if selected):</b>", self.styles['ContractText']))
        
        third_party_data = [
            ['Payer Name:', '_' * 35],
            ['Relationship:', '_' * 15, 'Contact:', '_' * 20],
        ]
        
        third_party_table = Table(third_party_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
        third_party_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        content.append(third_party_table)
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_payment_schedule_section(self):
        """Create payment schedule section"""
        content = []
        
        content.append(Paragraph("PAYMENT SCHEDULE", self.styles['SectionHeader']))
        
        content.append(Paragraph("Payment Plan: _________________", self.styles['ContractText']))
        content.append(Spacer(1, 10))
        
        # Payment schedule table
        content.append(Paragraph("<b>Payment Schedule:</b>", self.styles['ContractText']))
        
        # Create a table for payment schedule
        schedule_headers = ['Payment #', 'Due Date', 'Amount']
        schedule_data = [schedule_headers]
        
        # Add 12 rows for payments (flexible)
        for i in range(1, 13):
            schedule_data.append([f'{i}', '_' * 15, '$_________'])
        
        schedule_table = Table(schedule_data, colWidths=[1*inch, 2*inch, 1.5*inch])
        schedule_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # Header background
        ]))
        
        content.append(schedule_table)
        content.append(Spacer(1, 15))
        
        # Summary
        schedule_summary = [
            ['First Payment Date:', '_' * 15, 'Final Payment Date:', '_' * 15],
            ['Number of Payments:', '_' * 5, 'Monthly Amount:', '$_________'],
        ]
        
        summary_table = Table(schedule_summary, colWidths=[2*inch, 2*inch, 2*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        content.append(summary_table)
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_contract_terms_section(self):
        """Create contract terms section"""
        content = []
        
        content.append(Paragraph("CONTRACT TERMS", self.styles['SectionHeader']))
        
        terms = [
            "1. <b>Tuition Payment:</b> The above tuition amount is due according to the payment schedule selected. Late payments may incur additional fees.",
            
            "2. <b>Registration Fee:</b> The registration fee secures your enrollment and is non-refundable. If 'Upfront' is selected, this amount is due at contract signing. If 'Rolled In' is selected, it is included in the monthly payment schedule.",
            
            "3. <b>Payment Method:</b> Payments will be processed according to the selected method and schedule. For credit card payments, charges will occur on the specified day of each month. For ACH payments, debits will occur on the specified day of each month.",
            
            "4. <b>Late Payments:</b> Payments not received within 10 days of the due date may incur a late fee. Continued non-payment may result in suspension of services.",
            
            "5. <b>Refund Policy:</b> Tuition refunds are subject to the school's refund policy as outlined in the student handbook.",
            
            "6. <b>Changes:</b> Any changes to this contract must be made in writing and agreed upon by both parties.",
            
            "7. <b>Agreement:</b> By signing below, both parties agree to the terms and conditions outlined in this contract."
        ]
        
        for term in terms:
            content.append(Paragraph(term, self.styles['ContractText']))
            content.append(Spacer(1, 8))
        
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_signature_section(self):
        """Create signature section"""
        content = []
        
        content.append(Paragraph("SIGNATURES", self.styles['SectionHeader']))
        
        # Signature table
        sig_data = [
            ['Student/Parent Signature:', '_' * 35, 'Date:', '_' * 15],
            ['', '', '', ''],
            ['Print Name:', '_' * 35, 'School Representative:', '_' * 25],
            ['', '', 'Date:', '_' * 15],
        ]
        
        sig_table = Table(sig_data, colWidths=[2*inch, 3*inch, 1*inch, 1.5*inch])
        sig_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        content.append(sig_table)
        content.append(Spacer(1, 20))
        
        # Footer
        content.append(Paragraph("This contract is legally binding upon signature by both parties.", self.styles['SmallText']))
        
        return content

    def create_filled_contract(self, division, student_data, contract_data, output_path=None):
        """
        Create a filled contract with actual data
        
        Args:
            division (str): Division code
            student_data (dict): Student information
            contract_data (dict): Contract information
            output_path (str): Output path for the PDF
            
        Returns:
            str: Path to the created PDF
        """
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in student_data.get('student_name', 'student') if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            output_path = f"contracts/filled_contract_{safe_name}_{timestamp}.pdf"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create the PDF with filled data
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        story = []
        
        # Add school header
        school_name = self.SCHOOL_INFO.get(division, 'Yeshiva Zichron Aryeh')
        story.extend(self._create_header_section(school_name))
        
        # Add contract title
        story.append(Paragraph("TUITION CONTRACT", self.styles['ContractTitle']))
        story.append(Spacer(1, 20))
        
        # Add filled sections
        story.extend(self._create_filled_student_info(student_data, contract_data))
        story.extend(self._create_filled_financial_info(contract_data))
        story.extend(self._create_filled_payment_method(contract_data))
        story.extend(self._create_filled_payment_schedule(contract_data))
        story.extend(self._create_contract_terms_section())
        story.extend(self._create_signature_section())
        
        # Build the PDF
        doc.build(story)
        
        print(f"✅ Filled contract created: {output_path}")
        return output_path
    
    def _create_filled_student_info(self, student_data, contract_data):
        """Create filled student information section"""
        content = []
        
        content.append(Paragraph("STUDENT INFORMATION", self.styles['SectionHeader']))
        
        student_data_filled = [
            ['Student Name:', student_data.get('student_name', ''), 'Academic Year:', contract_data.get('academic_year', '')],
            ['Division:', student_data.get('division', ''), 'Date:', datetime.now().strftime("%B %d, %Y")],
        ]
        
        student_table = Table(student_data_filled, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 2*inch])
        student_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        content.append(student_table)
        content.append(Spacer(1, 20))
        
        return content
    
    def _create_filled_financial_info(self, contract_data):
        """Create filled financial information section"""
        content = []
        
        content.append(Paragraph("FINANCIAL INFORMATION", self.styles['SectionHeader']))
        
        def format_currency(amount):
            if amount is None:
                return "$0.00"
            try:
                return f"${float(amount):,.2f}"
            except (ValueError, TypeError):
                return str(amount)
        
        financial_data_filled = [
            ['Tuition Amount:', format_currency(contract_data.get('total_tuition', 0)), 'Registration Fee:', format_currency(contract_data.get('registration_fee', 0))],
            ['Room Charge:', format_currency(contract_data.get('room_amount', 0)), 'Board Charge:', format_currency(contract_data.get('board_amount', 0))],
            ['Financial Aid:', format_currency(contract_data.get('financial_aid_amount', 0)), 'Final Amount:', format_currency(contract_data.get('final_amount', 0))],
        ]
        
        financial_table = Table(financial_data_filled, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
        financial_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        content.append(financial_table)
        content.append(Spacer(1, 15))
        
        # Registration fee option with checkmarks
        reg_fee_option = contract_data.get('registration_fee_option', 'upfront')
        upfront_check = "☑" if reg_fee_option == 'upfront' else "☐"
        rolled_check = "☑" if reg_fee_option == 'rolled_in' else "☐"
        
        content.append(Paragraph(f"Registration Fee: {upfront_check} Upfront  {rolled_check} Rolled into monthly payments", self.styles['ContractText']))
        content.append(Spacer(1, 15))
        
        return content
    
    def _create_filled_payment_method(self, contract_data):
        """Create filled payment method section"""
        content = []
        
        content.append(Paragraph("PAYMENT METHOD", self.styles['SectionHeader']))
        
        # Payment method selection with checkmarks
        payment_method = contract_data.get('payment_method', '')
        cc_check = "☑" if payment_method == 'credit_card' else "☐"
        ach_check = "☑" if payment_method == 'ach' else "☐"
        third_check = "☑" if payment_method == 'third_party' else "☐"
        
        content.append(Paragraph(f"Payment Method: {cc_check} Credit Card  {ach_check} ACH/Bank  {third_check} Third Party", self.styles['ContractText']))
        content.append(Spacer(1, 10))
        
        # Show relevant payment info based on method
        if payment_method == 'credit_card':
            content.append(Paragraph("<b>Credit Card Information:</b>", self.styles['ContractText']))
            cc_data = [
                ['Cardholder Name:', contract_data.get('cc_holder_name', '')],
                ['Expiration Date:', contract_data.get('cc_exp_date', ''), 'Billing Zip:', contract_data.get('cc_zip', '')],
                ['Charge Date (day of month):', str(contract_data.get('cc_charge_date', ''))],
            ]
            
            cc_table = Table(cc_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            cc_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            content.append(cc_table)
            
        elif payment_method == 'ach':
            content.append(Paragraph("<b>ACH/Bank Information:</b>", self.styles['ContractText']))
            ach_data = [
                ['Account Holder Name:', contract_data.get('ach_account_holder_name', '')],
                ['Routing Number:', contract_data.get('ach_routing_number', ''), 'Debit Date:', str(contract_data.get('ach_debit_date', ''))],
            ]
            
            ach_table = Table(ach_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            ach_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            content.append(ach_table)
            
        elif payment_method == 'third_party':
            content.append(Paragraph("<b>Third Party Payer Information:</b>", self.styles['ContractText']))
            third_party_data = [
                ['Payer Name:', contract_data.get('third_party_payer_name', '')],
                ['Relationship:', contract_data.get('third_party_payer_relationship', ''), 'Contact:', contract_data.get('third_party_payer_contact', '')],
            ]
            
            third_party_table = Table(third_party_data, colWidths=[2*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            third_party_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            content.append(third_party_table)
        
        content.append(Spacer(1, 20))
        return content
    
    def _create_filled_payment_schedule(self, contract_data):
        """Create filled payment schedule section"""
        content = []
        
        content.append(Paragraph("PAYMENT SCHEDULE", self.styles['SectionHeader']))
        
        content.append(Paragraph(f"Payment Plan: {contract_data.get('payment_plan', '')}", self.styles['ContractText']))
        content.append(Spacer(1, 10))
        
        # Payment schedule table
        content.append(Paragraph("<b>Payment Schedule:</b>", self.styles['ContractText']))
        
        # Get payment schedule from contract data
        payment_schedule = contract_data.get('payment_schedule', [])
        
        if payment_schedule:
            schedule_headers = ['Payment #', 'Due Date', 'Amount']
            schedule_data = [schedule_headers]
            
            for i, payment in enumerate(payment_schedule, 1):
                due_date = payment.get('due_date', '')
                amount = f"${float(payment.get('amount', 0)):,.2f}" if payment.get('amount') else '$0.00'
                schedule_data.append([str(i), due_date, amount])
            
            schedule_table = Table(schedule_data, colWidths=[1*inch, 2*inch, 1.5*inch])
            schedule_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ]))
            
            content.append(schedule_table)
        
        content.append(Spacer(1, 15))
        
        # Summary
        def format_date(date_val):
            if isinstance(date_val, str):
                return date_val
            elif hasattr(date_val, 'strftime'):
                return date_val.strftime("%B %d, %Y")
            return str(date_val) if date_val else ''
        
        def format_currency(amount):
            if amount is None:
                return "$0.00"
            try:
                return f"${float(amount):,.2f}"
            except (ValueError, TypeError):
                return str(amount)
        
        schedule_summary = [
            ['First Payment Date:', format_date(contract_data.get('first_payment_date', '')), 'Final Payment Date:', format_date(contract_data.get('final_payment_date', ''))],
            ['Number of Payments:', str(contract_data.get('number_of_payments', '')), 'Monthly Amount:', format_currency(contract_data.get('monthly_payment_amount', 0))],
        ]
        
        summary_table = Table(schedule_summary, colWidths=[2*inch, 2*inch, 2*inch, 1.5*inch])
        summary_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        
        content.append(summary_table)
        content.append(Spacer(1, 20))
        
        return content


# Testing function
def create_test_templates():
    """Create test templates for all divisions"""
    service = SimpleFillablePDFService()
    
    for division in ['YZA', 'YOH', 'KOLLEL']:
        try:
            output_path = f"static/templates/pdf/contract_template_{division.lower()}.pdf"
            result = service.create_contract_template(division=division, output_path=output_path)
            print(f"✅ Created template for {division}: {result}")
        except Exception as e:
            print(f"❌ Error creating template for {division}: {str(e)}")
            import traceback
            traceback.print_exc()

def create_test_filled_contract():
    """Create a test filled contract"""
    service = SimpleFillablePDFService()
    
    # Sample data
    student_data = {
        'student_name': 'John Doe',
        'division': 'YZA'
    }
    
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
        'first_payment_date': 'September 1, 2024',
        'final_payment_date': 'June 1, 2025',
        'number_of_payments': 10,
        'monthly_payment_amount': 701.00,
        'payment_schedule': [
            {'due_date': 'September 1, 2024', 'amount': 701.00},
            {'due_date': 'October 1, 2024', 'amount': 701.00},
            {'due_date': 'November 1, 2024', 'amount': 701.00},
            # ... more payments
        ]
    }
    
    try:
        result = service.create_filled_contract('YZA', student_data, contract_data)
        print(f"✅ Test filled contract created: {result}")
    except Exception as e:
        print(f"❌ Error creating test contract: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_test_templates()
    create_test_filled_contract() 