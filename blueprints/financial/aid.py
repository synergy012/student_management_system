from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import (Student, AcademicYear, db, FinancialRecord, FinancialAidApplication, 
                   DivisionFinancialConfig)
from utils.decorators import permission_required
from datetime import datetime
from decimal import Decimal
import traceback

financial_aid = Blueprint('financial_aid', __name__)

@financial_aid.route('/api/financial/records/<int:record_id>/mark-fa-received', methods=['POST'])
@login_required
@permission_required('edit_students')
def mark_fa_form_received(record_id):
    """Mark financial aid form as received"""
    try:
        record = FinancialRecord.query.get(record_id)
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        record.financial_aid_form_received = True
        record.financial_aid_form_received_date = datetime.utcnow()
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Financial aid form marked as received'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/financial/records/<int:record_id>/update-fafsa', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_fafsa_status(record_id):
    """Update FAFSA status"""
    try:
        data = request.get_json()
        record = FinancialRecord.query.get(record_id)
        
        if not record:
            return jsonify({'error': 'Record not found'}), 404
        
        record.fafsa_status = data.get('fafsa_status')
        
        if data.get('fafsa_submission_date'):
            record.fafsa_submission_date = datetime.strptime(data['fafsa_submission_date'], '%Y-%m-%d')
        
        record.pell_grant_eligible = data.get('pell_grant_eligible', False)
        record.pell_grant_amount = Decimal(str(data.get('pell_grant_amount', 0)))
        
        if record.pell_grant_eligible and record.pell_grant_amount > 0:
            record.pell_grant_received_date = datetime.utcnow()
        
        record.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'FAFSA status updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/divisions/<division>/financial-aid')
@login_required
@permission_required('view_students')
def division_financial_aid(division):
    """Display financial aid applications for a specific division"""
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
        
        # Get all applications for this division and year
        applications = FinancialAidApplication.query.filter_by(
            division=division,
            academic_year_id=academic_year.id
        ).order_by(FinancialAidApplication.application_date.desc()).all()
        
        # Get academic years for selector
        all_academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
        
        return render_template('financial/division_financial_aid.html',
                             division=division,
                             applications=applications,
                             academic_year=academic_year,
                             all_academic_years=all_academic_years)
    
    except Exception as e:
        current_app.logger.error(f"Error loading division financial aid: {str(e)}")
        flash('Error loading financial aid applications', 'error')
        return redirect(url_for('financial.financial_dashboard'))

