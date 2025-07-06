"""
Kollel Management Blueprint
==========================
Handles kollel student management, monthly stipend calculations, and payment tracking.
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime, date
from decimal import Decimal
from models import (db, Student, KollelStudent, MonthlyStipend, DivisionConfig, 
                    AcademicYear, KollelBreakCredit)
from utils.decorators import permission_required
from sqlalchemy import and_, or_, extract
import calendar

kollel = Blueprint('kollel', __name__)

# Helper function to get or create division config
def get_kollel_config():
    config = DivisionConfig.query.filter_by(division='KOLLEL').first()
    if not config:
        config = DivisionConfig(division='KOLLEL', form_id='3')
        db.session.add(config)
        db.session.commit()
    return config

def get_current_academic_year():
    """Get current academic year based on today's date (Sept-Aug cycle)"""
    today = date.today()
    if today.month >= 9:  # September or later = start of new academic year
        return today.year
    else:  # January-August = continuation of previous academic year
        return today.year - 1

def get_academic_year_range(academic_year):
    """Get the start and end calendar years for an academic year"""
    start_year = academic_year
    end_year = academic_year + 1
    return start_year, end_year

def format_academic_year(academic_year):
    """Format academic year for display (e.g., '2024-2025')"""
    return f"{academic_year}-{academic_year + 1}"

def get_academic_year_months():
    """Get ordered list of months in academic year (Sept-Aug)"""
    return [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]

def get_calendar_year_for_month(academic_year, month):
    """Get the correct calendar year for a given month in an academic year"""
    if month >= 9:  # Sept-Dec are in the first calendar year
        return academic_year
    else:  # Jan-Aug are in the second calendar year  
        return academic_year + 1

@kollel.route('/kollel')
@login_required
@permission_required('edit_students')
def kollel_dashboard():
    """Main kollel dashboard with monthly stipend tracking"""
    # Get academic year from query params (can be ID or year number for backward compatibility)
    academic_year_param = request.args.get('academic_year_id') or request.args.get('school_year')
    month = request.args.get('month', type=int, default=datetime.now().month)
    
    # If academic_year_param is provided, determine if it's an ID or year number
    selected_academic_year = None
    if academic_year_param:
        try:
            academic_year_param = int(academic_year_param)
            # Check if it's an ID (likely > 1000) or a year (like 2024)
            if academic_year_param > 1000:
                # It's an ID
                selected_academic_year = AcademicYear.query.get(academic_year_param)
            else:
                # It's a year number - find the corresponding academic year
                selected_academic_year = AcademicYear.query.filter(
                    AcademicYear.year_label == f"{academic_year_param}-{academic_year_param + 1}"
                ).first()
        except (ValueError, TypeError):
            pass
    
    # If no valid academic year found, use the current active one
    if not selected_academic_year:
        selected_academic_year = AcademicYear.query.filter_by(is_active=True).first()
    
    # If still no academic year, use the most recent one
    if not selected_academic_year:
        selected_academic_year = AcademicYear.query.order_by(AcademicYear.start_date.desc()).first()
    
    # Extract academic year number from name (e.g., "2024-2025" -> 2024)
    if selected_academic_year:
        academic_year = int(selected_academic_year.year_label.split('-')[0])
    else:
        academic_year = get_current_academic_year()
    
    # Calculate the actual calendar year for this month
    year = get_calendar_year_for_month(academic_year, month)
    
    # Get all active kollel students
    kollel_students = KollelStudent.query.filter_by(is_active=True).all()
    
    student_records = []
    for ks in kollel_students:
        # Get or create monthly stipend record
        stipend = MonthlyStipend.query.filter_by(
            kollel_student_id=ks.id,
            month=month,
            year=year
        ).first()
        
        if not stipend:
            # Create new stipend record
            stipend = MonthlyStipend(
                kollel_student_id=ks.id,
                month=month,
                year=year,
                base_stipend_amount=ks.base_stipend_amount,
                actual_credits_earned=0,
                prorated_credits=0,
                total_credits=0,
                incentive_amount=0,
                base_plus_incentive=0,
                kollel_elyon_bonus=Decimal('1000') if ks.is_kollel_elyon else Decimal('0'),
                retufin_pay=Decimal('0'),  # No auto-population, everyone eligible
                mussar_chabura_pay=Decimal('0'),  # No auto-population, everyone eligible
                iyun_chabura_pay=Decimal('0'),
                special_pay=Decimal('0'),  # Work study, etc.
                missed_time_deduction=0,
                other_deductions=0,
                final_amount=0,
                payment_status='Pending'
            )
            db.session.add(stipend)
            db.session.commit()
        
        student_records.append({
            'student': ks.student,
            'kollel_student': ks,
            'stipend': stipend
        })
    
    # Get all available academic years for the dropdown
    all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    available_academic_years = []
    for ay in all_academic_years:
        available_academic_years.append({
            'id': ay.id,
            'name': ay.year_label,
            'is_selected': ay.id == (selected_academic_year.id if selected_academic_year else None)
        })
    
    # Generate list of available school years (for backward compatibility)
    current_academic_year_num = get_current_academic_year()
    available_school_years = []
    for i in range(5, -2, -1):  # 5 years back to 1 year forward
        ay = current_academic_year_num - i
        available_school_years.append({
            'year': ay,
            'label': format_academic_year(ay)
        })
    
    return render_template('kollel_dashboard.html',
                         student_records=student_records,
                         selected_month=month,
                         selected_school_year=academic_year,
                         selected_year=year,  # Keep for compatibility
                         available_school_years=available_school_years,
                         available_academic_years=available_academic_years,
                         school_year_months=get_academic_year_months(),
                         current_academic_year=selected_academic_year)

