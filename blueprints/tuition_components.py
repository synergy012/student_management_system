from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from models import (db, Student, AcademicYear, TuitionComponent, DivisionTuitionComponent, 
                   StudentTuitionComponent, TuitionRecord, DivisionConfig)
from utils.decorators import permission_required
from datetime import datetime
from decimal import Decimal

tuition_components = Blueprint('tuition_components', __name__)

@tuition_components.route('/api/tuition-components')
@login_required
@permission_required('view_students')
def get_tuition_components():
    """Get all tuition components"""
    try:
        components = TuitionComponent.query.filter_by(is_active=True).order_by(TuitionComponent.display_order).all()
        
        return jsonify({
            'success': True,
            'components': [{
                'id': comp.id,
                'name': comp.name,
                'description': comp.description,
                'component_type': comp.component_type,
                'is_required': comp.is_required,
                'is_proration_eligible': comp.is_proration_eligible,
                'calculation_method': comp.calculation_method,
                'display_order': comp.display_order
            } for comp in components]
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting tuition components: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/divisions/<division>/tuition-components')
@login_required
@permission_required('view_students')
def get_division_tuition_components(division):
    """Get tuition components configured for a specific division"""
    try:
        # Check if this division requires tuition
        division_config = DivisionConfig.query.filter_by(division=division).first()
        if division_config and not division_config.requires_tuition:
            return jsonify({
                'success': True,
                'division': division,
                'components': [],
                'message': f'{division} division does not require tuition'
            })
        
        academic_year_id = request.args.get('academic_year_id')
        if not academic_year_id:
            # Get active academic year
            active_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = active_year.id if active_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        # Get division components with their configurations
        division_components = db.session.query(
            DivisionTuitionComponent, TuitionComponent
        ).join(TuitionComponent).filter(
            DivisionTuitionComponent.division == division,
            DivisionTuitionComponent.academic_year_id == academic_year_id,
            DivisionTuitionComponent.is_enabled == True
        ).order_by(TuitionComponent.display_order).all()
        
        components_data = []
        for div_comp, comp in division_components:
            components_data.append({
                'id': comp.id,
                'name': comp.name,
                'description': comp.description,
                'component_type': comp.component_type,
                'default_amount': float(div_comp.default_amount),
                'minimum_amount': float(div_comp.minimum_amount or 0),
                'maximum_amount': float(div_comp.maximum_amount) if div_comp.maximum_amount else None,
                'is_required': div_comp.is_required,
                'is_student_editable': div_comp.is_student_editable,
                'is_proration_eligible': comp.is_proration_eligible,
                'notes': div_comp.notes
            })
        
        return jsonify({
            'success': True,
            'division': division,
            'academic_year_id': academic_year_id,
            'components': components_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting division tuition components: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/tuition-components/by-division')
@login_required  
@permission_required('view_students')
def get_tuition_components_by_division():
    """Get tuition components by division with student-specific overrides"""
    try:
        student_id = request.args.get('student_id')
        academic_year_id = request.args.get('academic_year_id')
        
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
            
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get academic year - use active year if not specified
        if academic_year_id:
            academic_year = AcademicYear.query.get(academic_year_id)
        else:
            academic_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = academic_year.id if academic_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        # Get division components for this academic year
        division_components = db.session.query(DivisionTuitionComponent, TuitionComponent).join(
            TuitionComponent, DivisionTuitionComponent.component_id == TuitionComponent.id
        ).filter(
            DivisionTuitionComponent.division == student.division,
            DivisionTuitionComponent.academic_year_id == academic_year_id,
            DivisionTuitionComponent.is_enabled == True,
            TuitionComponent.is_active == True
        ).order_by(TuitionComponent.display_order).all()
        
        # Check if student already has components configured for this year
        existing_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).all()
        
        existing_component_map = {comp.component_id: comp for comp in existing_components}
        
        # If no existing components for this year, try to find prior year components to copy settings
        prior_year_components = {}
        if not existing_components:
            # Find the most recent prior academic year for this student
            prior_year = AcademicYear.query.filter(
                AcademicYear.start_date < academic_year.start_date
            ).order_by(AcademicYear.start_date.desc()).first()
            
            if prior_year:
                prior_components = StudentTuitionComponent.query.filter_by(
                    student_id=student_id,
                    academic_year_id=prior_year.id
                ).all()
                
                # Map prior year components by component type for matching
                for comp in prior_components:
                    component = TuitionComponent.query.get(comp.component_id)
                    if component:
                        # Use component name as key for matching (e.g., "Tuition", "Room", "Board")
                        prior_year_components[component.name] = comp
        
        components_data = []
        for div_comp, comp in division_components:
            # Use existing student component if available
            student_comp = existing_component_map.get(comp.id)
            
            # If no existing component, check for prior year settings
            prior_comp = prior_year_components.get(comp.name) if not student_comp else None
            
            component_data = {
                'id': comp.id,
                'name': comp.name,
                'description': comp.description,
                'type': comp.component_type,
                'is_required': div_comp.is_required,
                'is_enabled': student_comp.is_active if student_comp else (
                    prior_comp.is_active if prior_comp else div_comp.is_required
                ),
                'amount': float(student_comp.amount if student_comp else div_comp.default_amount),
                'default_amount': float(div_comp.default_amount),
                'discount_percentage': float(
                    student_comp.discount_percentage if student_comp else (
                        prior_comp.discount_percentage if prior_comp else 0
                    )
                ),
                'calculated_amount': 0,  # Will be calculated by JavaScript
                'minimum_amount': float(div_comp.minimum_amount or 0),
                'maximum_amount': float(div_comp.maximum_amount) if div_comp.maximum_amount else None,
                'is_student_editable': div_comp.is_student_editable,
                'is_prorated': False,  # Always start with no proration for new academic years
                'proration_percentage': 100,  # Always start at 100% - user can manually adjust if needed
                'proration_reason': '',  # Don't carry over proration reasons
                'notes': div_comp.notes or ''
            }
            
            # Calculate the amount after discount
            amount = component_data['amount']
            discount = component_data['discount_percentage']
            component_data['calculated_amount'] = amount * (1 - discount / 100)
            
            components_data.append(component_data)
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'division': student.division,
            'academic_year_id': academic_year_id,
            'components': components_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting tuition components by division: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/students/<student_id>/tuition-components')
@login_required
@permission_required('view_students')
def get_student_tuition_components(student_id):
    """Get tuition components for a specific student"""
    try:
        academic_year_id = request.args.get('academic_year_id')
        if not academic_year_id:
            # Get active academic year
            active_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = active_year.id if active_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get or create student components
        student_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id,
            is_active=True
        ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
        
        # If no components exist, create them from division defaults
        if not student_components:
            StudentTuitionComponent.create_for_student(student_id, academic_year_id, student.division)
            student_components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id,
                is_active=True
            ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
        
        components_data = []
        total_amount = 0
        total_paid = 0
        total_balance = 0
        
        for comp in student_components:
            calculated_amount = comp.calculated_amount
            balance = comp.calculate_balance()
            
            total_amount += calculated_amount
            total_paid += (comp.amount_paid or 0)
            total_balance += balance
            
            components_data.append({
                'id': comp.id,
                'component_id': comp.component_id,
                'name': comp.component.name,
                'description': comp.component.description,
                'component_type': comp.component.component_type,
                'original_amount': float(comp.original_amount or 0),
                'amount': float(comp.amount),
                'calculated_amount': float(calculated_amount),
                'discount_amount': float(comp.discount_amount or 0),
                'discount_percentage': float(comp.discount_percentage or 0),
                'discount_reason': comp.discount_reason or '',
                'is_prorated': comp.is_prorated,
                'proration_percentage': float(comp.proration_percentage),
                'proration_reason': comp.proration_reason or '',
                'amount_paid': float(comp.amount_paid or 0),
                'balance_due': float(balance),
                'is_override': comp.is_override,
                'override_reason': comp.override_reason or '',
                'notes': comp.notes or ''
            })
        
        return jsonify({
            'success': True,
            'student_id': student_id,
            'student_name': student.student_name,
            'division': student.division,
            'academic_year_id': academic_year_id,
            'components': components_data,
            'totals': {
                'total_amount': float(total_amount),
                'total_paid': float(total_paid),
                'total_balance': float(total_balance)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting student tuition components: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/students/<student_id>/tuition-components/<int:component_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def update_student_tuition_component(student_id, component_id):
    """Update a student's tuition component"""
    try:
        data = request.get_json()
        
        student_component = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            component_id=component_id
        ).first()
        
        if not student_component:
            return jsonify({'error': 'Student component not found'}), 404
        
        # Update fields
        if 'amount' in data:
            student_component.amount = Decimal(str(data['amount']))
            if not student_component.original_amount:
                student_component.original_amount = student_component.amount
        
        if 'discount_amount' in data:
            student_component.discount_amount = Decimal(str(data['discount_amount'] or 0))
        
        if 'discount_percentage' in data:
            student_component.discount_percentage = Decimal(str(data['discount_percentage'] or 0))
        
        if 'discount_reason' in data:
            student_component.discount_reason = data['discount_reason']
        
        if 'is_prorated' in data:
            student_component.is_prorated = data['is_prorated']
        
        if 'proration_percentage' in data:
            student_component.proration_percentage = Decimal(str(data['proration_percentage'] or 100))
        
        if 'proration_reason' in data:
            student_component.proration_reason = data['proration_reason']
        
        if 'override_reason' in data:
            student_component.override_reason = data['override_reason']
            student_component.is_override = bool(data['override_reason'])
        
        if 'notes' in data:
            student_component.notes = data['notes']
        
        # Mark as updated
        student_component.updated_by = current_user.username
        student_component.updated_at = datetime.utcnow()
        
        # Recalculate balance
        student_component.calculate_balance()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Component updated successfully',
            'calculated_amount': float(student_component.calculated_amount),
            'balance_due': float(student_component.balance_due)
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating student tuition component: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/students/<student_id>/tuition-components/recalculate', methods=['POST'])
@login_required
@permission_required('edit_students')
def recalculate_student_tuition(student_id):
    """Recalculate total tuition for a student based on components"""
    try:
        academic_year_id = request.json.get('academic_year_id')
        if not academic_year_id:
            active_year = AcademicYear.query.filter_by(is_active=True).first()
            academic_year_id = active_year.id if active_year else None
        
        if not academic_year_id:
            return jsonify({'error': 'No academic year specified'}), 400
        
        # Get all student components
        student_components = StudentTuitionComponent.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id,
            is_active=True
        ).all()
        
        total_amount = 0
        total_paid = 0
        total_balance = 0
        
        for comp in student_components:
            calculated_amount = comp.calculated_amount
            comp.calculate_balance()
            
            total_amount += calculated_amount
            total_paid += (comp.amount_paid or 0)
            total_balance += comp.balance_due
        
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
        
        # Update tuition record with calculated totals
        tuition_record.tuition_determination = total_amount
        tuition_record.amount_paid = total_paid
        tuition_record.tuition_amount = total_amount
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tuition recalculated successfully',
            'totals': {
                'total_amount': float(total_amount),
                'total_paid': float(total_paid),
                'total_balance': float(total_balance)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error recalculating student tuition: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/api/divisions/<division>/tuition-components/<int:component_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def update_division_tuition_component(division, component_id):
    """Update division default for a tuition component"""
    try:
        data = request.get_json()
        academic_year_id = data.get('academic_year_id')
        
        if not academic_year_id:
            return jsonify({'error': 'Academic year ID required'}), 400
        
        division_component = DivisionTuitionComponent.query.filter_by(
            division=division,
            component_id=component_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not division_component:
            return jsonify({'error': 'Division component not found'}), 404
        
        # Update fields
        if 'default_amount' in data:
            division_component.default_amount = Decimal(str(data['default_amount']))
        
        if 'minimum_amount' in data:
            division_component.minimum_amount = Decimal(str(data['minimum_amount'] or 0))
        
        if 'maximum_amount' in data:
            division_component.maximum_amount = Decimal(str(data['maximum_amount'])) if data['maximum_amount'] else None
        
        if 'is_required' in data:
            division_component.is_required = data['is_required']
        
        if 'is_student_editable' in data:
            division_component.is_student_editable = data['is_student_editable']
        

        
        if 'notes' in data:
            division_component.notes = data['notes']
        
        division_component.updated_by = current_user.username
        division_component.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Division component updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating division tuition component: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tuition_components.route('/tuition-settings')
@login_required
@permission_required('edit_students')
def tuition_settings():
    """Show tuition settings management page"""
    try:
        # Get active academic year
        active_year = AcademicYear.query.filter_by(is_active=True).first()
        academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        # Get all tuition components
        components = TuitionComponent.query.filter_by(is_active=True).order_by(TuitionComponent.display_order).all()
        
        # Get division configurations for active year
        division_configs = {}
        if active_year:
            for division in ['YZA', 'YOH', 'KOLLEL']:
                division_configs[division] = DivisionTuitionComponent.query.filter_by(
                    division=division,
                    academic_year_id=active_year.id,
                    is_enabled=True
                ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
        
        return render_template('tuition_settings.html',
                             academic_years=academic_years,
                             active_year=active_year,
                             components=components,
                             division_configs=division_configs)
    
    except Exception as e:
        current_app.logger.error(f"Error loading tuition settings: {str(e)}")
        return render_template('404.html'), 500 