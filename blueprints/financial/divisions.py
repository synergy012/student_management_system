from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import (DivisionFinancialConfig, TuitionContract, FinancialAidApplication, 
                   AcademicYear, db)
from utils.decorators import permission_required
from datetime import datetime
from decimal import Decimal
import traceback

financial_divisions = Blueprint('financial_divisions', __name__)

@financial_divisions.route('/divisions/<division>/config')
@login_required
@permission_required('manage_users')
def division_financial_config(division):
    """Configure financial settings for a division"""
    try:
        # Get or create config
        config = DivisionFinancialConfig.query.filter_by(division=division).first()
        if not config:
            config = DivisionFinancialConfig(
                division=division,
                base_tuition_amount=Decimal('25000'),
                payment_plans_available=['Annual', 'Semester', 'Monthly'],
                late_fee_policy={'amount': 50, 'percentage': 1.5, 'grace_days': 10}
            )
            db.session.add(config)
            db.session.commit()
        
        return render_template('financial/division_config.html',
                             division=division,
                             config=config)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division config: {str(e)}")
        flash('Error loading configuration', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial_divisions.route('/api/divisions/<division>/config/update', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_division_financial_config(division):
    """Update financial configuration for a division"""
    try:
        config = DivisionFinancialConfig.query.filter_by(division=division).first()
        if not config:
            return jsonify({'error': 'Configuration not found'}), 404
        
        data = request.get_json()
        
        # Update config fields
        if 'base_tuition_amount' in data:
            config.base_tuition_amount = Decimal(str(data['base_tuition_amount']))
        if 'aid_application_deadline' in data:
            config.aid_application_deadline = datetime.strptime(data['aid_application_deadline'], '%Y-%m-%d').date()
        if 'aid_application_requirements' in data:
            config.aid_application_requirements = data['aid_application_requirements']
        if 'payment_plans_available' in data:
            config.payment_plans_available = data['payment_plans_available']
        if 'late_fee_policy' in data:
            config.late_fee_policy = data['late_fee_policy']
        if 'opensign_template_id' in data:
            config.opensign_template_id = data['opensign_template_id']
        if 'opensign_folder_id' in data:
            config.opensign_folder_id = data['opensign_folder_id']
        if 'contract_terms_path' in data:
            config.contract_terms_path = data['contract_terms_path']
        if 'letterhead_path' in data:
            config.letterhead_path = data['letterhead_path']
        if 'logo_path' in data:
            config.logo_path = data['logo_path']
        
        config.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating division config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_divisions.route('/divisions/<division>/tuition-contracts')
@login_required
@permission_required('view_students')
def division_tuition_contracts(division):
    """Display tuition contracts for a specific division"""
    try:
        # Get academic year
        academic_year_id = request.args.get('academic_year_id')
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if not academic_year:
            flash('No active academic year found', 'error')
            return redirect(url_for('financial.financial_dashboard'))
        
        # Get all contracts for this division and year
        contracts = TuitionContract.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).order_by(TuitionContract.contract_date.desc()).all()
        
        # Get academic years for selector
        all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('financial/division_tuition_contracts.html',
                             division=division,
                             contracts=contracts,
                             academic_year=academic_year,
                             all_academic_years=all_academic_years)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division tuition contracts: {str(e)}")
        flash('Error loading tuition contracts', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial_divisions.route('/api/divisions/<division>/config', methods=['GET'])
@login_required
@permission_required('view_students')
def get_division_financial_config(division):
    """Get financial configuration for a division"""
    try:
        config = DivisionFinancialConfig.query.filter_by(division=division).first()
        
        if not config:
            # Return default configuration
            return jsonify({
                'division': division,
                'base_tuition_amount': 25000,
                'payment_plans_available': ['Annual', 'Semester', 'Monthly'],
                'late_fee_policy': {'amount': 50, 'percentage': 1.5, 'grace_days': 10},
                'opensign_template_id': None,
                'opensign_folder_id': None,
                'contract_terms_path': None,
                'letterhead_path': None,
                'logo_path': None,
                'aid_application_deadline': None,
                'aid_application_requirements': None
            })
        
        return jsonify({
            'division': config.division,
            'base_tuition_amount': float(config.base_tuition_amount) if config.base_tuition_amount else 25000,
            'payment_plans_available': config.payment_plans_available or ['Annual', 'Semester', 'Monthly'],
            'late_fee_policy': config.late_fee_policy or {'amount': 50, 'percentage': 1.5, 'grace_days': 10},
            'opensign_template_id': config.opensign_template_id,
            'opensign_folder_id': config.opensign_folder_id,
            'contract_terms_path': config.contract_terms_path,
            'letterhead_path': config.letterhead_path,
            'logo_path': config.logo_path,
            'aid_application_deadline': config.aid_application_deadline.isoformat() if config.aid_application_deadline else None,
            'aid_application_requirements': config.aid_application_requirements,
            'created_at': config.created_at.isoformat() if config.created_at else None,
            'updated_at': config.updated_at.isoformat() if config.updated_at else None
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting division config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_divisions.route('/api/divisions/<division>/config/create', methods=['POST'])
@login_required
@permission_required('manage_users')
def create_division_financial_config(division):
    """Create a new financial configuration for a division"""
    try:
        # Check if config already exists
        existing_config = DivisionFinancialConfig.query.filter_by(division=division).first()
        if existing_config:
            return jsonify({'error': 'Configuration already exists for this division'}), 400
        
        data = request.get_json()
        
        # Create new config with defaults
        config = DivisionFinancialConfig(
            division=division,
            base_tuition_amount=Decimal(str(data.get('base_tuition_amount', 25000))),
            payment_plans_available=data.get('payment_plans_available', ['Annual', 'Semester', 'Monthly']),
            late_fee_policy=data.get('late_fee_policy', {'amount': 50, 'percentage': 1.5, 'grace_days': 10}),
            opensign_template_id=data.get('opensign_template_id'),
            opensign_folder_id=data.get('opensign_folder_id'),
            contract_terms_path=data.get('contract_terms_path'),
            letterhead_path=data.get('letterhead_path'),
            logo_path=data.get('logo_path'),
            aid_application_requirements=data.get('aid_application_requirements'),
            created_at=datetime.utcnow()
        )
        
        if data.get('aid_application_deadline'):
            config.aid_application_deadline = datetime.strptime(data['aid_application_deadline'], '%Y-%m-%d').date()
        
        db.session.add(config)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Division configuration created successfully',
            'config_id': config.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating division config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_divisions.route('/api/divisions/<division>/stats', methods=['GET'])
@login_required
@permission_required('view_students')
def get_division_financial_stats(division):
    """Get financial statistics for a division"""
    try:
        # Get academic year
        academic_year_id = request.args.get('academic_year_id')
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if not academic_year:
            return jsonify({'error': 'No academic year found'}), 404
        
        # Use the service to get statistics
        from services.financial_service import FinancialService
        financial_service = FinancialService()
        stats = financial_service.get_division_financial_stats(division, academic_year.id)
        
        # Add academic year info to the response
        stats['academic_year'] = academic_year.year_label
        
        return jsonify(stats)
        
    except Exception as e:
        current_app.logger.error(f"Error getting division stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_divisions.route('/api/divisions/<division>/export', methods=['GET'])
@login_required
@permission_required('view_students')
def export_division_financial_data(division):
    """Export financial data for a division"""
    try:
        # Get academic year
        academic_year_id = request.args.get('academic_year_id')
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if not academic_year:
            return jsonify({'error': 'No academic year found'}), 404
        
        export_type = request.args.get('type', 'csv')  # csv or excel
        
        # Get contracts for division
        contracts = TuitionContract.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).all()
        
        # Get financial aid applications
        aid_applications = FinancialAidApplication.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).all()
        
        # Prepare data for export
        export_data = {
            'contracts': [
                {
                    'student_name': contract.student.student_name,
                    'tuition_amount': float(contract.tuition_amount),
                    'final_amount': float(contract.final_tuition_amount),
                    'contract_status': contract.contract_status,
                    'signing_status': contract.opensign_status,
                    'generated_date': contract.generated_date.isoformat() if contract.generated_date else None,
                    'sent_date': contract.sent_date.isoformat() if contract.sent_date else None
                }
                for contract in contracts
            ],
            'financial_aid': [
                {
                    'student_name': app.student.student_name,
                    'household_income': float(app.household_income or 0),
                    'requested_amount': float(app.requested_aid_amount or 0),
                    'award_amount': float(app.award_amount or 0),
                    'application_status': app.application_status,
                    'application_date': app.application_date.isoformat() if app.application_date else None,
                    'reviewed_date': app.reviewed_date.isoformat() if app.reviewed_date else None
                }
                for app in aid_applications
            ]
        }
        
        if export_type == 'excel':
            # Create Excel file (would need pandas/openpyxl)
            # For now, return JSON with instructions
            return jsonify({
                'success': True,
                'message': 'Excel export would be generated here',
                'data': export_data
            })
        else:
            # Return CSV data
            return jsonify({
                'success': True,
                'format': 'csv',
                'data': export_data
            })
        
    except Exception as e:
        current_app.logger.error(f"Error exporting division data: {str(e)}")
        return jsonify({'error': str(e)}), 500
