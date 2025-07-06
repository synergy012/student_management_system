from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import (Student, TuitionRecord, AcademicYear, db, FinancialRecord, 
                   StudentTuitionComponent, TuitionComponent, DivisionTuitionComponent, 
                   StudentYearlyTracking, Application)
from utils.decorators import permission_required
from utils.helpers import parse_decimal
from datetime import datetime, date
from decimal import Decimal
import traceback

financial_tuition = Blueprint('financial_tuition', __name__)

# This function has been moved to FinancialService.determine_tuition_type()
# Import and use the service instead

@financial_tuition.route('/api/students/<student_id>/update-financial', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_student_financial(student_id):
    """Update student financial information."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        
        # Update financial fields
        if 'tuition_amount' in data:
            student.tuition_amount = parse_decimal(data['tuition_amount'])
        
        if 'tuition_amount_paid' in data:
            student.tuition_amount_paid = parse_decimal(data['tuition_amount_paid'])
        
        if 'scholarship_amount' in data:
            student.scholarship_amount = parse_decimal(data['scholarship_amount'])
        
        if 'tuition_payment_plan' in data:
            student.tuition_payment_plan = data['tuition_payment_plan']
        
        if 'financial_aid_status' in data:
            student.financial_aid_status = data['financial_aid_status']
        
        if 'tuition_notes' in data:
            student.tuition_notes = data['tuition_notes']
        
        # Update tuition record for current year if exists
        if 'current_year_id' in data and 'current_year_amount' in data:
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=data['current_year_id']
            ).first()
            
            if tuition_record:
                tuition_record.tuition_amount = parse_decimal(data['current_year_amount'])
                if 'current_year_paid' in data:
                    tuition_record.amount_paid = parse_decimal(data['current_year_paid'])
                if 'current_year_plan' in data:
                    tuition_record.payment_plan = data['current_year_plan']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Financial information updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating financial info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/change-academic-year', methods=['POST'])
@login_required
@permission_required('edit_students')
def change_academic_year(student_id):
    """Change the selected academic year for student financial view."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        # Get the selected academic year
        selected_year = AcademicYear.query.filter_by(id=academic_year_id).first()
        if not selected_year:
            return jsonify({'error': 'Academic year not found'}), 404
        
        # Get tuition record for the selected year
        tuition_record = None
        try:
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition record for year change: {str(e)}")
        
        # Get tuition history
        tuition_history = []
        try:
            tuition_history = TuitionRecord.query.filter_by(student_id=student_id).order_by(TuitionRecord.academic_year_id.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition history for year change: {str(e)}")
        
        # Calculate totals with error handling
        total_tuition = 0
        total_paid = 0
        try:
            total_tuition = sum(record.tuition_amount for record in tuition_history if record.tuition_amount)
            total_paid = sum(record.amount_paid for record in tuition_history if record.amount_paid)
        except Exception as e:
            current_app.logger.error(f"Error calculating totals for year change: {str(e)}")
        
        total_balance = total_tuition - total_paid
        
        # Safely build the response with error handling
        try:
            response_data = {
                'success': True,
                'selected_year': {
                    'id': selected_year.id,
                    'year_label': selected_year.year_label,
                    'is_active': selected_year.is_active,
                    'is_current': selected_year.is_current,
                    'status_color': getattr(selected_year, 'status_color', 'secondary'),
                    'status_badge': getattr(selected_year, 'status_badge', 'Unknown')
                },
                'tuition_record': None,
                'tuition_history': [],
                'totals': {
                    'total_tuition': float(total_tuition),
                    'total_paid': float(total_paid),
                    'total_balance': float(total_balance)
                }
            }
            
            # Safely add tuition record data
            if tuition_record:
                try:
                    response_data['tuition_record'] = {
                        'id': tuition_record.id,
                        'tuition_determination': float(tuition_record.tuition_determination) if tuition_record.tuition_determination else None,
                        'tuition_determination_notes': tuition_record.tuition_determination_notes if tuition_record else None,
                        'financial_aid_type': tuition_record.financial_aid_type if tuition_record else None,
                        'financial_aid_app_sent': tuition_record.financial_aid_app_sent if tuition_record else False,
                        'financial_aid_app_received': tuition_record.financial_aid_app_received if tuition_record else False,
                        'contract_status': tuition_record.contract_status if tuition_record else None,
                        'payment_status': tuition_record.payment_status if tuition_record else None,
                        'payment_plan': tuition_record.payment_plan if tuition_record else None,
                        'amount_paid': float(tuition_record.amount_paid) if tuition_record and tuition_record.amount_paid else 0,
                        'opensign_document_id': tuition_record.opensign_document_id if tuition_record else None
                    }
                except Exception as e:
                    current_app.logger.error(f"Error processing tuition record data: {str(e)}")
                    response_data['tuition_record'] = None
            
            # Safely add tuition history data
            try:
                response_data['tuition_history'] = [
                    {
                        'academic_year_id': record.academic_year_id,
                        'academic_year': {
                            'year_label': record.academic_year.year_label if record.academic_year else 'Unknown',
                            'status_color': getattr(record.academic_year, 'status_color', 'secondary') if record.academic_year else 'secondary',
                            'status_badge': getattr(record.academic_year, 'status_badge', 'Unknown') if record.academic_year else 'Unknown'
                        },
                        'tuition_determination': float(record.tuition_determination) if record.tuition_determination else None,
                        'contract_status': record.contract_status or 'Unknown',
                        'payment_status': record.payment_status or 'Unknown',
                        'payment_status_color': getattr(record, 'payment_status_color', 'secondary'),
                        'matriculation_status_for_year': getattr(record, 'matriculation_status_for_year', None)
                    } 
                    for record in tuition_history
                ]
            except Exception as e:
                current_app.logger.error(f"Error processing tuition history data: {str(e)}")
                response_data['tuition_history'] = []
            
            return jsonify(response_data)
            
        except Exception as e:
            current_app.logger.error(f"Error building response data: {str(e)}")
            return jsonify({'error': 'Error processing data'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error changing academic year for student {student_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/financial-info')
@login_required
@permission_required('edit_students')
def get_student_financial_info(student_id):
    """Get student financial information for API calls."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Handle potential UTF-8 encoding issues in student data
        try:
            student_name = student.student_name or f"{student.student_first_name or ''} {student.student_last_name or ''}".strip()
            student_email = student.email or ""
            student_phone = student.phone_number or ""
            student_division = student.division or ""
        except UnicodeDecodeError as e:
            current_app.logger.error(f"Unicode decode error for student {student_id}: {str(e)}")
            student_name = f"Student {student_id[:8]}"
            student_email = ""
            student_phone = ""
            student_division = ""
        
        # Get all academic years
        try:
            academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading academic years: {str(e)}")
            academic_years = []
        
        # Get current/active academic year
        selected_year = None
        try:
            selected_year = AcademicYear.query.filter_by(is_active=True).first()
            if not selected_year:
                selected_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
        except Exception as e:
            current_app.logger.error(f"Error loading selected year: {str(e)}")
        
        # Get tuition record for selected year
        tuition_record = None
        if selected_year:
            try:
                tuition_record = TuitionRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=selected_year.id
                ).first()
            except Exception as e:
                current_app.logger.error(f"Error loading tuition record: {str(e)}")
        
        # Get tuition history
        tuition_history = []
        try:
            tuition_history = TuitionRecord.query.filter_by(student_id=student_id).order_by(TuitionRecord.academic_year_id.desc()).all()
        except Exception as e:
            current_app.logger.error(f"Error loading tuition history: {str(e)}")
        
        # Calculate totals with error handling
        total_tuition = 0
        total_paid = 0
        try:
            total_tuition = sum(record.tuition_amount for record in tuition_history if record.tuition_amount)
            total_paid = sum(record.amount_paid for record in tuition_history if record.amount_paid)
        except Exception as e:
            current_app.logger.error(f"Error calculating totals: {str(e)}")
        
        total_balance = total_tuition - total_paid
        
        # Safely build the response
        try:
            response_data = {
                'student': {
                    'id': student.id,
                    'student_name': student_name,
                    'email': student_email,
                    'phone_number': student_phone,
                    'division': student_division,
                    'status': getattr(student, 'status', 'Unknown'),
                    'status_color': getattr(student, 'status_color', 'secondary')
                },
                'academic_years': [
                    {
                        'id': year.id,
                        'year_label': year.year_label,
                        'is_active': year.is_active,
                        'is_current': year.is_current,
                        'status_color': getattr(year, 'status_color', 'secondary'),
                        'status_badge': getattr(year, 'status_badge', 'Unknown')
                    } for year in academic_years
                ],
                'selected_year': {
                    'id': selected_year.id,
                    'year_label': selected_year.year_label,
                    'is_active': selected_year.is_active,
                    'is_current': selected_year.is_current,
                    'status_color': getattr(selected_year, 'status_color', 'secondary'),
                    'status_badge': getattr(selected_year, 'status_badge', 'Unknown')
                } if selected_year else None,
                'tuition_record': None,
                'tuition_history': [],
                'totals': {
                    'total_tuition': float(total_tuition),
                    'total_paid': float(total_paid),
                    'total_balance': float(total_balance)
                }
            }
            
            # Safely add tuition record data
            if tuition_record:
                try:
                    response_data['tuition_record'] = {
                        'id': tuition_record.id,
                        'tuition_determination': float(tuition_record.tuition_determination) if tuition_record.tuition_determination else None,
                        'tuition_determination_notes': tuition_record.tuition_determination_notes if tuition_record else None,
                        'financial_aid_type': tuition_record.financial_aid_type if tuition_record else None,
                        'financial_aid_app_sent': tuition_record.financial_aid_app_sent if tuition_record else False,
                        'financial_aid_app_received': tuition_record.financial_aid_app_received if tuition_record else False,
                        'contract_status': tuition_record.contract_status if tuition_record else None,
                        'payment_status': tuition_record.payment_status if tuition_record else None,
                        'payment_plan': tuition_record.payment_plan if tuition_record else None,
                        'amount_paid': float(tuition_record.amount_paid) if tuition_record and tuition_record.amount_paid else 0,
                        'opensign_document_id': tuition_record.opensign_document_id if tuition_record else None
                    }
                except Exception as e:
                    current_app.logger.error(f"Error processing tuition record data: {str(e)}")
                    response_data['tuition_record'] = None
            
            # Safely add tuition history data
            try:
                response_data['tuition_history'] = [
                    {
                        'academic_year_id': record.academic_year_id,
                        'academic_year': {
                            'year_label': record.academic_year.year_label if record.academic_year else 'Unknown',
                            'status_color': getattr(record.academic_year, 'status_color', 'secondary') if record.academic_year else 'secondary',
                            'status_badge': getattr(record.academic_year, 'status_badge', 'Unknown') if record.academic_year else 'Unknown'
                        },
                        'tuition_determination': float(record.tuition_determination) if record.tuition_determination else None,
                        'contract_status': record.contract_status or 'Unknown',
                        'payment_status': record.payment_status or 'Unknown',
                        'payment_status_color': getattr(record, 'payment_status_color', 'secondary'),
                        'matriculation_status_for_year': getattr(record, 'matriculation_status_for_year', None)
                    } 
                    for record in tuition_history
                ]
            except Exception as e:
                current_app.logger.error(f"Error processing tuition history data: {str(e)}")
                response_data['tuition_history'] = []
            
            return jsonify(response_data)
            
        except Exception as e:
            current_app.logger.error(f"Error building response data: {str(e)}")
            return jsonify({'error': 'Error processing data'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error loading financial info for student {student_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/application-defaults')
@login_required
@permission_required('view_students')
def get_application_defaults(student_id):
    """Get defaults based on application and prior year data"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        defaults = {
            'dormitory_requested': False,
            'meals_requested': False,
            'scholarship_amount_requested': 0,
            'base_tuition': 0
        }
        
        # Check application data
        if student.application:
            # Parse dormitory/meals option
            dorm_meals = student.application.dormitory_meals_option or ''
            defaults['dormitory_requested'] = 'dorm' in dorm_meals.lower() or 'room' in dorm_meals.lower()
            defaults['meals_requested'] = 'meal' in dorm_meals.lower() or 'board' in dorm_meals.lower() or 'food' in dorm_meals.lower()
            defaults['scholarship_amount_requested'] = float(student.application.scholarship_amount_requested or 0)
        
        # Get base tuition for division
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if academic_year:
            tuition_component = TuitionComponent.query.filter_by(name='Tuition', is_active=True).first()
            if tuition_component:
                division_config = DivisionTuitionComponent.query.filter_by(
                    division=student.division,
                    component_id=tuition_component.id,
                    academic_year_id=academic_year.id
                ).first()
                
                if division_config:
                    defaults['base_tuition'] = float(division_config.default_amount)
        
        # Check prior year data for returning students
        if academic_year:
            prior_year = AcademicYear.query.filter(
                AcademicYear.start_date < academic_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            if prior_year:
                prior_components = StudentTuitionComponent.query.filter_by(
                    student_id=student_id,
                    academic_year_id=prior_year.id,
                    is_active=True
                ).join(TuitionComponent).all()
                
                for comp in prior_components:
                    if comp.component.component_type == 'room':
                        defaults['dormitory_requested'] = True
                    elif comp.component.component_type == 'board':
                        defaults['meals_requested'] = True
        
        return jsonify({
            'success': True,
            'defaults': defaults,
            'application_preferences': {
                'dormitory_meals_option': student.application.dormitory_meals_option if student.application else None,
                'financial_aid_request': bool(student.application and student.application.scholarship_amount_requested and student.application.scholarship_amount_requested > 0) if student.application else False
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting application defaults: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/tuition-components/save', methods=['POST'])
@login_required
@permission_required('edit_students')
def save_student_tuition_components(student_id):
    """Save student tuition components for the academic year"""
    try:
        data = request.get_json()
        
        # Get academic year from data or current year
        academic_year_id = data.get('academic_year_id')
        if not academic_year_id:
            # Try to get from academic_year field (year number)
            academic_year_year = data.get('academic_year', datetime.now().year)
            academic_year = AcademicYear.query.filter(
                AcademicYear.start_date <= datetime(academic_year_year, 12, 31),
                AcademicYear.end_date >= datetime(academic_year_year, 1, 1)
            ).first()
            
            if not academic_year:
                academic_year = AcademicYear.query.filter_by(is_active=True).first()
            
            academic_year_id = academic_year.id if academic_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Process each component
        total_amount = 0
        components_summary = []
        dorm_program = False
        meal_program = False
        
        for comp_data in data.get('components', []):
            component_id = comp_data['component_id']
            
            # Get or create student component
            student_comp = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id,
                component_id=component_id
            ).first()
            
            if not student_comp:
                student_comp = StudentTuitionComponent(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    component_id=component_id
                )
                db.session.add(student_comp)
            
            # Update component data  
            student_comp.is_active = comp_data.get('is_enabled', True)
            student_comp.amount = Decimal(str(comp_data.get('amount', 0)))
            student_comp.original_amount = student_comp.amount
            student_comp.discount_percentage = Decimal(str(comp_data.get('discount_percentage', 0)))
            student_comp.updated_by = current_user.username
            
            # Handle proration information  
            proration_percentage = data.get('proration_percentage', 100)
            proration_reason = data.get('proration_reason', '')
            
            # Set proration fields if applicable
            if proration_percentage < 100:
                student_comp.is_prorated = True
                student_comp.proration_percentage = Decimal(str(proration_percentage))
                student_comp.proration_reason = proration_reason
            else:
                student_comp.is_prorated = False
                student_comp.proration_percentage = Decimal('100.00')
                student_comp.proration_reason = ''
            
            # Set discount reason if global discount was applied
            global_discount = data.get('global_discount_percentage', 0)
            if global_discount > 0 and student_comp.discount_percentage > 0:
                student_comp.discount_reason = data.get('global_discount_reason', f'Global {global_discount}% discount applied')
            elif comp_data.get('discount_percentage', 0) > 0 and not student_comp.discount_reason:
                student_comp.discount_reason = 'Individual discount applied'
            
            # Calculate discount amount based on percentage (for reference)
            if student_comp.discount_percentage > 0:
                student_comp.discount_amount = student_comp.amount * (student_comp.discount_percentage / 100)
            else:
                student_comp.discount_amount = Decimal('0')
            
            # Calculate final amount and track components
            final_amount = float(comp_data.get('final_amount', 0))
            if student_comp.is_active:
                total_amount += final_amount
                
                # Track program participation
                component = TuitionComponent.query.get(component_id)
                if component:
                    if component.component_type == 'room':
                        dorm_program = True
                    elif component.component_type == 'board':
                        meal_program = True
                    
                    # Add to components summary
                    components_summary.append({
                        'component_id': component_id,
                        'name': component.name,
                        'component_type': component.component_type,
                        'is_active': True,
                        'original_amount': float(student_comp.original_amount),
                        'discount_percentage': float(student_comp.discount_percentage or 0),
                        'is_prorated': student_comp.is_prorated,
                        'proration_percentage': float(student_comp.proration_percentage or 100),
                        'proration_reason': student_comp.proration_reason or '',
                        'final_amount': final_amount
                    })
        
        # Update or create tuition record
        tuition_record = TuitionRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not tuition_record:
            tuition_record = TuitionRecord(
                student_id=student_id,
                academic_year_id=academic_year_id
            )
            db.session.add(tuition_record)
        
        # Determine tuition type automatically using service
        from services.financial_service import FinancialService
        financial_service = FinancialService()
        tuition_type = financial_service.determine_tuition_type(student_id, academic_year_id)
        
        # Update tuition record
        tuition_record.tuition_determination = Decimal(str(total_amount))
        tuition_record.tuition_amount = Decimal(str(total_amount))
        tuition_record.tuition_type = tuition_type
        tuition_record.updated_by = current_user.username
        tuition_record.updated_at = datetime.utcnow()
        
        # Update student tracking flags
        student.current_year_tuition = Decimal(str(total_amount))
        
        # Also update the FinancialRecord if it exists
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if financial_record:
            financial_record.tuition_type = tuition_type
            financial_record.tuition_amount = Decimal(str(total_amount))
            financial_record.final_tuition_amount = Decimal(str(total_amount))
        
        # Create or update yearly tracking record
        yearly_tracking = StudentYearlyTracking.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not yearly_tracking:
            yearly_tracking = StudentYearlyTracking(
                student_id=student_id,
                academic_year_id=academic_year_id
            )
            db.session.add(yearly_tracking)
        
        # Update tracking data
        yearly_tracking.dorm_program_status = data.get('dorm_program_this_year', dorm_program)
        yearly_tracking.meal_program_status = data.get('meal_program_this_year', meal_program) 
        yearly_tracking.total_tuition_charged = Decimal(str(total_amount))
        yearly_tracking.tuition_components_summary = components_summary
        yearly_tracking.fafsa_required = data.get('fafsa_required', False)
        yearly_tracking.updated_by = current_user.username
        yearly_tracking.updated_at = datetime.utcnow()
        
        # Check if tuition changes require contract regeneration
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if financial_record and financial_record.enhanced_contract_generated:
            current_hash = financial_record.generate_tuition_hash()
            if current_hash != financial_record.contract_generation_hash:
                financial_record.mark_contract_outdated("Tuition components updated")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition components saved successfully',
            'total_amount': total_amount,
            'tuition_type': tuition_type,
            'record_id': tuition_record.id,
            'tracking_id': yearly_tracking.id,
            'program_summary': yearly_tracking.program_summary,
            'contract_status': financial_record.get_contract_status() if financial_record else 'not_generated'
        })
        
    except Exception as e:
        db.session.rollback()
        error_message = str(e)
        current_app.logger.error(f"Error saving tuition components: {error_message}")
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': error_message,
            'message': f'Failed to save tuition components: {error_message}'
        }), 500

@financial_tuition.route('/api/financial/students/<student_id>/set-tuition', methods=['POST'])
@login_required
@permission_required('edit_students')
def set_student_tuition(student_id):
    """Set tuition for a student for the current academic year"""
    try:
        data = request.get_json()
        
        # Get academic year
        academic_year_id = data.get('academic_year_id') or request.args.get('academic_year_id')
        if not academic_year_id:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = academic_year.id if academic_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        # Get or create financial record
        record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not record:
            record = FinancialRecord(
                student_id=student_id,
                academic_year_id=academic_year_id,
                created_by=current_user.username
            )
            db.session.add(record)
        
        # Update tuition information
        record.tuition_type = data.get('tuition_type', 'Full')
        record.tuition_amount = Decimal(str(data.get('tuition_amount', 0)))
        record.discount_percentage = int(data.get('discount_percentage', 0))
        record.discount_reason = data.get('discount_reason')
        record.final_tuition_amount = Decimal(str(data.get('final_tuition_amount', 0)))
        record.fafsa_required = data.get('fafsa_required', False)
        record.updated_by = current_user.username
        record.updated_at = datetime.utcnow()
        
        # Calculate balance
        record.calculate_balance()
        
        # Check if tuition changes require contract regeneration
        if record.enhanced_contract_generated:
            current_hash = record.generate_tuition_hash()
            if current_hash != record.contract_generation_hash:
                record.mark_contract_outdated("Tuition amounts changed")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition set successfully',
            'record_id': record.id,
            'contract_status': record.get_contract_status()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting tuition: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/tuition-history')
@login_required
@permission_required('view_students')
def get_student_tuition_history(student_id):
    """Get complete tuition history with year-over-year tracking"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get all yearly tracking records
        tracking_records = StudentYearlyTracking.query.filter_by(
            student_id=student_id
        ).join(AcademicYear).order_by(AcademicYear.start_date.desc()).all()
        
        history = []
        for tracking in tracking_records:
            # Get tuition record for this year
            tuition_record = TuitionRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=tracking.academic_year_id
            ).first()
            
            # Get component details for this year
            components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=tracking.academic_year_id,
                is_active=True
            ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
            
            component_details = []
            for comp in components:
                component_details.append({
                    'name': comp.component.name,
                    'type': comp.component.component_type,
                    'amount': float(comp.amount),
                    'discount_percentage': float(comp.discount_percentage or 0),
                    'final_amount': float(comp.calculated_amount)
                })
            
            history_item = {
                'academic_year': {
                    'id': tracking.academic_year.id,
                    'year_label': tracking.academic_year.year_label,
                    'start_date': tracking.academic_year.start_date.strftime('%Y-%m-%d'),
                    'end_date': tracking.academic_year.end_date.strftime('%Y-%m-%d')
                },
                'programs': {
                    'dorm_program': tracking.dorm_program_status,
                    'meal_program': tracking.meal_program_status,
                    'program_summary': tracking.program_summary
                },
                'tuition': {
                    'total_charged': float(tracking.total_tuition_charged or 0),
                    'amount_paid': float(tuition_record.amount_paid or 0) if tuition_record else 0,
                    'balance_due': float(tuition_record.balance_due or 0) if tuition_record else 0
                },
                'financial_aid': {
                    'financial_aid_received': float(tracking.financial_aid_received or 0),
                    'scholarship_amount': float(tracking.scholarship_amount or 0),
                    'fafsa_amount': float(tracking.fafsa_amount or 0)
                },
                'components': component_details,
                'enrollment_status': tracking.enrollment_status,
                'notes': tracking.notes,
                'last_updated': tracking.updated_at.strftime('%Y-%m-%d %H:%M') if tracking.updated_at else None
            }
            
            history.append(history_item)
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'student_name': student.student_name,
            'division': student.division,
            'history': history,
            'summary': {
                'total_years': len(history),
                'years_with_dorm': sum(1 for h in history if h['programs']['dorm_program']),
                'years_with_meals': sum(1 for h in history if h['programs']['meal_program']),
                'total_tuition_all_years': sum(h['tuition']['total_charged'] for h in history)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting tuition history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/get-or-create-financial-record', methods=['POST'])
@login_required
@permission_required('edit_students')
def get_or_create_financial_record(student_id):
    """Get or create a financial record for a student and academic year"""
    try:
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID is required'}), 400
        
        # Use the service to get or create the record
        from services.financial_service import FinancialService
        financial_service = FinancialService()
        financial_record = financial_service.get_or_create_financial_record(student_id, academic_year_id)
        
        return jsonify({
            'success': True,
            'financial_record_id': financial_record.id,
            'message': 'Financial record ready'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting/creating financial record: {str(e)}")
        return jsonify({'error': f'Failed to create financial record: {str(e)}'}), 500

@financial_tuition.route('/api/students/<student_id>/financial-action', methods=['POST'])
@login_required
@permission_required('edit_students')
def student_financial_action(student_id):
    """Handle financial actions like payments, adjustments, etc."""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        data = request.get_json()
        action = data.get('action')
        
        if action == 'record_payment':
            amount = parse_decimal(data.get('amount', 0))
            payment_date = datetime.strptime(data['payment_date'], '%Y-%m-%d').date()
            payment_method = data.get('payment_method', 'Cash')
            notes = data.get('notes', '')
            
            # Update student's total paid
            student.tuition_amount_paid = (student.tuition_amount_paid or Decimal('0')) + amount
            
            # Update current year's record if specified
            if 'academic_year_id' in data:
                tuition_record = TuitionRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=data['academic_year_id']
                ).first()
                
                if tuition_record:
                    tuition_record.amount_paid = (tuition_record.amount_paid or Decimal('0')) + amount
                    tuition_record.last_payment_date = payment_date
            
            # TODO: Create payment record in payment history table
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Payment of ${amount} recorded successfully'
            })
        
        elif action == 'apply_scholarship':
            amount = parse_decimal(data.get('amount', 0))
            reason = data.get('reason', '')
            
            student.scholarship_amount = (student.scholarship_amount or Decimal('0')) + amount
            
            # TODO: Create scholarship record
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Scholarship of ${amount} applied successfully'
            })
        
        else:
            return jsonify({'error': 'Invalid action'}), 400
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error processing financial action: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_tuition.route('/api/students/<student_id>/unenroll', methods=['POST'])
@login_required
@permission_required('edit_students')
def unenroll_student(student_id):
    """Unenroll a student (mark as inactive)"""
    try:
        student = Student.query.filter_by(id=student_id).first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        student.status = 'Inactive'
        student.date_left = date.today()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student unenrolled successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
