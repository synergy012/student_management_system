"""
Report Service for Student Management System
Handles report generation, filtering, and export functionality
"""

import os
import csv
import json
import time
from datetime import datetime, date
from io import StringIO, BytesIO
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
from flask import current_app
from sqlalchemy import text, and_, or_, desc, asc
from sqlalchemy.orm import aliased

from models import (
    db, Student, Application, ReportTemplate, ReportExecution, ReportField,
    TuitionRecord, AcademicYear, BedAssignment, Bed, Room, Dormitory,
    KollelStudent, KollelStipend
)

# For PDF generation
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: ReportLab not installed. PDF export will not be available.")

class ReportService:
    """Main service class for report generation and management"""
    
    def __init__(self):
        self.report_types = {
            'students': {
                'name': 'Student Reports',
                'description': 'Reports on student data, admissions, and enrollment',
                'base_model': Student,
                'default_fields': ['student_name', 'division', 'status', 'email', 'phone_number']
            },
            'applications': {
                'name': 'Application Reports',
                'description': 'Reports on application submissions and processing',
                'base_model': Application,
                'default_fields': ['student_name', 'division', 'status', 'submitted_at', 'processed_at']
            },
            'financial': {
                'name': 'Financial Reports',
                'description': 'Tuition and financial aid reports',
                'base_model': TuitionRecord,
                'default_fields': ['student_name', 'academic_year', 'total_tuition', 'payments_received']
            },
            'dormitory': {
                'name': 'Dormitory Reports',
                'description': 'Housing and bed assignment reports',
                'base_model': BedAssignment,
                'default_fields': ['student_name', 'bed_name', 'dormitory_name', 'start_date', 'end_date']
            },
            'kollel': {
                'name': 'Kollel Reports',
                'description': 'Kollel student and stipend reports',
                'base_model': KollelStudent,
                'default_fields': ['student_name', 'status', 'monthly_stipend', 'iyun_chaburah']
            }
        }
    
    def initialize_report_fields(self):
        """Initialize default report fields for all report types"""
        try:
            # Clear existing fields (for development/testing)
            ReportField.query.delete()
            
            # Student Report Fields
            student_fields = [
                ('id', 'Student ID', 'number', 'students', 'id', False, False),
                ('student_name', 'Full Name', 'string', 'students', 'student_name', True, False),
                ('division', 'Division', 'string', 'students', 'division', True, True),
                ('status', 'Status', 'string', 'students', 'status', True, True),
                ('email', 'Email Address', 'string', 'students', 'email', True, False),
                ('phone_number', 'Phone', 'string', 'students', 'phone_number', True, False),
                ('date_of_birth', 'Date of Birth', 'date', 'students', 'date_of_birth', True, False),
                ('address', 'Address', 'string', 'students', 'address', False, False),
                ('city', 'City', 'string', 'students', 'city', True, True),
                ('state', 'State', 'string', 'students', 'state', True, True),
                ('zip_code', 'ZIP Code', 'string', 'students', 'zip_code', True, False),
                ('country', 'Country', 'string', 'students', 'country', True, True),
                ('emergency_contact_name', 'Emergency Contact', 'string', 'students', 'emergency_contact_name', False, False),
                ('dormitory_meals_option', 'Meals Option', 'string', 'students', 'dormitory_meals_option', True, True),
                ('accepted_date', 'Acceptance Date', 'date', 'students', 'accepted_date', True, False),
                ('graduation_date', 'Graduation Date', 'date', 'students', 'graduation_date', True, False),
            ]
            
            # Application Report Fields
            application_fields = [
                ('id', 'Application ID', 'number', 'students', 'id', False, False),
                ('student_name', 'Student Name', 'string', 'students', 'student_name', True, False),
                ('division', 'Division', 'string', 'students', 'division', True, True),
                ('status', 'Status', 'string', 'students', 'status', True, True),
                ('submitted_at', 'Submitted Date', 'date', 'students', 'submitted_at', True, False),
                ('processed_at', 'Processed Date', 'date', 'students', 'processed_at', True, False),
                ('processed_by', 'Processed By', 'string', 'students', 'processed_by', True, False),
                ('form_data', 'Form Data', 'json', 'students', 'form_data', False, False),
            ]
            
            # Financial Report Fields  
            financial_fields = [
                ('student_name', 'Student Name', 'string', 'tuition_records', 'student_name', True, False),
                ('academic_year', 'Academic Year', 'string', 'tuition_records', 'academic_year_name', True, True),
                ('total_tuition', 'Total Tuition', 'number', 'tuition_records', 'total_tuition', True, False),
                ('payments_received', 'Payments Received', 'number', 'tuition_records', 'payments_received', True, False),
                ('balance_due', 'Balance Due', 'number', 'tuition_records', 'balance_due', True, False),
                ('dormitory_cost', 'Dormitory Cost', 'number', 'tuition_records', 'dormitory_cost', True, False),
                ('meals_cost', 'Meals Cost', 'number', 'tuition_records', 'meals_cost', True, False),
                ('iyun_chaburah', 'Iyun Chaburah', 'number', 'tuition_records', 'iyun_chaburah', True, False),
                ('contract_signed', 'Contract Signed', 'boolean', 'tuition_records', 'contract_signed', True, True),
                ('contract_signed_date', 'Contract Date', 'date', 'tuition_records', 'contract_signed_date', True, False),
            ]
            
            # Dormitory Report Fields
            dormitory_fields = [
                ('student_name', 'Student Name', 'string', 'bed_assignments', 'student_name', True, False),
                ('bed_name', 'Bed', 'string', 'bed_assignments', 'bed_name', True, False),
                ('dormitory_name', 'Dormitory', 'string', 'bed_assignments', 'dormitory_name', True, True),
                ('room_number', 'Room', 'string', 'bed_assignments', 'room_number', True, True),
                ('start_date', 'Start Date', 'date', 'bed_assignments', 'start_date', True, False),
                ('end_date', 'End Date', 'date', 'bed_assignments', 'end_date', True, False),
                ('is_active', 'Active Assignment', 'boolean', 'bed_assignments', 'is_active', True, True),
                ('assigned_by', 'Assigned By', 'string', 'bed_assignments', 'assigned_by', True, False),
                ('notes', 'Notes', 'string', 'bed_assignments', 'notes', False, False),
            ]
            
            # Kollel Report Fields
            kollel_fields = [
                ('student_name', 'Student Name', 'string', 'kollel_students', 'student_name', True, False),
                ('status', 'Status', 'string', 'kollel_students', 'status', True, True),
                ('start_date', 'Start Date', 'date', 'kollel_students', 'start_date', True, False),
                ('end_date', 'End Date', 'date', 'kollel_students', 'end_date', True, False),
                ('monthly_stipend', 'Monthly Stipend', 'number', 'kollel_students', 'monthly_stipend', True, False),
                ('iyun_chaburah', 'Iyun Chaburah', 'number', 'kollel_students', 'iyun_chaburah', True, False),
                ('notes', 'Notes', 'string', 'kollel_students', 'notes', False, False),
            ]
            
            # Add fields to database
            all_fields = [
                ('students', student_fields),
                ('applications', application_fields), 
                ('financial', financial_fields),
                ('dormitory', dormitory_fields),
                ('kollel', kollel_fields)
            ]
            
            sort_order = 0
            for report_type, fields in all_fields:
                for field_name, display_name, field_type, table_name, column_name, is_groupable, is_aggregatable in fields:
                    report_field = ReportField(
                        report_type=report_type,
                        field_name=field_name,
                        display_name=display_name,
                        field_type=field_type,
                        table_name=table_name,
                        column_name=column_name,
                        is_filterable=True,
                        is_sortable=True,
                        is_groupable=is_groupable,
                        is_aggregatable=is_aggregatable,
                        sort_order=sort_order,
                        category='Basic Info'
                    )
                    db.session.add(report_field)
                    sort_order += 1
            
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error initializing report fields: {str(e)}")
            return False
    
    def get_available_fields(self, report_type: str) -> List[Dict]:
        """Get available fields for a report type"""
        fields = ReportField.query.filter_by(
            report_type=report_type,
            is_active=True
        ).order_by(ReportField.sort_order).all()
        
        return [field.to_dict() for field in fields]
    
    def build_query(self, report_type: str, fields: List[str], filters: Dict = None, sorting: Dict = None) -> Tuple[Any, int]:
        """Build SQLAlchemy query based on report configuration"""
        
        if report_type == 'students':
            return self._build_students_query(fields, filters, sorting)
        elif report_type == 'applications':
            return self._build_applications_query(fields, filters, sorting)
        elif report_type == 'financial':
            return self._build_financial_query(fields, filters, sorting)
        elif report_type == 'dormitory':
            return self._build_dormitory_query(fields, filters, sorting)
        elif report_type == 'kollel':
            return self._build_kollel_query(fields, filters, sorting)
        else:
            raise ValueError(f"Unsupported report type: {report_type}")
    
    def _build_students_query(self, fields: List[str], filters: Dict = None, sorting: Dict = None):
        """Build query for student reports"""
        query = db.session.query(Student)
        total_count = query.count()
        
        # Apply filters
        if filters:
            query = self._apply_filters(query, Student, filters)
        
        # Apply sorting
        if sorting:
            query = self._apply_sorting(query, Student, sorting)
        
        return query, total_count
    
    def _build_applications_query(self, fields: List[str], filters: Dict = None, sorting: Dict = None):
        """Build query for application reports"""
        # Applications are stored as Student records with submitted_at
        query = db.session.query(Student).filter(Student.submitted_at.isnot(None))
        total_count = query.count()
        
        if filters:
            query = self._apply_filters(query, Student, filters)
        
        if sorting:
            query = self._apply_sorting(query, Student, sorting)
        
        return query, total_count
    
    def _build_financial_query(self, fields: List[str], filters: Dict = None, sorting: Dict = None):
        """Build query for financial reports"""
        query = db.session.query(TuitionRecord).join(Student).join(AcademicYear)
        total_count = query.count()
        
        if filters:
            query = self._apply_filters(query, TuitionRecord, filters, Student)
        
        if sorting:
            query = self._apply_sorting(query, TuitionRecord, sorting)
        
        return query, total_count
    
    def _build_dormitory_query(self, fields: List[str], filters: Dict = None, sorting: Dict = None):
        """Build query for dormitory reports"""
        query = db.session.query(BedAssignment).join(Student).join(Bed).join(Room).join(Dormitory)
        total_count = query.count()
        
        if filters:
            query = self._apply_filters(query, BedAssignment, filters, Student, Bed, Room, Dormitory)
        
        if sorting:
            query = self._apply_sorting(query, BedAssignment, sorting)
        
        return query, total_count
    
    def _build_kollel_query(self, fields: List[str], filters: Dict = None, sorting: Dict = None):
        """Build query for kollel reports"""
        query = db.session.query(KollelStudent).join(Student)
        total_count = query.count()
        
        if filters:
            query = self._apply_filters(query, KollelStudent, filters, Student)
        
        if sorting:
            query = self._apply_sorting(query, KollelStudent, sorting)
        
        return query, total_count
    
    def _apply_filters(self, query, primary_model, filters: Dict, *additional_models):
        """Apply filters to query"""
        if not filters:
            return query
        
        all_models = [primary_model] + list(additional_models)
        
        for field_name, filter_config in filters.items():
            if not filter_config or not filter_config.get('value'):
                continue
            
            filter_type = filter_config.get('type', 'equals')
            filter_value = filter_config.get('value')
            
            # Find the appropriate column
            column = None
            for model in all_models:
                if hasattr(model, field_name):
                    column = getattr(model, field_name)
                    break
            
            if column is None:
                continue
            
            # Apply filter based on type
            if filter_type == 'equals':
                query = query.filter(column == filter_value)
            elif filter_type == 'contains':
                query = query.filter(column.contains(filter_value))
            elif filter_type == 'starts_with':
                query = query.filter(column.startswith(filter_value))
            elif filter_type == 'greater_than':
                query = query.filter(column > filter_value)
            elif filter_type == 'less_than':
                query = query.filter(column < filter_value)
            elif filter_type == 'between':
                if isinstance(filter_value, list) and len(filter_value) == 2:
                    query = query.filter(column.between(filter_value[0], filter_value[1]))
            elif filter_type == 'in':
                if isinstance(filter_value, list):
                    query = query.filter(column.in_(filter_value))
            elif filter_type == 'not_null':
                query = query.filter(column.isnot(None))
            elif filter_type == 'is_null':
                query = query.filter(column.is_(None))
        
        return query
    
    def _apply_sorting(self, query, primary_model, sorting: Dict):
        """Apply sorting to query"""
        if not sorting:
            return query
        
        sort_field = sorting.get('field')
        sort_direction = sorting.get('direction', 'asc')
        
        if not sort_field:
            return query
        
        # Find the column
        column = None
        if hasattr(primary_model, sort_field):
            column = getattr(primary_model, sort_field)
        
        if column is None:
            return query
        
        if sort_direction.lower() == 'desc':
            query = query.order_by(desc(column))
        else:
            query = query.order_by(asc(column))
        
        return query
    
    def extract_data(self, query_result, report_type: str, fields: List[str]) -> List[Dict]:
        """Extract data from query result based on specified fields"""
        data = []
        
        for record in query_result:
            row_data = {}
            
            for field_name in fields:
                value = self._extract_field_value(record, field_name, report_type)
                row_data[field_name] = value
            
            data.append(row_data)
        
        return data
    
    def _extract_field_value(self, record, field_name: str, report_type: str):
        """Extract field value from a record"""
        try:
            if report_type == 'students':
                return getattr(record, field_name, None)
            elif report_type == 'applications':
                return getattr(record, field_name, None)
            elif report_type == 'financial':
                if field_name == 'student_name':
                    return record.student.student_name if record.student else None
                elif field_name == 'academic_year':
                    return record.academic_year.year_label if record.academic_year else None
                else:
                    return getattr(record, field_name, None)
            elif report_type == 'dormitory':
                if field_name == 'student_name':
                    return record.student.student_name if record.student else None
                elif field_name == 'bed_name':
                    return record.bed.full_bed_name if record.bed else None
                elif field_name == 'dormitory_name':
                    return record.bed.room.dormitory.name if record.bed and record.bed.room and record.bed.room.dormitory else None
                elif field_name == 'room_number':
                    return record.bed.room.room_number if record.bed and record.bed.room else None
                else:
                    return getattr(record, field_name, None)
            elif report_type == 'kollel':
                if field_name == 'student_name':
                    return record.student.student_name if record.student else None
                else:
                    return getattr(record, field_name, None)
            else:
                return getattr(record, field_name, None)
        except Exception as e:
            current_app.logger.warning(f"Error extracting field {field_name}: {str(e)}")
            return None
    
    def export_to_csv(self, data: List[Dict], fields: List[str], field_definitions: Dict = None) -> str:
        """Export data to CSV format"""
        output = StringIO()
        
        if not data:
            return ""
        
        # Get field display names
        headers = []
        for field in fields:
            if field_definitions and field in field_definitions:
                headers.append(field_definitions[field].get('display_name', field))
            else:
                headers.append(field.replace('_', ' ').title())
        
        writer = csv.writer(output)
        writer.writerow(headers)
        
        for row in data:
            csv_row = []
            for field in fields:
                value = row.get(field, '')
                
                # Format values for CSV
                if isinstance(value, datetime):
                    value = value.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(value, date):
                    value = value.strftime('%Y-%m-%d')
                elif value is None:
                    value = ''
                elif isinstance(value, bool):
                    value = 'Yes' if value else 'No'
                
                csv_row.append(str(value))
            
            writer.writerow(csv_row)
        
        return output.getvalue()

    def export_to_pdf(self, data: List[Dict], fields: List[str], report_name: str = "Report", 
                     field_definitions: Dict = None) -> bytes:
        """Export data to PDF format"""
        if not PDF_AVAILABLE:
            raise ImportError("ReportLab is required for PDF export")
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        
        # Build content
        content = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=16,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        content.append(Paragraph(report_name, title_style))
        content.append(Spacer(1, 12))
        
        # Add generation info
        info_style = ParagraphStyle(
            'Info',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey
        )
        generation_info = f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>Total Records: {len(data)}"
        content.append(Paragraph(generation_info, info_style))
        content.append(Spacer(1, 20))
        
        if data:
            # Prepare table data
            headers = []
            for field in fields:
                if field_definitions and field in field_definitions:
                    headers.append(field_definitions[field].get('display_name', field))
                else:
                    headers.append(field.replace('_', ' ').title())
            
            table_data = [headers]
            
            for row in data:
                pdf_row = []
                for field in fields:
                    value = row.get(field, '')
                    
                    # Format values for PDF
                    if isinstance(value, datetime):
                        value = value.strftime('%Y-%m-%d')
                    elif isinstance(value, date):
                        value = value.strftime('%Y-%m-%d')
                    elif value is None:
                        value = ''
                    elif isinstance(value, bool):
                        value = 'Yes' if value else 'No'
                    
                    # Truncate long text
                    str_value = str(value)
                    if len(str_value) > 50:
                        str_value = str_value[:47] + "..."
                    
                    pdf_row.append(str_value)
                
                table_data.append(pdf_row)
            
            # Create table
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            content.append(table)
        else:
            content.append(Paragraph("No data available for the selected criteria.", styles['Normal']))
        
        # Build PDF
        doc.build(content)
        buffer.seek(0)
        return buffer.getvalue()

    def generate_report(self, template_id: int = None, report_config: Dict = None, 
                       export_format: str = 'csv', executed_by: str = None) -> Dict:
        """Generate a report from template or configuration"""
        start_time = time.time()
        
        try:
            # Get configuration
            if template_id:
                template = ReportTemplate.query.get_or_404(template_id)
                config = {
                    'name': template.name,
                    'report_type': template.report_type,
                    'fields': template.fields or [],
                    'filters': template.filters or {},
                    'sorting': template.sorting or {}
                }
                template.increment_usage()
            else:
                config = report_config
                template = None
            
            if not config:
                raise ValueError("No report configuration provided")
            
            # Build and execute query
            query, total_count = self.build_query(
                config['report_type'],
                config['fields'],
                config.get('filters'),
                config.get('sorting')
            )
            
            query_results = query.all()
            filtered_count = len(query_results)
            
            # Extract data
            data = self.extract_data(query_results, config['report_type'], config['fields'])
            
            # Get field definitions for formatting
            field_defs = {field.field_name: field.to_dict() 
                         for field in ReportField.query.filter_by(report_type=config['report_type']).all()}
            
            # Export data
            if export_format.lower() == 'pdf':
                file_content = self.export_to_pdf(data, config['fields'], config.get('name', 'Report'), field_defs)
                file_extension = 'pdf'
                content_type = 'application/pdf'
            else:
                file_content = self.export_to_csv(data, config['fields'], field_defs)
                file_extension = 'csv'
                content_type = 'text/csv'
            
            # Save file
            filename = self._generate_filename(config.get('name', 'report'), file_extension)
            file_path = self._save_report_file(filename, file_content, export_format)
            
            execution_time = time.time() - start_time
            
            # Record execution
            execution = ReportExecution(
                template_id=template_id,
                report_name=config.get('name', 'Unnamed Report'),
                report_type=config['report_type'],
                export_format=export_format,
                fields_used=config['fields'],
                filters_used=config.get('filters'),
                sorting_used=config.get('sorting'),
                total_records=total_count,
                filtered_records=filtered_count,
                file_size=len(file_content) if isinstance(file_content, (str, bytes)) else 0,
                file_path=file_path,
                executed_by=executed_by or 'system',
                execution_time=execution_time,
                status='completed'
            )
            
            db.session.add(execution)
            db.session.commit()
            
            return {
                'success': True,
                'execution_id': execution.id,
                'filename': filename,
                'file_path': file_path,
                'content_type': content_type,
                'total_records': total_count,
                'filtered_records': filtered_count,
                'execution_time': execution_time,
                'file_content': file_content
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            # Record failed execution
            if executed_by:
                execution = ReportExecution(
                    template_id=template_id,
                    report_name=config.get('name', 'Failed Report') if config else 'Failed Report',
                    report_type=config.get('report_type', 'unknown') if config else 'unknown',
                    export_format=export_format,
                    executed_by=executed_by,
                    execution_time=execution_time,
                    status='failed',
                    error_message=str(e)
                )
                db.session.add(execution)
                db.session.commit()
            
            current_app.logger.error(f"Report generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'execution_time': execution_time
            }
    
    def _generate_filename(self, report_name: str, extension: str) -> str:
        """Generate a unique filename for the report"""
        # Clean report name
        clean_name = "".join(c for c in report_name if c.isalnum() or c in (' ', '_', '-')).strip()
        clean_name = clean_name.replace(' ', '_')
        
        # Add timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return f"{clean_name}_{timestamp}.{extension}"
    
    def _save_report_file(self, filename: str, content, format_type: str) -> str:
        """Save report file to disk"""
        # Create reports directory if it doesn't exist
        reports_dir = os.path.join(current_app.root_path, 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        
        file_path = os.path.join(reports_dir, filename)
        relative_path = os.path.join('reports', filename)
        
        # Write file
        if format_type.lower() == 'pdf':
            with open(file_path, 'wb') as f:
                f.write(content)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return relative_path

# Create singleton instance
report_service = ReportService() 