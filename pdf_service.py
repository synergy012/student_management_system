"""
PDF Service for generating acceptance letters as PDF attachments
"""
import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from flask import current_app


class PDFService:
    """Service for generating PDF documents"""
    
    @staticmethod
    def generate_acceptance_letter_pdf(student, division_config=None):
        """
        Generate an acceptance letter PDF for a student
        
        Args:
            student: Student model instance
            division_config: DivisionConfig model instance (optional)
            
        Returns:
            bytes: PDF content as bytes
        """
        try:
            # Get division configuration if not provided
            if not division_config:
                from models import DivisionConfig
                division_config = DivisionConfig.query.filter_by(division=student.division).first()
            
            # Create a BytesIO buffer to hold the PDF
            buffer = io.BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Custom styles with division-specific colors
            division = student.division or 'YZA'
            primary_color = '#003366' if division == 'YZA' else '#1e4d2b'
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=30,
                alignment=TA_CENTER,
                textColor=HexColor(primary_color)
            )
            
            subtitle_style = ParagraphStyle(
                'CustomSubtitle',
                parent=styles['Normal'],
                fontSize=14,
                spaceAfter=20,
                alignment=TA_CENTER,
                textColor=HexColor('#666666'),
                fontName='Helvetica-Oblique'
            )
            
            header_style = ParagraphStyle(
                'CustomHeader',
                parent=styles['Heading2'],
                fontSize=16,
                spaceAfter=12,
                textColor=HexColor('#34495e')
            )
            
            body_style = ParagraphStyle(
                'CustomBody',
                parent=styles['Normal'],
                fontSize=12,
                spaceAfter=12,
                leading=16
            )
            
            signature_style = ParagraphStyle(
                'Signature',
                parent=styles['Normal'],
                fontSize=12,
                alignment=TA_RIGHT,
                spaceAfter=6
            )
            
            # Build the document content
            story = []
            
            # Get template content from division config or use defaults
            school_name = (division_config.pdf_letterhead_title if division_config and division_config.pdf_letterhead_title 
                          else ("Yeshiva Zichron Aryeh" if division == 'YZA' else "Yeshiva Ohr Hatzafon"))
            
            subtitle = (division_config.pdf_letterhead_subtitle if division_config and division_config.pdf_letterhead_subtitle
                       else ("Excellence in Torah Learning and Personal Growth" if division == 'YZA' else "Illuminating Paths in Torah and Wisdom"))
            
            # Create letterhead with logo and custom styling
            letterhead_elements = PDFService._create_letterhead(
                school_name, subtitle, division_config, title_style, subtitle_style
            )
            story.extend(letterhead_elements)
            story.append(Spacer(1, 20))
            
            # Date
            date_str = datetime.now().strftime("%B %d, %Y")
            story.append(Paragraph(f"<b>Date:</b> {date_str}", body_style))
            story.append(Spacer(1, 12))
            
            # Student information
            story.append(Paragraph("<b>ACCEPTANCE LETTER</b>", header_style))
            story.append(Spacer(1, 12))
            
            # Greeting - use custom template or default
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            
            greeting_text = (division_config.pdf_greeting_text if division_config and division_config.pdf_greeting_text
                           else f"בס״ד\n\nDear {student_name},")
            
            # Replace template variables
            greeting_text = greeting_text.replace('{student_name}', student_name)
            story.append(Paragraph(greeting_text.replace('\n', '<br/>'), body_style))
            story.append(Spacer(1, 12))
            
            # Main acceptance content - use custom template or default
            if division_config and division_config.pdf_main_content:
                main_content = division_config.pdf_main_content
            else:
                if division == 'YZA':
                    main_content = """We are delighted to inform you that you have been accepted to Yeshiva Zichron Aryeh for the upcoming academic year. After careful review of your application and credentials, we are confident that you will be a valuable addition to our Yeshiva community.
                    
Your acceptance is a testament to your dedication to Torah learning and your commitment to personal growth. We look forward to supporting you in your journey of spiritual and intellectual development."""
                else:
                    main_content = """It is with great pleasure that we inform you of your acceptance to Yeshiva Ohr Hatzafon for the upcoming zman. Your application demonstrated the qualities and commitment we value in our talmidim, and we are confident you will thrive in our unique learning environment.
                    
At Yeshiva Ohr Hatzafon, we pride ourselves on fostering an atmosphere of intensive Torah study combined with personal mentorship. Your journey with us will be one of profound growth in learning, middos, and avodas Hashem."""
            
            # Replace template variables in main content
            main_content = main_content.replace('{student_name}', student_name)
            main_content = main_content.replace('{school_name}', school_name)
            
            story.append(Paragraph(main_content.replace('\n', '<br/>'), body_style))
            story.append(Spacer(1, 20))
            
            # Student details table
            student_data = [
                ['<b>Student Information</b>', ''],
                ['Full Name:', student_name],
                ['Hebrew Name:', student.hebrew_name or 'N/A'],
                ['Division:', division],
                ['Phone:', student.phone_number or 'N/A'],
                ['Email:', student.email or 'N/A']
            ]
            
            if student.date_of_birth:
                student_data.append(['Date of Birth:', student.date_of_birth.strftime('%B %d, %Y')])
            
            student_table = Table(student_data, colWidths=[2*inch, 4*inch])
            student_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#2c3e50')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, HexColor('#bdc3c7'))
            ]))
            
            story.append(student_table)
            story.append(Spacer(1, 20))
            
            # Next steps - use custom template or default
            if division_config and division_config.pdf_next_steps:
                next_steps_content = division_config.pdf_next_steps
            else:
                if division == 'YZA':
                    next_steps_content = """1. Confirm your acceptance by responding to this email within 14 days
2. Complete the enrollment forms that will be sent separately
3. Submit any remaining required documents
4. Attend the orientation session (details to follow)"""
                else:
                    next_steps_content = """1. Reply to this email confirming your intention to attend
2. Submit the enrollment deposit within 10 business days
3. Complete the online registration forms
4. Schedule your pre-arrival meeting with the Mashgiach"""
            
            # Format next steps
            next_steps_formatted = f"<b>Next Steps:</b><br/>{next_steps_content.replace(chr(10), '<br/>')}"
            story.append(Paragraph(next_steps_formatted, body_style))
            story.append(Spacer(1, 20))
            
            # Closing text - use custom template or default
            if division_config and division_config.pdf_closing_text:
                closing_text = division_config.pdf_closing_text
            else:
                if division == 'YZA':
                    closing_text = """We are excited to welcome you to our Beis Medrash, where you will join a vibrant community of talmidim dedicated to Torah study and avodas Hashem. Our experienced Rebbeim and staff are committed to helping you reach your full potential.
                    
If you have any questions or need additional information, please don't hesitate to contact our admissions office."""
                else:
                    closing_text = """Our Rebbeim are looking forward to learning with you and helping you reach new heights in your Torah studies. The unique approach of Yeshiva Ohr Hatzafon combines rigorous textual analysis with practical application, preparing our talmidim for lives of Torah leadership.
                    
Should you have any questions about housing arrangements, the daily schedule, or any other matters, please contact our office."""
            
            # Replace template variables in closing text
            closing_text = closing_text.replace('{student_name}', student_name)
            closing_text = closing_text.replace('{school_name}', school_name)
            
            story.append(Paragraph(closing_text.replace('\n', '<br/>'), body_style))
            story.append(Spacer(1, 30))
            
            # Welcome message
            story.append(Paragraph("We eagerly anticipate welcoming you to our Yeshiva family!", body_style))
            story.append(Spacer(1, 20))
            
            # Signature - use custom template or default with optional image
            signature_elements = PDFService._create_signature_section(
                division_config, division, school_name, signature_style
            )
            story.extend(signature_elements)
            
            # Footer with contact info and optional footer image
            footer_elements = PDFService._create_footer_section(
                division_config, school_name, styles
            )
            story.extend(footer_elements)
            
            # Build the PDF
            doc.build(story)
            
            # Get the PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            
            current_app.logger.info(f"✅ Generated acceptance letter PDF for student {student.id} ({len(pdf_content)} bytes)")
            return pdf_content
            
        except Exception as e:
            current_app.logger.error(f"❌ Error generating acceptance letter PDF: {str(e)}")
            raise e
    
    @staticmethod
    def _create_letterhead(school_name, subtitle, division_config, title_style, subtitle_style):
        """Create letterhead section with full-width support and flexible layouts"""
        elements = []
        
        try:
            # Get letterhead configuration
            layout = division_config.pdf_letterhead_layout if division_config else 'logo_above_text'
            full_width = division_config.pdf_letterhead_full_width if division_config else False
            margin_top = division_config.pdf_letterhead_margin_top if division_config else 0
            margin_bottom = division_config.pdf_letterhead_margin_bottom if division_config else 20
            
            # Add top margin if specified
            if margin_top > 0:
                elements.append(Spacer(1, margin_top))
            
            # Apply custom colors if configured
            if division_config and division_config.pdf_letterhead_text_color:
                title_style.textColor = HexColor(division_config.pdf_letterhead_text_color)
                subtitle_style.textColor = HexColor(division_config.pdf_letterhead_text_color)
            
            # Check if custom logo is configured
            has_logo = (division_config and 
                       division_config.pdf_letterhead_logo_path and 
                       os.path.exists(division_config.pdf_letterhead_logo_path))
            
            if has_logo:
                logo_path = division_config.pdf_letterhead_logo_path
                
                # Get logo dimensions
                if full_width:
                    # For full-width letterheads, use page width minus margins
                    logo_width = division_config.pdf_letterhead_logo_width or 450  # ~6.25" at 72 DPI
                    logo_height = division_config.pdf_letterhead_logo_height or 150  # Proportional height
                else:
                    logo_width = division_config.pdf_letterhead_logo_width or 150
                    logo_height = division_config.pdf_letterhead_logo_height or 75
                
                # Create logo image
                logo = Image(logo_path, width=logo_width, height=logo_height)
                
                # Handle different layout options
                if layout == 'logo_only':
                    # Just the logo, no text
                    elements.extend(PDFService._create_logo_only_layout(logo, full_width))
                    
                elif layout == 'text_only':
                    # Just text, no logo (ignore logo even if provided)
                    elements.extend(PDFService._create_text_only_layout(school_name, subtitle, title_style, subtitle_style))
                    
                elif layout == 'logo_beside_text':
                    # Logo and text side by side
                    elements.extend(PDFService._create_logo_beside_text_layout(
                        logo, school_name, subtitle, title_style, subtitle_style, full_width, division_config
                    ))
                    
                else:  # 'logo_above_text' (default)
                    # Logo above text
                    elements.extend(PDFService._create_logo_above_text_layout(
                        logo, school_name, subtitle, title_style, subtitle_style, full_width, division_config
                    ))
                
                current_app.logger.info(f"✅ Added letterhead with layout '{layout}': {logo_path}")
                
            else:
                # No logo, just text
                elements.extend(PDFService._create_text_only_layout(school_name, subtitle, title_style, subtitle_style))
            
            # Add bottom margin
            if margin_bottom > 0:
                elements.append(Spacer(1, margin_bottom))
                
        except Exception as e:
            current_app.logger.error(f"❌ Error creating letterhead: {str(e)}")
            # Fallback to simple text header
            elements = [
                Spacer(1, 10),
                Paragraph(school_name, title_style),
                Paragraph(subtitle, subtitle_style) if subtitle else None,
                Spacer(1, 20)
            ]
            elements = [e for e in elements if e is not None]
        
        return elements
    
    @staticmethod
    def _create_logo_only_layout(logo, full_width):
        """Create layout with only logo"""
        elements = []
        
        if full_width:
            # Full width logo
            logo_table = Table([[logo]], colWidths=[6.5*inch])
        else:
            # Centered logo
            logo_table = Table([[logo]], colWidths=[6*inch])
        
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(logo_table)
        return elements
    
    @staticmethod
    def _create_text_only_layout(school_name, subtitle, title_style, subtitle_style):
        """Create layout with only text"""
        elements = []
        elements.append(Paragraph(school_name, title_style))
        if subtitle:
            elements.append(Paragraph(subtitle, subtitle_style))
        return elements
    
    @staticmethod
    def _create_logo_above_text_layout(logo, school_name, subtitle, title_style, subtitle_style, full_width, division_config):
        """Create layout with logo above text"""
        elements = []
        
        # Add background color if specified
        if division_config and division_config.pdf_letterhead_background_color:
            bg_color = HexColor(division_config.pdf_letterhead_background_color)
            
            # Create a table with background color
            if full_width:
                content_table = Table([[logo], [Paragraph(school_name, title_style)]], colWidths=[6.5*inch])
                if subtitle:
                    content_table = Table([[logo], [Paragraph(school_name, title_style)], [Paragraph(subtitle, subtitle_style)]], colWidths=[6.5*inch])
            else:
                content_table = Table([[logo], [Paragraph(school_name, title_style)]], colWidths=[6*inch])
                if subtitle:
                    content_table = Table([[logo], [Paragraph(school_name, title_style)], [Paragraph(subtitle, subtitle_style)]], colWidths=[6*inch])
            
            content_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ]))
            
            elements.append(content_table)
        else:
            # Simple layout without background
            if full_width:
                logo_table = Table([[logo]], colWidths=[6.5*inch])
            else:
                logo_table = Table([[logo]], colWidths=[6*inch])
            
            logo_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(logo_table)
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(school_name, title_style))
            if subtitle:
                elements.append(Paragraph(subtitle, subtitle_style))
        
        return elements
    
    @staticmethod
    def _create_logo_beside_text_layout(logo, school_name, subtitle, title_style, subtitle_style, full_width, division_config):
        """Create layout with logo beside text"""
        elements = []
        
        # Create text content
        text_content = [Paragraph(school_name, title_style)]
        if subtitle:
            text_content.append(Paragraph(subtitle, subtitle_style))
        
        # Combine text into a single cell
        text_cell = []
        for text in text_content:
            text_cell.append(text)
        
        # Create side-by-side layout
        if full_width:
            # Logo takes 40%, text takes 60%
            side_by_side_table = Table([[logo, text_cell]], colWidths=[2.6*inch, 3.9*inch])
        else:
            # Standard layout
            side_by_side_table = Table([[logo, text_cell]], colWidths=[2*inch, 4*inch])
        
        # Apply background color if specified
        if division_config and division_config.pdf_letterhead_background_color:
            bg_color = HexColor(division_config.pdf_letterhead_background_color)
            side_by_side_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo center
                ('ALIGN', (1, 0), (1, 0), 'LEFT'),    # Text left
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                ('LEFTPADDING', (1, 0), (1, 0), 20),  # Text padding
            ]))
        else:
            side_by_side_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo center
                ('ALIGN', (1, 0), (1, 0), 'LEFT'),    # Text left
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (1, 0), (1, 0), 20),  # Text padding
            ]))
        
        elements.append(side_by_side_table)
        return elements
    
    @staticmethod
    def _create_signature_section(division_config, division, school_name, signature_style):
        """Create signature section with optional signature image"""
        elements = []
        
        try:
            # Signature greeting
            greeting = "With Torah blessings," if division == 'YOH' else "B'vracha,"
            elements.append(Paragraph(greeting, signature_style))
            elements.append(Spacer(1, 30))
            
            # Check if custom signature image is configured
            if division_config and division_config.pdf_signature_image_path:
                sig_path = division_config.pdf_signature_image_path
                
                if os.path.exists(sig_path):
                    # Add signature image
                    sig_image = Image(sig_path, width=150, height=50)  # Reasonable signature size
                    
                    # Create table to right-align the signature
                    sig_table = Table([[sig_image]], colWidths=[6*inch])
                    sig_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    elements.append(sig_table)
                    elements.append(Spacer(1, 10))
                    
                    current_app.logger.info(f"✅ Added signature image to PDF: {sig_path}")
                else:
                    current_app.logger.warning(f"⚠️ Signature image not found: {sig_path}")
            
            # Signature name and title
            signature_name = (division_config.pdf_signature_name if division_config and division_config.pdf_signature_name
                            else "Rabbi [Name]")
            signature_title = (division_config.pdf_signature_title if division_config and division_config.pdf_signature_title
                             else "Rosh Yeshiva")
            
            elements.append(Paragraph(f"<b>{signature_name}</b>", signature_style))
            elements.append(Paragraph(signature_title, signature_style))
            elements.append(Paragraph(school_name, signature_style))
            
        except Exception as e:
            current_app.logger.error(f"❌ Error creating signature section: {str(e)}")
            # Fallback to simple text signature
            signature_name = (division_config.pdf_signature_name if division_config and division_config.pdf_signature_name
                            else "Rabbi [Name]")
            signature_title = (division_config.pdf_signature_title if division_config and division_config.pdf_signature_title
                             else "Rosh Yeshiva")
            
            elements = [
                Paragraph("With Torah blessings," if division == 'YOH' else "B'vracha,", signature_style),
                Spacer(1, 30),
                Paragraph(f"<b>{signature_name}</b>", signature_style),
                Paragraph(signature_title, signature_style),
                Paragraph(school_name, signature_style)
            ]
        
        return elements
    
    @staticmethod
    def _create_footer_section(division_config, school_name, styles):
        """Create footer section with optional footer image and contact info"""
        elements = []
        
        try:
            elements.append(Spacer(1, 30))
            
            # Check if custom footer image is configured
            if division_config and division_config.pdf_footer_image_path:
                footer_path = division_config.pdf_footer_image_path
                
                if os.path.exists(footer_path):
                    # Get footer image dimensions (with defaults)
                    footer_width = division_config.pdf_footer_image_width or 500
                    footer_height = division_config.pdf_footer_image_height or 100
                    
                    # Create footer image
                    footer_image = Image(footer_path, width=footer_width, height=footer_height)
                    
                    # Create table to center the footer image
                    footer_table = Table([[footer_image]], colWidths=[6*inch])
                    footer_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    # Apply background color if configured
                    if division_config.pdf_footer_background_color:
                        footer_table.setStyle(TableStyle([
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('BACKGROUND', (0, 0), (-1, -1), HexColor(division_config.pdf_footer_background_color)),
                            ('TOPPADDING', (0, 0), (-1, -1), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                        ]))
                    
                    elements.append(footer_table)
                    elements.append(Spacer(1, 10))
                    
                    current_app.logger.info(f"✅ Added footer image to PDF: {footer_path}")
                else:
                    current_app.logger.warning(f"⚠️ Footer image not found: {footer_path}")
            
            # Add contact information text
            if division_config and division_config.pdf_contact_info:
                contact_info = division_config.pdf_contact_info
            else:
                contact_info = f"""{school_name}
[Address]
Phone: [Phone] | Email: [Email]"""
            
            # Create footer text style
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_CENTER,
                textColor=HexColor('#666666')
            )
            
            elements.append(Paragraph(contact_info.replace('\n', '<br/>'), footer_style))
            
        except Exception as e:
            current_app.logger.error(f"❌ Error creating footer section: {str(e)}")
            # Fallback to simple text footer
            contact_info = f"""{school_name}
[Address]
Phone: [Phone] | Email: [Email]"""
            
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_CENTER,
                textColor=HexColor('#666666')
            )
            
            elements = [
                Spacer(1, 30),
                Paragraph(contact_info.replace('\n', '<br/>'), footer_style)
            ]
        
        return elements
    
    @staticmethod
    def save_pdf_to_file(pdf_content, filename):
        """
        Save PDF content to a file
        
        Args:
            pdf_content: PDF content as bytes
            filename: Filename to save to
            
        Returns:
            str: Full path to saved file
        """
        try:
            # Ensure attachments directory exists
            attachments_dir = 'attachments'
            if not os.path.exists(attachments_dir):
                os.makedirs(attachments_dir)
            
            # Create full path
            file_path = os.path.join(attachments_dir, filename)
            
            # Write PDF content to file
            with open(file_path, 'wb') as f:
                f.write(pdf_content)
            
            current_app.logger.info(f"✅ Saved PDF to {file_path}")
            return file_path
            
        except Exception as e:
            current_app.logger.error(f"❌ Error saving PDF to file: {str(e)}")
            raise e
    
    @staticmethod
    def generate_filename(student, division=None):
        """
        Generate a standardized filename for the acceptance letter PDF
        
        Args:
            student: Student model instance
            division: Division name (optional)
            
        Returns:
            str: Generated filename
        """
        try:
            # Get student name
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            
            # Clean the name for filename (remove special characters)
            import re
            clean_name = re.sub(r'[^\w\s-]', '', student_name)
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
            
            # Get division
            division = division or student.division or 'YZA'
            
            # Get current date
            date_str = datetime.now().strftime("%Y%m%d")
            
            # Generate filename
            filename = f"{division}_Acceptance_Letter_{clean_name}_{date_str}.pdf"
            
            return filename
            
        except Exception as e:
            current_app.logger.error(f"❌ Error generating PDF filename: {str(e)}")
            # Fallback filename
            return f"Acceptance_Letter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    @staticmethod
    def generate_tuition_contract_pdf(student, division_config=None):
        """
        Generate a YZA-style tuition contract PDF for a student
        
        Args:
            student: Student model instance
            division_config: DivisionConfig model instance (optional)
            
        Returns:
            bytes: PDF content as bytes
        """
        try:
            # Get division configuration if not provided
            if not division_config:
                from models import DivisionConfig
                division_config = DivisionConfig.query.filter_by(division=student.division).first()
            
            # Create a BytesIO buffer to hold the PDF
            buffer = io.BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=50,
                bottomMargin=72
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Custom styles matching YZA format
            division = student.division or 'YZA'
            
            # Header approval style (small, right-aligned)
            approval_style = ParagraphStyle(
                'Approval',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_RIGHT,
                spaceAfter=20
            )
            
            # Year style (large, right-aligned)
            year_style = ParagraphStyle(
                'Year',
                parent=styles['Normal'],
                fontSize=16,
                alignment=TA_RIGHT,
                spaceAfter=10,
                fontName='Helvetica-Bold'
            )
            
            # School header style
            school_header_style = ParagraphStyle(
                'SchoolHeader',
                parent=styles['Normal'],
                fontSize=14,
                alignment=TA_CENTER,
                spaceAfter=5,
                fontName='Helvetica-Bold'
            )
            
            # Address style
            address_style = ParagraphStyle(
                'Address',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_CENTER,
                spaceAfter=20
            )
            
            # Contract title style
            title_style = ParagraphStyle(
                'ContractTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            # Body text style
            body_style = ParagraphStyle(
                'ContractBody',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=12,
                leading=16
            )
            
            # Build the document content
            story = []
            
            # Header approval line
            story.append(Paragraph("Approved By: YJ        TC", approval_style))
            
            # Academic year (right-aligned)
            current_year = datetime.now().year
            academic_year = f"{current_year}-{current_year + 1}"
            story.append(Paragraph(academic_year, year_style))
            
            # School letterhead
            school_name = "Yeshiva Zichron Aryeh" if division == 'YZA' else (
                division_config.pdf_letterhead_title if division_config and division_config.pdf_letterhead_title 
                else f"Yeshiva {division}"
            )
            
            story.append(Paragraph(school_name, school_header_style))
            
            # Address information
            if division == 'YZA':
                address_text = """PO Box 486   Cedarhurst, NY  11516<br/>
Tel: (347) 619-9074          Fax: (516) 295-5737"""
            else:
                address_text = """[Address Line 1]<br/>
Tel: [Phone]          Fax: [Fax]"""
            
            story.append(Paragraph(address_text, address_style))
            
            # Contract title
            story.append(Paragraph("ENROLLMENT CONTRACT", title_style))
            
            # Student name section
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            story.append(Paragraph(f"Student Name: <b>{student_name}</b>", body_style))
            story.append(Spacer(1, 20))
            
            # Payment sections
            # 1. Registration fee
            story.append(Paragraph("1.\tThe following is due at time of signature:", body_style))
            
            reg_fee_data = [
                ['', 'Registration:  $550.00', '☐ Use Payment Method Below', '☐ Check Enclosed']
            ]
            
            reg_fee_table = Table(reg_fee_data, colWidths=[0.5*inch, 2*inch, 2*inch, 1.5*inch])
            reg_fee_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            story.append(reg_fee_table)
            story.append(Spacer(1, 15))
            
            # 2. Payment method section
            story.append(Paragraph("2.\tIndicate your method of payment of $4,260.00:", body_style))
            story.append(Spacer(1, 8))
            
            # Payment options
            payment_options = [
                "☐ Enclosed Payment in Full",
                "☐ Four Equal Postdated Checks of $1,065.00 dated April through July.",
                "☐ Four Monthly Credit Card Payments of $1,065.00."
            ]
            
            for option in payment_options:
                story.append(Paragraph(f"\t{option}", body_style))
            
            # Credit card details section
            cc_details = """
\tCC #___________________________________Ex. Date ____________________<br/>
\tCardholder's Name _______________________________________<br/>
\tCVV Code __________ Billing Zip__________ Day of Month to Charge _______
"""
            story.append(Paragraph(cc_details, body_style))
            story.append(Spacer(1, 8))
            
            # Organization payment option
            story.append(Paragraph("\t☐ An organization will be sending monthly checks on my behalf.", body_style))
            story.append(Paragraph("\t\tTen Checks mailed from ____________________________", body_style))
            story.append(Spacer(1, 20))
            
            # Important notice (centered, bold)
            notice_style = ParagraphStyle(
                'Notice',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_CENTER,
                spaceAfter=20,
                fontName='Helvetica-Bold'
            )
            
            story.append(Paragraph("THIS ENROLLMENT CONTRACT WILL ONLY BE ACCEPTED IF ACCOMPANIED BY", notice_style))
            story.append(Paragraph("REGISTRATION FEE & PAYMENT SCHEDULE HAS BEEN FILLED OUT", notice_style))
            story.append(Spacer(1, 20))
            
            # Contract text
            contract_text = f"""I hereby enroll my son for the {academic_year} academic year in {school_name}. I understand that this is a binding obligation toward the Yeshiva and that I will be responsible for satisfaction of his tuition obligation as well as all costs incurred by my son, including damage caused to the Yeshiva property. With my signature I hereby accept the terms of this contract and authorize all payments required herein."""
            
            story.append(Paragraph(contract_text, body_style))
            story.append(Spacer(1, 40))
            
            # Signature section
            signature_data = [
                ['Signature:___________________________________________', 'Date:_______________']
            ]
            
            signature_table = Table(signature_data, colWidths=[4.5*inch, 1.5*inch])
            signature_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            story.append(signature_table)
            
            # Build the PDF
            doc.build(story)
            
            # Get the PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            
            try:
                current_app.logger.info(f"✅ Generated YZA-style tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            except:
                # Fallback if current_app is not available
                print(f"✅ Generated YZA-style tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            return pdf_content
            
        except Exception as e:
            try:
                current_app.logger.error(f"❌ Error generating tuition contract PDF: {str(e)}")
            except:
                # Fallback if current_app is not available
                print(f"❌ Error generating tuition contract PDF: {str(e)}")
            raise e

    @staticmethod
    def generate_enhanced_tuition_contract_pdf(student, contract_terms, division_config=None):
        """
        Generate an enhanced tuition contract PDF with custom payment terms
        
        Args:
            student: Student model instance
            contract_terms: Dictionary with enhanced contract terms
            division_config: DivisionConfig model instance (optional)
            
        Returns:
            bytes: PDF content as bytes
        """
        try:
            # Get division configuration if not provided
            if not division_config:
                from models import DivisionConfig
                division_config = DivisionConfig.query.filter_by(division=student.division).first()
            
            # Create a BytesIO buffer to hold the PDF
            buffer = io.BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=50,
                bottomMargin=72
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Custom styles matching YZA format
            division = student.division or 'YZA'
            
            # Header approval style (small, right-aligned)
            approval_style = ParagraphStyle(
                'Approval',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_RIGHT,
                spaceAfter=20
            )
            
            # Year style (large, right-aligned)
            year_style = ParagraphStyle(
                'Year',
                parent=styles['Normal'],
                fontSize=16,
                alignment=TA_RIGHT,
                spaceAfter=10,
                fontName='Helvetica-Bold'
            )
            
            # School header style
            school_header_style = ParagraphStyle(
                'SchoolHeader',
                parent=styles['Normal'],
                fontSize=14,
                alignment=TA_CENTER,
                spaceAfter=5,
                fontName='Helvetica-Bold'
            )
            
            # Address style
            address_style = ParagraphStyle(
                'Address',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_CENTER,
                spaceAfter=20
            )
            
            # Contract title style
            title_style = ParagraphStyle(
                'ContractTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            # Body text style
            body_style = ParagraphStyle(
                'ContractBody',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=12,
                leading=16
            )
            
            # Build the document content
            story = []
            
            # Header approval line
            story.append(Paragraph("Approved By: YJ        TC", approval_style))
            
            # Academic year (right-aligned)
            academic_year = f"{contract_terms['payment_start_year']}-{contract_terms['payment_start_year'] + 1}"
            story.append(Paragraph(academic_year, year_style))
            
            # School letterhead
            school_name = "Yeshiva Zichron Aryeh" if division == 'YZA' else (
                division_config.pdf_letterhead_title if division_config and division_config.pdf_letterhead_title 
                else f"Yeshiva {division}"
            )
            
            story.append(Paragraph(school_name, school_header_style))
            
            # Address information
            if division == 'YZA':
                address_text = """PO Box 486   Cedarhurst, NY  11516<br/>
Tel: (347) 619-9074          Fax: (516) 295-5737"""
            else:
                address_text = """[Address Line 1]<br/>
Tel: [Phone]          Fax: [Fax]"""
            
            story.append(Paragraph(address_text, address_style))
            
            # Contract title
            story.append(Paragraph("ENROLLMENT CONTRACT", title_style))
            
            # Student name section
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            story.append(Paragraph(f"Student Name: <b>{student_name}</b>", body_style))
            story.append(Spacer(1, 20))
            
            # Enhanced payment sections
            # 1. Registration fee section
            registration_fee = contract_terms.get('registration_fee', 0)
            registration_option = contract_terms.get('registration_fee_option', 'upfront')
            
            if registration_option == 'upfront' and registration_fee > 0:
                story.append(Paragraph("1.\tThe following is due at time of signature:", body_style))
                
                reg_fee_data = [
                    ['', f'Registration:  ${registration_fee:.2f}', '☐ Use Payment Method Below', '☐ Check Enclosed']
                ]
                
                reg_fee_table = Table(reg_fee_data, colWidths=[0.5*inch, 2*inch, 2*inch, 1.5*inch])
                reg_fee_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                ]))
                
                story.append(reg_fee_table)
                story.append(Spacer(1, 15))
                section_number = 2
            else:
                section_number = 1
            
            # 2. Enhanced payment method section
            total_tuition = contract_terms.get('total_tuition', 0)
            monthly_payment = contract_terms.get('monthly_payment', 0)
            number_of_payments = contract_terms.get('number_of_payments', 10)
            
            # Calculate payment amount for display
            if registration_option == 'upfront':
                payment_amount = total_tuition - registration_fee
            else:
                payment_amount = total_tuition
                
            story.append(Paragraph(f"{section_number}.\tIndicate your method of payment of ${payment_amount:,.2f}:", body_style))
            story.append(Spacer(1, 8))
            
            # Enhanced payment options
            payment_options = [
                "☐ Enclosed Payment in Full",
                f"☐ {number_of_payments} Monthly Payments of ${monthly_payment:.2f} each.",
                f"☐ {number_of_payments} Monthly Credit Card Payments of ${monthly_payment:.2f} each."
            ]
            
            for option in payment_options:
                story.append(Paragraph(f"\t{option}", body_style))
            
            # Payment schedule details
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"\t<b>Payment Schedule:</b> {contract_terms['start_month_name']} {contract_terms['payment_start_year']} through {contract_terms['end_month_name']} {contract_terms['payment_end_year']}", body_style))
            
            # Credit card details section
            cc_details = """
\tCC #___________________________________Ex. Date ____________________<br/>
\tCardholder's Name _______________________________________<br/>
\tCVV Code __________ Billing Zip__________ Day of Month to Charge _______
"""
            story.append(Paragraph(cc_details, body_style))
            story.append(Spacer(1, 8))
            
            # Organization payment option
            story.append(Paragraph(f"\t☐ An organization will be sending monthly checks on my behalf.", body_style))
            story.append(Paragraph(f"\t\t{number_of_payments} Checks mailed from ____________________________", body_style))
            story.append(Spacer(1, 20))
            
            # Important notice (centered, bold)
            notice_style = ParagraphStyle(
                'Notice',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_CENTER,
                spaceAfter=20,
                fontName='Helvetica-Bold'
            )
            
            notice_text = "THIS ENROLLMENT CONTRACT WILL ONLY BE ACCEPTED IF ACCOMPANIED BY"
            if registration_option == 'upfront' and registration_fee > 0:
                notice_text += "<br/>REGISTRATION FEE &amp; PAYMENT SCHEDULE HAS BEEN FILLED OUT"
            else:
                notice_text += "<br/>PAYMENT SCHEDULE HAS BEEN FILLED OUT"
            
            story.append(Paragraph(notice_text, notice_style))
            story.append(Spacer(1, 20))
            
            # Contract text with enhanced variables
            contract_text = f"""I hereby enroll my son for the {academic_year} academic year in {school_name}. I understand that this is a binding obligation toward the Yeshiva and that I will be responsible for satisfaction of his tuition obligation as well as all costs incurred by my son, including damage caused to the Yeshiva property. With my signature I hereby accept the terms of this contract and authorize all payments required herein."""
            
            if registration_option == 'rolled' and registration_fee > 0:
                contract_text += f" The registration fee of ${registration_fee:.2f} is included in the monthly payment schedule."
            
            story.append(Paragraph(contract_text, body_style))
            story.append(Spacer(1, 40))
            
            # Signature section
            signature_data = [
                ['Signature:___________________________________________', 'Date:_______________']
            ]
            
            signature_table = Table(signature_data, colWidths=[4.5*inch, 1.5*inch])
            signature_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            story.append(signature_table)
            
            # Build the PDF
            doc.build(story)
            
            # Get the PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            
            try:
                current_app.logger.info(f"✅ Generated enhanced tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            except:
                # Fallback if current_app is not available
                print(f"✅ Generated enhanced tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            return pdf_content
            
        except Exception as e:
            try:
                current_app.logger.error(f"❌ Error generating enhanced tuition contract PDF: {str(e)}")
            except:
                # Fallback if current_app is not available
                print(f"❌ Error generating enhanced tuition contract PDF: {str(e)}")
            raise e

    @staticmethod
    def generate_comprehensive_tuition_contract_pdf(student, contract_terms, division_config=None):
        """
        Generate a comprehensive tuition contract PDF with detailed payment methods
        
        Args:
            student: Student model instance
            contract_terms: Dictionary with contract terms and tuition breakdown
            division_config: DivisionConfig model instance (optional)
            
        Returns:
            bytes: PDF content as bytes
        """
        try:
            # Get division configuration if not provided
            if not division_config:
                from models import DivisionConfig
                division_config = DivisionConfig.query.filter_by(division=student.division).first()
            
            # Create a BytesIO buffer to hold the PDF
            buffer = io.BytesIO()
            
            # Create the PDF document with compact margins
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=50,
                leftMargin=50,
                topMargin=30,
                bottomMargin=40
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Custom styles - more compact
            division = student.division or 'YZA'
            
            # Header approval style (small, right-aligned)
            approval_style = ParagraphStyle(
                'Approval',
                parent=styles['Normal'],
                fontSize=9,
                alignment=TA_RIGHT,
                spaceAfter=8
            )
            
            # Year style (smaller, right-aligned)
            year_style = ParagraphStyle(
                'Year',
                parent=styles['Normal'],
                fontSize=12,
                alignment=TA_RIGHT,
                spaceAfter=6,
                fontName='Helvetica-Bold'
            )
            
            # School header style
            school_header_style = ParagraphStyle(
                'SchoolHeader',
                parent=styles['Normal'],
                fontSize=12,
                alignment=TA_CENTER,
                spaceAfter=3,
                fontName='Helvetica-Bold'
            )
            
            # Address style
            address_style = ParagraphStyle(
                'Address',
                parent=styles['Normal'],
                fontSize=9,
                alignment=TA_CENTER,
                spaceAfter=8
            )
            
            # Contract title style
            title_style = ParagraphStyle(
                'ContractTitle',
                parent=styles['Heading1'],
                fontSize=14,
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            # Body text style
            body_style = ParagraphStyle(
                'ContractBody',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=6,
                leading=12
            )
            
            # Payment method header style
            payment_header_style = ParagraphStyle(
                'PaymentHeader',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=4,
                fontName='Helvetica-Bold'
            )
            
            # Build the document content
            story = []
            
            # PAGE 1: CONTRACT & PAYMENT METHODS
            # Header approval line
            story.append(Paragraph("Approved: _________________ Date: _______", approval_style))
            
            # Academic year (right-aligned)
            academic_year = f"{contract_terms['payment_start_year']}-{contract_terms['payment_start_year'] + 1}"
            story.append(Paragraph(academic_year, year_style))
            
            # Division-specific school letterhead
            if division == 'YOH':
                school_name = "Yeshiva Ohr Hatzafon"
                address_text = """PO Box 486 Cedarhurst, NY 11516<br/>
Tel: (347) 619-9074 Fax: (516) 295-5737"""
            else:  # YZA or default
                school_name = "Yeshiva Zichron Aryeh"
                address_text = """PO Box 486 Cedarhurst, NY 11516<br/>
Tel: (347) 619-9074 Fax: (516) 295-5737"""
            
            story.append(Paragraph(school_name, school_header_style))
            story.append(Paragraph(address_text, address_style))
            
            # Contract title
            story.append(Paragraph("ENROLLMENT CONTRACT", title_style))
            
            # Student information section
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            story.append(Paragraph(f"<b>Student Name:</b> {student_name}", body_style))
            story.append(Spacer(1, 8))
            
            # Registration fee section - Dynamic based on whether it's rolled in
            registration_fee = contract_terms.get('registration_fee', 0)
            registration_rolled_in = contract_terms.get('registration_rolled_in', False)
            
            if registration_fee > 0 and not registration_rolled_in:
                # Separate registration fee
                story.append(Paragraph("1. The following is due at time of signature:", body_style))
                story.append(Spacer(1, 4))
                
                reg_data = [
                    [f'Registration: ${registration_fee:,.2f}', '☐ Use Payment Method Below', '☐ Check Enclosed']
                ]
                
                reg_table = Table(reg_data, colWidths=[2*inch, 2.5*inch, 1.5*inch])
                reg_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                story.append(reg_table)
                story.append(Spacer(1, 8))
            elif registration_fee > 0 and registration_rolled_in:
                # Registration fee rolled into monthly payments
                story.append(Paragraph("1. Registration Fee:", body_style))
                story.append(Spacer(1, 4))
                story.append(Paragraph(f"<b>Registration fee of ${registration_fee:,.2f} is included in the monthly payment amount below.</b>", body_style))
                story.append(Spacer(1, 8))
            else:
                # No registration fee
                story.append(Paragraph("1. Registration Fee: <b>No registration fee required</b>", body_style))
                story.append(Spacer(1, 8))
            
            # Tuition payment section
            tuition_amount = contract_terms.get('total_tuition', 0)
            monthly_payment = contract_terms.get('monthly_payment', 0)
            num_payments = contract_terms.get('number_of_payments', 10)
            
            story.append(Paragraph(f"2. Total Amount Due: ${tuition_amount:,.2f}", body_style))
            story.append(Spacer(1, 4))
            
            # Payment options
            payment_options = [
                ['☐ Enclosed Payment in Full'],
                [f'☐ {num_payments} Monthly Payments of ${monthly_payment:,.2f} each (September {contract_terms.get("payment_start_year", 2025)} - June {contract_terms.get("payment_start_year", 2025) + 1})']
            ]
            
            options_table = Table(payment_options, colWidths=[7*inch])
            options_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]))
            story.append(options_table)
            story.append(Spacer(1, 8))
            
            # Payment Method Section Header
            story.append(Paragraph("3. Payment Method (check one):", body_style))
            story.append(Spacer(1, 6))
            
            # ALL 4 PAYMENT METHODS
            
            # Payment Method 1: Credit Card
            story.append(Paragraph("<b>☐ Credit Card</b>", payment_header_style))
            cc_data = [
                ['CC Number', '_______________________________________________'],
                ['Exp Date', '___________', 'CVV', '________'],
                ['Cardholder Name', '_______________________________________________'],
                ['Billing Zip Code', '___________', 'Day to Charge', '________']
            ]
            
            cc_table = Table(cc_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            cc_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (1, 0), (3, 0)),  # Span CC number field
                ('SPAN', (1, 2), (3, 2)),  # Span cardholder name field
            ]))
            story.append(cc_table)
            story.append(Spacer(1, 6))
            
            # Payment Method 2: ACH Debit
            story.append(Paragraph("<b>☐ ACH Debit</b>", payment_header_style))
            ach_data = [
                ['Name on Account', '___________________________________________________'],
                ['Routing Number', '__________________', 'Account Number', '____________________'],
                ['Day to Debit', '_______']
            ]
            
            ach_table = Table(ach_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 1.5*inch])
            ach_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (1, 0), (3, 0)),  # Span name field
            ]))
            story.append(ach_table)
            story.append(Spacer(1, 6))
            
            # Payment Method 3: Post Dated Checks
            story.append(Paragraph("<b>☐ Post Dated Checks</b>", payment_header_style))
            story.append(Paragraph(f"I will provide {num_payments} post-dated checks of ${monthly_payment:,.2f} each", body_style))
            story.append(Spacer(1, 6))
            
            # Payment Method 4: Third Party Payment
            story.append(Paragraph("<b>☐ Third Party Payment</b>", payment_header_style))
            third_party_data = [
                ['Name of 3rd Party', '_______________________________________']
            ]
            
            third_party_table = Table(third_party_data, colWidths=[1.5*inch, 5.5*inch])
            third_party_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            story.append(third_party_table)
            story.append(Spacer(1, 8))
            
            # Contract acceptance notice
            story.append(Paragraph("THIS ENROLLMENT CONTRACT WILL ONLY BE ACCEPTED IF ACCOMPANIED BY", 
                                 ParagraphStyle('Notice', parent=styles['Normal'], 
                                              fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER)))
            story.append(Paragraph("REGISTRATION FEE & PAYMENT SCHEDULE HAS BEEN FILLED OUT", 
                                 ParagraphStyle('Notice', parent=styles['Normal'], 
                                              fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER)))
            story.append(Spacer(1, 8))
            
            # Contract agreement text
            contract_text = f"""I hereby enroll my son for the {academic_year} academic year in {school_name}. I
understand that this is a binding obligation toward the Yeshiva and that I will be responsible
for satisfaction of his tuition obligation as well as all costs incurred by my son, including
damage caused to the Yeshiva property. With my signature I hereby accept the terms of this
contract and authorize all payments required herein."""
            
            story.append(Paragraph(contract_text, body_style))
            story.append(Spacer(1, 8))
            
            # Signature section
            signature_data = [
                ['Signature:', '___________________________________________', 'Date:', '_______________']
            ]
            
            signature_table = Table(signature_data, colWidths=[1*inch, 3.5*inch, 0.75*inch, 1.25*inch])
            signature_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            story.append(signature_table)
            
            # PAGE BREAK
            story.append(PageBreak())
            
            # PAGE 2: TUITION DETAIL & BILLING SCHEDULE
            story.append(Paragraph("TUITION DETAIL & BILLING SCHEDULE", title_style))
            story.append(Paragraph(f"<b>Student:</b> {student_name}", body_style))
            story.append(Paragraph(f"<b>Academic Year:</b> {academic_year}", body_style))
            story.append(Spacer(1, 8))
            
            # Tuition Components Breakdown
            story.append(Paragraph("TUITION BREAKDOWN", payment_header_style))
            
            # Build tuition components table in correct order
            tuition_data = [['Component', 'Amount']]
            total_components = 0
            
            # 1. Registration Fee (first)
            registration_fee = contract_terms.get('registration_fee', 0)
            if registration_fee > 0:
                tuition_data.append(['Registration Fee', f"${registration_fee:,.2f}"])
                total_components += registration_fee
            
            # 2. Tuition components in order: Tuition, Room, Board, Others
            components = contract_terms.get('tuition_components', [])
            
            # Sort components to ensure proper order
            tuition_component = None
            room_component = None
            board_component = None
            other_components = []
            
            for component in components:
                name = component.get('name', '').lower()
                if 'tuition' in name and 'room' not in name and 'board' not in name:
                    tuition_component = component
                elif 'room' in name and 'board' not in name:
                    room_component = component
                elif 'board' in name and 'room' not in name:
                    board_component = component
                elif ('room' in name and 'board' in name) or 'dormitory' in name:
                    # This is a combined room & board component
                    room_component = component  # Treat as room component
                else:
                    other_components.append(component)
            
            # Add in correct order
            if tuition_component:
                tuition_data.append([tuition_component.get('name', 'Tuition'), f"${tuition_component.get('amount', 0):,.2f}"])
                total_components += tuition_component.get('amount', 0)
            
            if room_component:
                tuition_data.append([room_component.get('name', 'Room'), f"${room_component.get('amount', 0):,.2f}"])
                total_components += room_component.get('amount', 0)
            
            if board_component:
                tuition_data.append([board_component.get('name', 'Board'), f"${board_component.get('amount', 0):,.2f}"])
                total_components += board_component.get('amount', 0)
            
            # Add any other components
            for component in other_components:
                tuition_data.append([component.get('name', 'Other'), f"${component.get('amount', 0):,.2f}"])
                total_components += component.get('amount', 0)
            
            # Add total
            tuition_data.append(['', ''])  # Empty row
            tuition_data.append(['TOTAL AMOUNT DUE', f"${total_components:,.2f}"])
            
            tuition_table = Table(tuition_data, colWidths=[4*inch, 2*inch])
            tuition_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -3), 1, colors.black),
                ('LINEBELOW', (0, -2), (-1, -2), 2, colors.black),
                ('FONTNAME', (-1, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (0, -1), 'Helvetica-Bold'),
            ]))
            
            story.append(tuition_table)
            story.append(Spacer(1, 12))
            
            # Payment Schedule
            story.append(Paragraph("PAYMENT SCHEDULE", payment_header_style))
            
            # Build payment schedule table
            schedule_data = [['Payment #', 'Due Date', 'Amount']]
            
            # Add Registration payment if not rolled into monthly payments
            registration_fee = contract_terms.get('registration_fee', 0)
            registration_rolled_in = contract_terms.get('registration_rolled_in', False)
            
            if registration_fee > 0 and not registration_rolled_in:
                # Registration is separate - add to payment schedule
                schedule_data.append([
                    'Registration',
                    'Due at signing',
                    f"${registration_fee:,.2f}"
                ])
            
            # Add regular payment schedule
            payment_schedule = contract_terms.get('payment_schedule', [])
            for payment in payment_schedule:
                schedule_data.append([
                    str(payment.get('payment_number', '')),
                    payment.get('due_date', ''),
                    f"${payment.get('amount', 0):,.2f}"
                ])
            
            schedule_table = Table(schedule_data, colWidths=[1*inch, 2.5*inch, 2.5*inch])
            schedule_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ]))
            
            story.append(schedule_table)
            story.append(Spacer(1, 10))
            
            # Important notes
            story.append(Paragraph("IMPORTANT NOTES:", payment_header_style))
            notes = [
                "• Late payments may incur additional fees",
                "• Payment method changes must be submitted in writing 30 days in advance",
                "• For questions regarding billing, contact the financial office",
                "• This contract is binding for the full academic year"
            ]
            
            for note in notes:
                story.append(Paragraph(note, body_style))
            
            # Build the PDF
            doc.build(story)
            
            # Get the PDF content
            pdf_content = buffer.getvalue()
            buffer.close()
            
            try:
                current_app.logger.info(f"✅ Generated comprehensive tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            except:
                # Fallback if current_app is not available
                print(f"✅ Generated comprehensive tuition contract PDF for student {student.id} ({len(pdf_content)} bytes)")
            return pdf_content
            
        except Exception as e:
            try:
                current_app.logger.error(f"❌ Error generating comprehensive tuition contract PDF: {str(e)}")
            except:
                # Fallback if current_app is not available
                print(f"❌ Error generating comprehensive tuition contract PDF: {str(e)}")
            raise e


