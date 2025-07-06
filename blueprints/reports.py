from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import ReportTemplate, ReportExecution, ReportField, db
from utils.decorators import permission_required
from report_service import ReportService
from datetime import datetime
import os

reports = Blueprint('reports', __name__)

@reports.route('/reports')
@login_required
@permission_required('view_students')
def reports_dashboard():
    """Main reports dashboard"""
    return render_template('reports/dashboard.html')

@reports.route('/reports/builder')
@login_required
@permission_required('view_students')
def report_builder():
    """Report builder interface"""
    return render_template('reports/builder.html')

@reports.route('/api/reports/types', methods=['GET'])
@login_required
@permission_required('view_students')
def get_report_types():
    """Get available report types"""
    report_types = [
        {
            'id': 'students',
            'name': 'Students Report',
            'description': 'Comprehensive student information report',
            'icon': 'fas fa-user-graduate'
        },
        {
            'id': 'applications',
            'name': 'Applications Report',
            'description': 'Student applications and admission data',
            'icon': 'fas fa-file-alt'
        },
        {
            'id': 'financial',
            'name': 'Financial Report',
            'description': 'Tuition and financial aid information',
            'icon': 'fas fa-dollar-sign'
        },
        {
            'id': 'dormitory',
            'name': 'Dormitory Report',
            'description': 'Housing assignments and dormitory utilization',
            'icon': 'fas fa-building'
        },
        {
            'id': 'kollel',
            'name': 'Kollel Report',
            'description': 'Kollel students and stipend information',
            'icon': 'fas fa-book'
        }
    ]
    
    return jsonify(report_types)

@reports.route('/api/reports/fields/<report_type>', methods=['GET'])
@login_required
@permission_required('view_students')
def get_report_fields(report_type):
    """Get available fields for a report type"""
    try:
        # Get fields from database
        fields = ReportField.query.filter_by(
            report_type=report_type,
            is_active=True
        ).order_by(ReportField.category, ReportField.display_order).all()
        
        # Group by category
        grouped_fields = {}
        for field in fields:
            category = field.category or 'Other'
            if category not in grouped_fields:
                grouped_fields[category] = []
            
            grouped_fields[category].append({
                'id': field.id,
                'field_name': field.field_name,
                'display_name': field.display_name,
                'data_type': field.data_type,
                'is_default': field.is_default,
                'can_filter': field.can_filter,
                'can_sort': field.can_sort
            })
        
        return jsonify(grouped_fields)
    except Exception as e:
        current_app.logger.error(f"Error getting report fields: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/templates', methods=['GET', 'POST'])
@login_required
@permission_required('view_students')
def manage_report_templates():
    """Get user's report templates or create a new one"""
    if request.method == 'GET':
        # Get templates accessible to user
        templates = ReportTemplate.query.filter(
            db.or_(
                ReportTemplate.created_by == current_user.id,
                ReportTemplate.is_public == True
            )
        ).order_by(ReportTemplate.last_used_at.desc()).all()
        
        return jsonify([{
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'report_type': t.report_type,
            'is_public': t.is_public,
            'created_by': t.created_by,
            'created_at': t.created_at.isoformat(),
            'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
            'use_count': t.use_count
        } for t in templates])
    
    else:  # POST
        try:
            data = request.get_json()
            
            template = ReportTemplate(
                name=data['name'],
                description=data.get('description', ''),
                report_type=data['report_type'],
                field_selection=data['field_selection'],
                filters=data.get('filters', {}),
                sorting=data.get('sorting', []),
                grouping=data.get('grouping', []),
                is_public=data.get('is_public', False),
                created_by=current_user.id
            )
            
            db.session.add(template)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'template_id': template.id,
                'message': 'Report template saved successfully'
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving report template: {str(e)}")
            return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/templates/<int:template_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@permission_required('view_students')
def manage_report_template(template_id):
    """Get, update or delete a specific report template"""
    template = ReportTemplate.query.get_or_404(template_id)
    
    # Check permissions
    if not template.is_public and template.created_by != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    if request.method == 'GET':
        return jsonify({
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'report_type': template.report_type,
            'field_selection': template.field_selection,
            'filters': template.filters,
            'sorting': template.sorting,
            'grouping': template.grouping,
            'is_public': template.is_public,
            'output_format': template.output_format
        })
    
    elif request.method == 'PUT':
        if template.created_by != current_user.id:
            return jsonify({'error': 'Only the creator can update this template'}), 403
        
        try:
            data = request.get_json()
            
            template.name = data.get('name', template.name)
            template.description = data.get('description', template.description)
            template.field_selection = data.get('field_selection', template.field_selection)
            template.filters = data.get('filters', template.filters)
            template.sorting = data.get('sorting', template.sorting)
            template.grouping = data.get('grouping', template.grouping)
            template.is_public = data.get('is_public', template.is_public)
            template.output_format = data.get('output_format', template.output_format)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Template updated successfully'
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating template: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    else:  # DELETE
        if template.created_by != current_user.id:
            return jsonify({'error': 'Only the creator can delete this template'}), 403
        
        try:
            db.session.delete(template)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Template deleted successfully'
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting template: {str(e)}")
            return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/generate', methods=['POST'])
@login_required
@permission_required('view_students')
def generate_report():
    """Generate a report based on configuration or template"""
    try:
        data = request.get_json()
        
        # Get configuration from template or direct input
        if 'template_id' in data:
            template = ReportTemplate.query.get_or_404(data['template_id'])
            
            # Check access
            if not template.is_public and template.created_by != current_user.id:
                return jsonify({'error': 'Access denied'}), 403
            
            # Update usage stats
            template.use_count += 1
            template.last_used_at = datetime.utcnow()
            
            config = {
                'report_type': template.report_type,
                'field_selection': template.field_selection,
                'filters': template.filters,
                'sorting': template.sorting,
                'grouping': template.grouping,
                'output_format': data.get('output_format', template.output_format)
            }
        else:
            config = data
        
        # Generate the report
        report_service = ReportService()
        file_path, file_name = report_service.generate_report(
            report_type=config['report_type'],
            field_selection=config['field_selection'],
            filters=config.get('filters', {}),
            sorting=config.get('sorting', []),
            grouping=config.get('grouping', []),
            output_format=config.get('output_format', 'csv'),
            user=current_user
        )
        
        # Create execution record
        execution = ReportExecution(
            report_type=config['report_type'],
            configuration=config,
            output_format=config.get('output_format', 'csv'),
            file_path=file_path,
            file_name=file_name,
            executed_by=current_user.id,
            template_id=data.get('template_id')
        )
        
        db.session.add(execution)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'execution_id': execution.id,
            'file_name': file_name,
            'message': 'Report generated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/download/<int:execution_id>')