@kollel.route('/kollel/students')
@login_required
@permission_required('edit_students')
def kollel_students():
    """Manage kollel students - add/remove from program"""
    # Get all active students (using status field instead of is_active)
    all_students = Student.query.filter_by(status='Active').order_by(Student.student_name).all()
    
    # Get existing kollel students with their kollel_student_id
    kollel_students = KollelStudent.query.filter_by(is_active=True).all()
    kollel_student_ids = [ks.student_id for ks in kollel_students]
    kollel_student_map = {ks.student_id: ks.id for ks in kollel_students}
    
    return render_template('kollel/students.html',
                         all_students=all_students,
                         kollel_student_ids=kollel_student_ids,
                         kollel_student_map=kollel_student_map)

@kollel.route('/kollel/students/add', methods=['POST'])
@login_required
@permission_required('edit_students')
def add_kollel_student():
    """Add a student to the kollel program"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        # Check if already in kollel
        existing = KollelStudent.query.filter_by(student_id=student_id).first()
        if existing:
            if existing.is_active:
                return jsonify({'success': False, 'message': 'Student is already in Kollel'})
            else:
                # Reactivate
                existing.is_active = True
                existing.date_joined_kollel = datetime.now().date()
                existing.date_left_kollel = None
        else:
            # Create new kollel student
            kollel_student = KollelStudent(
                student_id=student_id,
                base_stipend_amount=Decimal(str(data.get('base_stipend_amount', 600))),
                is_kollel_elyon=data.get('is_kollel_elyon', False),
                date_joined_kollel=datetime.now().date(),
                is_active=True
            )
            db.session.add(kollel_student)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Student added to Kollel'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@kollel.route('/kollel/students/<int:kollel_student_id>/remove', methods=['POST'])
@login_required
@permission_required('edit_students')
def remove_kollel_student(kollel_student_id):
    """Remove a student from the kollel program"""
    try:
        kollel_student = KollelStudent.query.get_or_404(kollel_student_id)
        kollel_student.is_active = False
        kollel_student.date_left_kollel = datetime.now().date()
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Student removed from Kollel'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@kollel.route('/kollel/stipends/<int:stipend_id>', methods=['PUT'])
@login_required
@permission_required('edit_students')
def update_stipend(stipend_id):
    """Update a monthly stipend record"""
    try:
        stipend = MonthlyStipend.query.get_or_404(stipend_id)
        data = request.get_json()
        
        # Update fields - convert to Decimal to avoid float/Decimal mixing errors
        if 'actual_credits_earned' in data:
            stipend.actual_credits_earned = Decimal(str(data['actual_credits_earned']))
        if 'prorated_credits' in data:
            stipend.prorated_credits = Decimal(str(data['prorated_credits']))
        if 'credits_override' in data:
            stipend.credits_override = bool(data['credits_override'])
        if 'base_stipend_amount' in data:
            stipend.base_stipend_amount = Decimal(str(data['base_stipend_amount']))
        if 'kollel_elyon_bonus' in data:
            stipend.kollel_elyon_bonus = Decimal(str(data['kollel_elyon_bonus']))
        if 'retufin_pay' in data:
            stipend.retufin_pay = Decimal(str(data['retufin_pay']))
        if 'special_pay' in data:
            stipend.special_pay = Decimal(str(data['special_pay']))
        
        # Handle chabura counts and calculate amounts  
        if 'mussar_chabura_count' in data:
            count = int(data['mussar_chabura_count'])
            stipend.mussar_chabura_pay = Decimal(str(count * 25))
        elif 'mussar_chabura_pay' in data:
            stipend.mussar_chabura_pay = Decimal(str(data['mussar_chabura_pay']))
            
        if 'iyun_chabura_count' in data:
            count = int(data['iyun_chabura_count'])
            stipend.iyun_chabura_pay = Decimal(str(count * 100))
        elif 'iyun_chabura_pay' in data:
            stipend.iyun_chabura_pay = Decimal(str(data['iyun_chabura_pay']))
        
        if 'total_deductions' in data:
            # Split deductions (simplified - you may want separate fields)
            stipend.other_deductions = Decimal(str(data['total_deductions']))
        if 'payment_status' in data:
            stipend.payment_status = data['payment_status']
        
        # Calculate derived fields - ensure all calculations use Decimal
        stipend.total_credits = stipend.actual_credits_earned + stipend.prorated_credits
        
        # Calculate incentive - must earn at least 10 credits to get any incentive pay
        total_credits = stipend.total_credits
        if total_credits < 10:
            stipend.incentive_amount = Decimal('0')  # No incentive if under 10 credits
        elif total_credits == 10:
            stipend.incentive_amount = Decimal('200')  # Base incentive for exactly 10 credits
        else:
            stipend.incentive_amount = Decimal('200') + ((total_credits - Decimal('10')) * Decimal('25'))
        
        # Calculate base + incentive with different caps based on base pay
        base_plus_incentive = stipend.base_stipend_amount + stipend.incentive_amount
        if stipend.base_stipend_amount == 0:
            # For 0 base pay students, incentive is capped at 500
            stipend.base_plus_incentive = min(stipend.incentive_amount, Decimal('500'))
        else:
            # For other students, base + incentive is capped at 1000
            stipend.base_plus_incentive = min(base_plus_incentive, Decimal('1000'))
        
        # Calculate final amount - ensure all values are Decimal
        stipend.final_amount = (
            stipend.base_plus_incentive +
            stipend.kollel_elyon_bonus +
            stipend.retufin_pay +
            stipend.mussar_chabura_pay +
            stipend.iyun_chabura_pay +
            (stipend.special_pay or Decimal('0')) -
            (stipend.missed_time_deduction or Decimal('0')) -
            (stipend.other_deductions or Decimal('0'))
        )
        
        # Update timestamp
        stipend.last_updated = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'stipend': {
                'total_credits': stipend.total_credits,
                'incentive_amount': stipend.incentive_amount,
                'base_plus_incentive': stipend.base_plus_incentive,
                'final_amount': stipend.final_amount
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

def calculate_break_days_in_month(month, calendar_year, academic_year_id):
    """Calculate number of break days in a specific month"""
    import calendar
    
    # Get month date range
    month_start = date(calendar_year, month, 1)
    _, last_day = calendar.monthrange(calendar_year, month)
    month_end = date(calendar_year, month, last_day)
    
    # Get all breaks for the academic year
    breaks = KollelBreakCredit.query.filter_by(
        academic_year_id=academic_year_id,
        is_active=True
    ).all()
    
    total_break_days = 0
    for break_period in breaks:
        # Check if break overlaps with this month
        if break_period.start_date <= month_end and break_period.end_date >= month_start:
            # Calculate overlap days
            overlap_start = max(break_period.start_date, month_start)
            overlap_end = min(break_period.end_date, month_end)
            overlap_days = (overlap_end - overlap_start).days + 1
            total_break_days += overlap_days
    
    return total_break_days

def calculate_non_break_days_in_month(month, calendar_year, academic_year_id):
    """Calculate number of non-break days in a month (total days - break days)"""
    import calendar
    
    # Get total days in month
    _, total_days = calendar.monthrange(calendar_year, month)
    
    # Get break days in month
    break_days = calculate_break_days_in_month(month, calendar_year, academic_year_id)
    
    return total_days - break_days

def get_last_n_pay_periods(kollel_student_id, current_month, current_year, n_periods=5):
    """Get the last N pay periods for a student, or fewer if they haven't been in kollel that long"""
    periods = []
    month = current_month
    year = current_year
    
    for i in range(n_periods):
        # Go back one month
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        
        # Check if student has a stipend record for this month
        stipend = MonthlyStipend.query.filter_by(
            kollel_student_id=kollel_student_id,
            month=month,
            year=year
        ).first()
        
        if stipend:
            periods.append({
                'month': month,
                'year': year,
                'stipend': stipend
            })
        else:
            # Student wasn't in kollel this month, stop looking back
            break
    
    return periods

