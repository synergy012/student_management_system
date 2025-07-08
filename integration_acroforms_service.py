"""
Integration-Ready AcroForms Service for Student Management System
Uses working patterns discovered through testing
"""

from reportlab.platypus import SimpleDocTemplate, Flowable, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os

class FormTextField(Flowable):
    """Working text field for forms"""
    def __init__(self, name, value="", width=150, height=24, **kwargs):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.name = name
        self.value = str(value) if value else ""
        self.kwargs = kwargs

    def draw(self):
        form = self.canv.acroForm
        form.textfieldRelative(
            name=self.name,
            value=self.value,
            width=self.width,
            height=self.height,
            forceBorder=True,
            borderStyle='inset',
            fontSize=10,
            **self.kwargs
        )

class FormCheckbox(Flowable):
    """Working checkbox for forms"""
    def __init__(self, name, checked=False, size=12, **kwargs):
        Flowable.__init__(self)
        self.width = size
        self.height = size
        self.name = name
        self.checked = checked
        self.kwargs = kwargs

    def draw(self):
        form = self.canv.acroForm
        form.checkboxRelative(
            name=self.name,
            checked=self.checked,
            size=self.width,
            forceBorder=True,
            **self.kwargs
        )

class IntegratedAcroFormsService:
    """Service to create fillable PDFs for the student management system"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_styles()
    
    def setup_styles(self):
        """Setup custom styles"""
        self.styles.add(ParagraphStyle(
            name='ContractTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.darkblue
        ))
    
    def create_tuition_contract_form(self, division, output_path=None, student_data=None):
        """Create a fillable tuition contract form"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"fillable_tuition_contract_{division}_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(
            output_path, 
            pagesize=letter,
            rightMargin=72, leftMargin=72,
            topMargin=72, bottomMargin=72
        )
        
        story = []
        
        # Title
        school_names = {
            'YZA': 'Yeshiva Zichron Aryeh',
            'YOH': 'Yeshiva Ohr Hatzafon', 
            'KOLLEL': 'Kollel Ner Yehoshua'
        }
        
        title = f"{school_names.get(division, division)} - Tuition Contract"
        story.append(Paragraph(title, self.styles['ContractTitle']))
        story.append(Spacer(1, 20))
        
        # Student Information
        story.append(Paragraph("STUDENT INFORMATION", self.styles['SectionHeader']))
        
        # Student name
        story.append(Paragraph("Student Name:", self.styles['Normal']))
        story.append(FormTextField(
            name='student_name',
            value=student_data.get('name', '') if student_data else '',
            width=300,
            height=24
        ))
        story.append(Spacer(1, 10))
        
        # Academic year 
        story.append(Paragraph("Academic Year:", self.styles['Normal']))
        story.append(FormTextField(
            name='academic_year',
            value='2024-2025',
            width=120,
            height=24
        ))
        story.append(Spacer(1, 20))
        
        # Financial Information
        story.append(Paragraph("FINANCIAL INFORMATION", self.styles['SectionHeader']))
        
        # Create table for financial fields
        financial_data = [
            [
                Paragraph("Total Tuition:", self.styles['Normal']),
                FormTextField(
                    name='total_tuition',
                    value=student_data.get('total_tuition', '') if student_data else '',
                    width=120,
                    height=24
                )
            ],
            [
                Paragraph("Registration Fee:", self.styles['Normal']),
                FormTextField(
                    name='registration_fee',
                    value=student_data.get('registration_fee', '') if student_data else '',
                    width=120,
                    height=24
                )
            ]
        ]
        
        financial_table = Table(financial_data, colWidths=[2*inch, 2*inch])
        financial_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(financial_table)
        story.append(Spacer(1, 15))
        
        # Payment Method Selection
        story.append(Paragraph("PAYMENT METHOD", self.styles['SectionHeader']))
        
        payment_data = [
            [
                FormCheckbox(name='payment_credit_card', size=12),
                Paragraph("Credit Card", self.styles['Normal']),
                FormCheckbox(name='payment_ach', size=12),
                Paragraph("ACH/Bank Transfer", self.styles['Normal'])
            ]
        ]
        
        payment_table = Table(payment_data, colWidths=[0.3*inch, 1.5*inch, 0.3*inch, 2*inch])
        payment_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(payment_table)
        story.append(Spacer(1, 15))
        
        # Credit Card Information
        story.append(Paragraph("Credit Card Information:", self.styles['Normal']))
        cc_data = [
            [
                Paragraph("Cardholder Name:", self.styles['Normal']),
                FormTextField(name='cc_holder_name', width=200, height=24)
            ],
            [
                Paragraph("Card Number:", self.styles['Normal']),
                FormTextField(name='cc_number', width=200, height=24)
            ],
            [
                Paragraph("Exp Date (MM/YY):", self.styles['Normal']),
                FormTextField(name='cc_exp_date', width=80, height=24),
                Paragraph("CVV:", self.styles['Normal']),
                FormTextField(name='cc_cvv', width=60, height=24)
            ]
        ]
        
        cc_table = Table(cc_data, colWidths=[1.5*inch, 2*inch, 0.8*inch, 1*inch])
        cc_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(cc_table)
        story.append(Spacer(1, 20))
        
        # Monthly Payment Amount
        story.append(Paragraph("Monthly Payment Amount:", self.styles['Normal']))
        story.append(FormTextField(
            name='monthly_amount',
            value=student_data.get('monthly_amount', '') if student_data else '',
            width=120,
            height=24
        ))
        story.append(Spacer(1, 20))
        
        # Signature Section
        story.append(Paragraph("SIGNATURE", self.styles['SectionHeader']))
        
        sig_data = [
            [
                Paragraph("Parent/Student Signature:", self.styles['Normal']),
                FormTextField(name='signature', width=250, height=40)
            ],
            [
                Paragraph("Print Name:", self.styles['Normal']),
                FormTextField(name='print_name', width=250, height=24)
            ],
            [
                Paragraph("Date:", self.styles['Normal']),
                FormTextField(name='date', width=120, height=24)
            ]
        ]
        
        sig_table = Table(sig_data, colWidths=[1.5*inch, 3*inch])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(sig_table)
        
        # Build PDF
        doc.build(story)
        print(f"✅ Fillable tuition contract created: {output_path}")
        return output_path
    
    def create_application_form(self, division, output_path=None):
        """Create a fillable application form"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"fillable_application_{division}_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        story = []
        
        story.append(Paragraph(f"{division} Application Form", self.styles['ContractTitle']))
        story.append(Spacer(1, 20))
        
        # Personal Information
        story.append(Paragraph("PERSONAL INFORMATION", self.styles['SectionHeader']))
        
        fields = [
            ("First Name:", "first_name"),
            ("Last Name:", "last_name"),
            ("Email:", "email"),
            ("Phone:", "phone"),
            ("Address:", "address")
        ]
        
        for label, field_name in fields:
            story.append(Paragraph(label, self.styles['Normal']))
            story.append(FormTextField(name=field_name, width=300, height=24))
            story.append(Spacer(1, 10))
        
        # Emergency Contact
        story.append(Paragraph("EMERGENCY CONTACT", self.styles['SectionHeader']))
        story.append(Paragraph("Emergency Contact Name:", self.styles['Normal']))
        story.append(FormTextField(name='emergency_name', width=250, height=24))
        story.append(Spacer(1, 5))
        story.append(Paragraph("Emergency Contact Phone:", self.styles['Normal']))
        story.append(FormTextField(name='emergency_phone', width=200, height=24))
        story.append(Spacer(1, 20))
        
        # Agreement
        story.append(Paragraph("AGREEMENT", self.styles['SectionHeader']))
        agreement_data = [
            [
                FormCheckbox(name='agree_terms', size=12),
                Paragraph("I agree to the terms and conditions", self.styles['Normal'])
            ],
            [
                FormCheckbox(name='agree_policies', size=12),
                Paragraph("I agree to the school policies", self.styles['Normal'])
            ]
        ]
        
        agreement_table = Table(agreement_data, colWidths=[0.3*inch, 4*inch])
        agreement_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(agreement_table)
        
        doc.build(story)
        print(f"✅ Fillable application form created: {output_path}")
        return output_path

# Integration with your existing system
def integrate_with_financial_blueprint():
    """Example of how to integrate with your financial blueprint"""
    
    # This could be added to your financial.py blueprint
    service = IntegratedAcroFormsService()
    
    # Example usage with student data
    student_data = {
        'name': 'John Doe',
        'total_tuition': '$15,000',
        'registration_fee': '$500',
        'monthly_amount': '$1,500'
    }
    
    # Create the fillable contract
    output_path = service.create_tuition_contract_form('YZA', student_data=student_data)
    return output_path

if __name__ == "__main__":
    # Test the service
    service = IntegratedAcroFormsService()
    
    # Test tuition contract
    service.create_tuition_contract_form('YZA')
    
    # Test application form
    service.create_application_form('YZA')
    
    print("✅ All fillable forms created successfully!")
    print("📋 AcroForms work perfectly with ReportLab free version!") 