@login_required
@permission_required('view_students')
def download_report(execution_id):
    """Download a generated report"""
    try:
        execution = ReportExecution.query.get_or_404(execution_id)
        
        # Check if user has access
        if execution.executed_by != current_user.id and not current_user.has_permission('manage_users'):
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not os.path.exists(execution.file_path):
            return jsonify({'error': 'Report file not found'}), 404
        
        # Update download stats
        execution.download_count += 1
        execution.last_downloaded_at = datetime.utcnow()
        db.session.commit()
        
        # Send file
        return send_file(
            execution.file_path,
            as_attachment=True,
            download_name=execution.file_name,
            mimetype='application/pdf' if execution.output_format == 'pdf' else 'text/csv'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/history', methods=['GET'])
@login_required
@permission_required('view_students')
def get_report_history():
    """Get report execution history"""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Build query
        query = ReportExecution.query
        
        # Filter by user unless they can manage users
        if not current_user.has_permission('manage_users'):
            query = query.filter_by(executed_by=current_user.id)
        
        # Apply filters
        report_type = request.args.get('report_type')
        if report_type:
            query = query.filter_by(report_type=report_type)
        
        # Order by execution date
        query = query.order_by(ReportExecution.executed_at.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Format results
        history = []
        for execution in pagination.items:
            history.append({
                'id': execution.id,
                'report_type': execution.report_type,
                'file_name': execution.file_name,
                'output_format': execution.output_format,
                'executed_at': execution.executed_at.isoformat(),
                'executed_by': execution.executed_by,
                'status': execution.status,
                'download_count': execution.download_count,
                'file_exists': os.path.exists(execution.file_path) if execution.file_path else False
            })
        
        return jsonify({
            'history': history,
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting report history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/preview', methods=['POST'])
@login_required
@permission_required('view_students')
def preview_report():
    """Preview report data without generating file"""
    try:
        data = request.get_json()
        
        # Get configuration
        if 'template_id' in data:
            template = ReportTemplate.query.get_or_404(data['template_id'])
            
            # Check access
            if not template.is_public and template.created_by != current_user.id:
                return jsonify({'error': 'Access denied'}), 403
            
            config = {
                'report_type': template.report_type,
                'field_selection': template.field_selection,
                'filters': template.filters,
                'sorting': template.sorting,
                'grouping': template.grouping
            }
        else:
            config = data
        
        # Get preview data
        report_service = ReportService()
        preview_data = report_service.get_report_data(
            report_type=config['report_type'],
            field_selection=config['field_selection'],
            filters=config.get('filters', {}),
            sorting=config.get('sorting', []),
            limit=20  # Limit preview to 20 rows
        )
        
        return jsonify({
            'success': True,
            'data': preview_data['data'][:20],  # Ensure max 20 rows
            'total_count': preview_data['total_count'],
            'preview_count': min(20, len(preview_data['data']))
        })
        
    except Exception as e:
        current_app.logger.error(f"Error previewing report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@reports.route('/api/reports/initialize-fields', methods=['POST'])
@login_required
@permission_required('manage_users')
def initialize_report_fields():
    """Initialize report field definitions in database"""
    try:
        report_service = ReportService()
        count = report_service.initialize_report_fields()
        
        return jsonify({
            'success': True,
            'message': f'Initialized {count} report fields'
        })
    except Exception as e:
        current_app.logger.error(f"Error initializing report fields: {str(e)}")
        return jsonify({'error': str(e)}), 500 