@kollel.route('/kollel/apply-breaks/<int:month>/<int:school_year>', methods=['POST'])
@login_required
@permission_required('manage_users')
def apply_break_credits(month, school_year):
    """Apply pro-rated break credits to all students for a given month using the proper formula"""
    try:
        # Convert academic year and month to calendar year
        calendar_year = get_calendar_year_for_month(school_year, month)
        
        # Get current academic year
        current_academic_year = AcademicYear.query.filter(
            AcademicYear.start_date <= date(calendar_year, month, 1),
            AcademicYear.end_date >= date(calendar_year, month, 1)
        ).first()
        
        if not current_academic_year:
            return jsonify({'success': False, 'message': 'No academic year found for this period'})
        
        # Calculate break days in the current month
        break_days_this_month = calculate_break_days_in_month(month, calendar_year, current_academic_year.id)
        
        if break_days_this_month == 0:
            return jsonify({'success': False, 'message': 'No break days found in this month'})
        
        # Get all stipends for this month
        stipends = MonthlyStipend.query.filter_by(month=month, year=calendar_year).all()
        updated_count = 0
        calculation_details = []
        
        for stipend in stipends:
            if stipend.credits_override:
                continue  # Skip if manually overridden
            
            # Get last 5 pay periods (or fewer if student hasn't been in kollel that long)
            past_periods = get_last_n_pay_periods(stipend.kollel_student_id, month, calendar_year, 5)
            
            if not past_periods:
                # Student has no history, skip
                continue
            
            total_actual_credits = Decimal('0')
            total_non_break_days = 0
            
            # Calculate totals from past periods
            for period in past_periods:
                # Get non-break days for this period
                period_academic_year = AcademicYear.query.filter(
                    AcademicYear.start_date <= date(period['year'], period['month'], 1),
                    AcademicYear.end_date >= date(period['year'], period['month'], 1)
                ).first()
                
                if period_academic_year:
                    non_break_days = calculate_non_break_days_in_month(
                        period['month'], period['year'], period_academic_year.id
                    )
                    total_non_break_days += non_break_days
                    total_actual_credits += period['stipend'].actual_credits_earned or Decimal('0')
            
            # Calculate break credits using the formula
            if total_non_break_days > 0:
                daily_credit_rate = total_actual_credits / Decimal(str(total_non_break_days))
                calculated_break_credits = daily_credit_rate * Decimal(str(break_days_this_month))
                
                # Store the full decimal calculation for display/special exceptions
                stipend.prorated_credits = calculated_break_credits
                
                # Note: Partial credits are not paid, but we show the decimal
                # The actual payment calculation will floor this value
                
                calculation_details.append({
                    'student_name': stipend.kollel_student.student.student_name,
                    'past_periods': len(past_periods),
                    'total_actual_credits': float(total_actual_credits),
                    'total_non_break_days': total_non_break_days,
                    'break_days_this_month': break_days_this_month,
                    'daily_rate': float(daily_credit_rate),
                    'calculated_credits': float(calculated_break_credits),
                    'paid_credits': float(calculated_break_credits.quantize(Decimal('1'), rounding='ROUND_DOWN'))
                })
                
                updated_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Applied break credits to {updated_count} students using last 5 pay periods formula',
            'break_days_this_month': break_days_this_month,
            'calculation_details': calculation_details
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@kollel.route('/kollel/history/<int:kollel_student_id>')
@login_required
@permission_required('edit_students')
def student_history(kollel_student_id):
    """View stipend history for a kollel student"""
    kollel_student = KollelStudent.query.get_or_404(kollel_student_id)
    
    # Get all stipends for this student
    stipends = MonthlyStipend.query.filter_by(
        kollel_student_id=kollel_student_id
    ).order_by(
        MonthlyStipend.year.desc(),
        MonthlyStipend.month.desc()
    ).all()
    
    # Calculate totals
    total_paid = sum(s.final_amount for s in stipends if s.payment_status == 'Paid')
    total_pending = sum(s.final_amount for s in stipends if s.payment_status == 'Pending')
    
    return render_template('kollel/history.html',
                         kollel_student=kollel_student,
                         stipends=stipends,
                         total_paid=total_paid,
                         total_pending=total_pending)