@financial_aid.route('/api/financial-aid/<int:application_id>/update', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_financial_aid_application(application_id):
    """Update a financial aid application"""
    try:
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        
        # Update application fields
        if 'household_income' in data:
            application.household_income = Decimal(str(data['household_income']))
        if 'household_size' in data:
            application.household_size = int(data['household_size'])
        if 'requested_aid_amount' in data:
            application.requested_aid_amount = Decimal(str(data['requested_aid_amount']))
        if 'hardship_explanation' in data:
            application.hardship_explanation = data['hardship_explanation']
        
        # Update status if needed
        if 'application_status' in data:
            application.application_status = data['application_status']
            if data['application_status'] == 'Submitted':
                application.submission_date = datetime.utcnow()
        
        application.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Application updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating financial aid application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/financial-aid/<int:application_id>/send-form', methods=['POST'])
@login_required
@permission_required('edit_students')
def send_financial_aid_form_secure(application_id):
    """Send secure financial aid form to student/parents"""
    try:
        from secure_forms_service import SecureFormsService
        
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        recipient_email = data.get('recipient_email')
        expires_hours = data.get('expires_hours', 72)
        
        # Create secure link and send email
        forms_service = SecureFormsService()
        secure_link = forms_service.create_secure_link_and_send_email(
            student_id=application.student_id,
            form_type='financial_aid_app',
            form_id=application_id,
            expires_hours=expires_hours,
            recipient_email=recipient_email
        )
        
        return jsonify({
            'success': True,
            'message': 'Secure form link created and email sent successfully',
            'link_id': secure_link.id,
            'expires_at': secure_link.expires_at.isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending financial aid form: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/financial-aid/<int:application_id>/approve', methods=['POST'])
@login_required
@permission_required('edit_students')
def approve_financial_aid_application(application_id):
    """Approve a financial aid application and set award amount"""
    try:
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        award_amount = data.get('award_amount', 0)
        notes = data.get('notes', '')
        
        # Update application status
        application.application_status = 'Approved'
        application.award_amount = Decimal(str(award_amount))
        application.award_notes = notes
        application.reviewed_by = current_user.username
        application.reviewed_date = datetime.utcnow()
        application.updated_at = datetime.utcnow()
        
        # Also update the student's financial record for this year
        financial_record = FinancialRecord.query.filter_by(
            student_id=application.student_id,
            academic_year_id=application.academic_year_id
        ).first()
        
        if financial_record:
            financial_record.financial_aid_approved_amount = Decimal(str(award_amount))
            financial_record.financial_aid_form_received = True
            financial_record.financial_aid_form_received_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Application approved with award amount of ${award_amount:,.2f}',
            'award_amount': float(award_amount)
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving financial aid application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/financial-aid/<int:application_id>/deny', methods=['POST'])
@login_required
@permission_required('edit_students')
def deny_financial_aid_application(application_id):
    """Deny a financial aid application"""
    try:
        application = FinancialAidApplication.query.get(application_id)
        if not application:
            return jsonify({'error': 'Application not found'}), 404
        
        data = request.get_json()
        reason = data.get('reason', '')
        
        # Update application status
        application.application_status = 'Denied'
        application.denial_reason = reason
        application.reviewed_by = current_user.username
        application.reviewed_date = datetime.utcnow()
        application.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Application has been denied'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error denying financial aid application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/students/<student_id>/financial-aid/create', methods=['POST'])
@login_required
@permission_required('edit_students')
def create_financial_aid_application(student_id):
    """Create a new financial aid application for a student"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get current academic year
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not academic_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Check if application already exists for this year
        existing_application = FinancialAidApplication.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id
        ).first()
        
        if existing_application:
            return jsonify({'error': 'Financial aid application already exists for this year'}), 400
        
        data = request.get_json()
        
        # Create new application
        application = FinancialAidApplication(
            student_id=student_id,
            academic_year_id=academic_year.id,
            division=student.division,
            application_date=datetime.utcnow(),
            household_income=Decimal(str(data.get('household_income', 0))),
            household_size=int(data.get('household_size', 1)),
            requested_aid_amount=Decimal(str(data.get('requested_aid_amount', 0))),
            hardship_explanation=data.get('hardship_explanation', ''),
            application_status='Draft',
            created_by=current_user.username
        )
        
        db.session.add(application)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Financial aid application created successfully',
            'application_id': application.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating financial aid application: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_aid.route('/api/students/<student_id>/financial-aid/status', methods=['GET'])
@login_required
@permission_required('view_students')
def get_financial_aid_status(student_id):
    """Get financial aid status for a student"""
    try:
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get current academic year
        academic_year = AcademicYear.query.filter_by(is_active=True).first()
        if not academic_year:
            return jsonify({'error': 'No active academic year found'}), 400
        
        # Get financial aid application for current year
        application = FinancialAidApplication.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id
        ).first()
        
        # Get financial record for current year
        financial_record = FinancialRecord.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year.id
        ).first()
        
        status = {
            'has_application': bool(application),
            'application_status': application.application_status if application else None,
            'award_amount': float(application.award_amount) if application and application.award_amount else 0,
            'requested_amount': float(application.requested_aid_amount) if application and application.requested_aid_amount else 0,
            'form_sent': financial_record.financial_aid_form_sent if financial_record else False,
            'form_received': financial_record.financial_aid_form_received if financial_record else False,
            'fafsa_status': financial_record.fafsa_status if financial_record else None,
            'pell_grant_eligible': financial_record.pell_grant_eligible if financial_record else False,
            'pell_grant_amount': float(financial_record.pell_grant_amount) if financial_record and financial_record.pell_grant_amount else 0
        }
        
        if application:
            status.update({
                'application_id': application.id,
                'application_date': application.application_date.isoformat() if application.application_date else None,
                'submission_date': application.submission_date.isoformat() if application.submission_date else None,
                'reviewed_date': application.reviewed_date.isoformat() if application.reviewed_date else None,
                'household_income': float(application.household_income) if application.household_income else 0,
                'household_size': application.household_size or 0,
                'hardship_explanation': application.hardship_explanation or '',
                'award_notes': application.award_notes or '',
                'denial_reason': application.denial_reason or ''
            })
        
        return jsonify(status)
        
    except Exception as e:
        current_app.logger.error(f"Error getting financial aid status: {str(e)}")
        return jsonify({'error': str(e)}), 500