@kollel.route('/kollel/edit/<int:kollel_student_id>', methods=['GET', 'POST'])
@login_required
@permission_required('edit_students')
def edit_kollel_student(kollel_student_id):
    """Edit kollel student details (base pay, Kollel Elyon status, etc.)"""
    kollel_student = KollelStudent.query.get_or_404(kollel_student_id)
    
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            # Track if changes were made that affect future stipends
            changes_made = False
            change_summary = []
            
            # Update base stipend amount (prospective only)
            if 'base_stipend_amount' in data:
                new_amount = Decimal(str(data['base_stipend_amount']))
                if kollel_student.base_stipend_amount != new_amount:
                    old_amount = kollel_student.base_stipend_amount
                    kollel_student.base_stipend_amount = new_amount
                    changes_made = True
                    change_summary.append(f"Base stipend: ${old_amount} → ${new_amount}")
            
            # Update Kollel Elyon status (prospective only)
            if 'is_kollel_elyon' in data:
                new_status = bool(data['is_kollel_elyon'])
                if kollel_student.is_kollel_elyon != new_status:
                    old_status = kollel_student.is_kollel_elyon
                    kollel_student.is_kollel_elyon = new_status
                    changes_made = True
                    status_change = f"Kollel Elyon: {'Yes' if old_status else 'No'} → {'Yes' if new_status else 'No'}"
                    change_summary.append(status_change)
            
            # Note: Removed eligibility flags since everyone is eligible for Retzufin and Mussar Chabura
            
            if changes_made:
                kollel_student.updated_at = datetime.now()
                db.session.commit()
                
                # Add note about prospective changes
                flash(f"Student details updated successfully. Changes will apply to future stipend calculations only.", 'success')
                
                if request.is_json:
                    return jsonify({
                        'success': True,
                        'message': 'Student details updated successfully',
                        'changes': change_summary,
                        'note': 'Changes apply to future stipends only'
                    })
                else:
                    return redirect(url_for('kollel.kollel_dashboard'))
            else:
                message = 'No changes were made.'
                if request.is_json:
                    return jsonify({'success': True, 'message': message})
                else:
                    flash(message, 'info')
        
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating student details: {str(e)}"
            if request.is_json:
                return jsonify({'success': False, 'message': error_msg}), 400
            else:
                flash(error_msg, 'error')
    
    # GET request - show edit form
    return render_template('kollel/edit_student.html', kollel_student=kollel_student)

@kollel.route('/kollel/reports')
@login_required
@permission_required('manage_users')
def kollel_reports():
    """Generate various kollel reports"""
    # Get report parameters
    report_type = request.args.get('type', 'monthly_summary')
    month = request.args.get('month', type=int, default=datetime.now().month)
    academic_year = request.args.get('school_year', type=int, default=get_current_academic_year())
    
    # Convert to calendar year
    year = get_calendar_year_for_month(academic_year, month)
    
    if report_type == 'monthly_summary':
        # Get all stipends for the month
        stipends = MonthlyStipend.query.filter_by(month=month, year=year).all()
        
        # Calculate summary statistics
        summary = {
            'total_students': len(stipends),
            'total_amount': sum(s.final_amount for s in stipends),
            'total_paid': sum(s.final_amount for s in stipends if s.payment_status == 'Paid'),
            'total_pending': sum(s.final_amount for s in stipends if s.payment_status == 'Pending'),
            'average_stipend': sum(s.final_amount for s in stipends) / len(stipends) if stipends else 0,
            'total_credits': sum(s.total_credits for s in stipends),
            'total_deductions': sum(s.missed_time_deduction + s.other_deductions for s in stipends)
        }
        
        return render_template('kollel/reports.html',
                             report_type=report_type,
                             month=month,
                             year=year,
                             summary=summary,
                             stipends=stipends)
    
    return render_template('kollel/reports.html')

@kollel.route('/kollel/settings')
@login_required
@permission_required('manage_users')
def kollel_settings():
    """Kollel program settings"""
    config = get_kollel_config()
    
    # Get break credit configuration
    break_configs = KollelBreakCredit.query.order_by(
        KollelBreakCredit.academic_year_id.desc()
    ).all()
    
    return render_template('kollel/settings.html',
                         config=config,
                         break_configs=break_configs)

@kollel.route('/kollel/settings/update', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_kollel_settings():
    """Update kollel settings"""
    try:
        config = get_kollel_config()
        
        # Update settings from form
        if 'default_base_stipend' in request.form:
            config.default_base_stipend = Decimal(str(request.form['default_base_stipend']))
        if 'kollel_elyon_bonus' in request.form:
            config.kollel_elyon_bonus = Decimal(str(request.form['kollel_elyon_bonus']))
        if 'credit_calculation_method' in request.form:
            config.credit_calculation_method = request.form['credit_calculation_method']
        
        db.session.commit()
        flash('Kollel settings updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating settings: {str(e)}', 'error')
    
    return redirect(url_for('kollel.kollel_settings'))

@kollel.route('/kollel/breaks')
@login_required
@permission_required('manage_users')
def manage_breaks():
    """Manage kollel break periods and credit calculations"""
    # Get all academic years
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    
    # Get break configurations
    break_configs = {}
    for year in academic_years:
        configs = KollelBreakCredit.query.filter_by(academic_year_id=year.id).all()
        break_configs[year.id] = configs
    
    return render_template('kollel/breaks.html',
                         academic_years=academic_years,
                         break_configs=break_configs)

@kollel.route('/kollel/breaks/add', methods=['POST'])
@login_required
@permission_required('manage_users')
def add_break_period():
    """Add a new break period"""
    try:
        data = request.get_json()
        
        break_credit = KollelBreakCredit(
            academic_year_id=data['academic_year_id'],
            name=data['break_name'],
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            prorated_credits_per_student=Decimal('0'),  # Not used since credits are calculated per student
            is_active=True
        )
        db.session.add(break_credit)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Break period added successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@kollel.route('/kollel/export/<int:month>/<int:school_year>')
@login_required
@permission_required('manage_users')
def export_stipends(month, school_year):
    """Export monthly stipends to CSV"""
    # Convert academic year and month to calendar year
    year = get_calendar_year_for_month(school_year, month)
    import csv
    from io import StringIO
    from flask import make_response
    
    # Get all stipends for the month
    stipends = db.session.query(MonthlyStipend, KollelStudent, Student).join(
        KollelStudent, MonthlyStipend.kollel_student_id == KollelStudent.id
    ).join(
        Student, KollelStudent.student_id == Student.id
    ).filter(
        MonthlyStipend.month == month,
        MonthlyStipend.year == year
    ).order_by(Student.student_name).all()
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow([
        'Student Name', 'Student ID', 'Base Stipend', 'Credits Earned', 
        'Pro-rated Credits', 'Total Credits', 'Incentive Amount',
        'Base + Incentive', 'KE Bonus', 'Retufin', 'Mussar Chabura',
        'Iyun Chabura', 'Deductions', 'Final Amount', 'Payment Status'
    ])
    
    # Write data
    for stipend, kollel_student, student in stipends:
        writer.writerow([
            student.student_name,
            student.student_id,
            stipend.base_stipend_amount,
            stipend.actual_credits_earned,
            stipend.prorated_credits,
            stipend.total_credits,
            stipend.incentive_amount,
            stipend.base_plus_incentive,
            stipend.kollel_elyon_bonus,
            stipend.retufin_pay,
            stipend.mussar_chabura_pay,
            stipend.iyun_chabura_pay,
            stipend.missed_time_deduction + stipend.other_deductions,
            stipend.final_amount,
            stipend.payment_status
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=kollel_stipends_{month}_{year}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response
