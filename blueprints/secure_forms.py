from flask import Blueprint, render_template, request, jsonify, send_file, current_app, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from models import SecureFormLink, FormUploadLog, db
from secure_forms_service import SecureFormsService
from datetime import datetime
import os

secure_forms = Blueprint('secure_forms', __name__)

@secure_forms.route('/secure-upload/<token>')
def upload_form(token):
    """Secure upload page for students/parents"""
    # Verify token
    secure_link = SecureFormLink.query.filter_by(token=token).first()
    if not secure_link:
        return render_template('secure_forms/invalid_link.html', 
                             error="Invalid upload link"), 404
    
    # Check if expired
    if secure_link.is_expired:
        return render_template('secure_forms/invalid_link.html', 
                             error="This upload link has expired"), 410
    
    # Check if already used
    if not secure_link.is_usable:
        return render_template('secure_forms/invalid_link.html', 
                             error="This upload link has already been used"), 410
    
    # Track access
    secure_link.increment_usage()
    
    return render_template('secure_forms/upload_form.html', 
                         secure_link=secure_link)

@secure_forms.route('/api/secure-upload/<token>', methods=['POST'])
def process_upload(token):
    """Process the uploaded form"""
    try:
        # Verify token
        secure_link = SecureFormLink.query.filter_by(token=token).first()
        if not secure_link or not secure_link.is_usable:
            return jsonify({'error': 'Invalid or expired upload link'}), 400
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get additional form data
        document_category = request.form.get('document_category')
        document_description = request.form.get('document_description')
        
        # Process upload
        forms_service = SecureFormsService()
        upload_log = forms_service.process_upload(
            token=token,
            uploaded_file=uploaded_file,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            document_category=document_category,
            document_description=document_description
        )
        
        return jsonify({
            'success': True,
            'message': 'File uploaded successfully! You will receive a confirmation email shortly.',
            'upload_id': upload_log.id
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': 'An error occurred during upload. Please try again.'}), 500

@secure_forms.route('/download-form/<token>')
def download_form(token):
    """Download pre-filled form"""
    # Verify token
    secure_link = SecureFormLink.query.filter_by(token=token).first()
    if not secure_link or secure_link.is_expired:
        abort(404)
    
    # Check if pre-filled form exists
    if not secure_link.pre_filled_pdf_path or not os.path.exists(secure_link.pre_filled_pdf_path):
        abort(404)
    
    # Track download
    secure_link.last_accessed = datetime.utcnow()
    if not secure_link.first_accessed:
        secure_link.first_accessed = datetime.utcnow()
        secure_link.status = 'accessed'
    db.session.commit()
    
    return send_file(
        secure_link.pre_filled_pdf_path,
        as_attachment=True,
        download_name=f"{secure_link.form_title.replace(' ', '_')}.pdf",
        mimetype='application/pdf'
    )

# Admin routes for managing secure forms
@secure_forms.route('/admin/secure-forms')
@login_required
def admin_secure_forms():
    """Admin page for managing secure form links"""
    if not current_user.has_permission('manage_users'):
        abort(403)
    
    # Get all secure links
    links = SecureFormLink.query.order_by(SecureFormLink.created_at.desc()).all()
    
    return render_template('secure_forms/admin_links.html', links=links)

@secure_forms.route('/admin/form-uploads')
@login_required
def admin_form_uploads():
    """Admin page for reviewing uploaded forms"""
    if not current_user.has_permission('manage_users'):
        abort(403)
    
    # Get all uploads
    uploads = FormUploadLog.query.order_by(FormUploadLog.uploaded_at.desc()).all()
    
    return render_template('secure_forms/admin_uploads.html', uploads=uploads)

@secure_forms.route('/admin/upload/<int:upload_id>/download')
@login_required
def admin_download_upload(upload_id):
    """Admin download uploaded form"""
    if not current_user.has_permission('view_students'):
        abort(403)
    
    upload_log = FormUploadLog.query.get_or_404(upload_id)
    
    if not os.path.exists(upload_log.file_path):
        abort(404)
    
    return send_file(
        upload_log.file_path,
        as_attachment=True,
        download_name=upload_log.original_filename,
        mimetype=upload_log.mime_type
    )

@secure_forms.route('/api/admin/upload/<int:upload_id>/mark-processed', methods=['POST'])
@login_required
def admin_mark_processed(upload_id):
    """Mark upload as processed"""
    if not current_user.has_permission('edit_students'):
        return jsonify({'error': 'Permission denied'}), 403
    
    upload_log = FormUploadLog.query.get_or_404(upload_id)
    
    data = request.get_json()
    
    upload_log.processing_status = 'processed'
    upload_log.processing_notes = data.get('notes', '')
    upload_log.reviewed_by = current_user.username
    upload_log.reviewed_at = datetime.utcnow()
    upload_log.processed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Upload marked as processed'})

@secure_forms.route('/api/admin/create-secure-link', methods=['POST'])
@login_required
def admin_create_secure_link():
    """Create a new secure link and send email"""
    if not current_user.has_permission('edit_students'):
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        data = request.get_json()
        
        forms_service = SecureFormsService()
        secure_link = forms_service.create_secure_link_and_send_email(
            student_id=data['student_id'],
            form_type=data['form_type'],
            form_id=data.get('form_id'),
            expires_hours=data.get('expires_hours', 72),
            recipient_email=data.get('recipient_email')
        )
        
        return jsonify({
            'success': True,
            'message': 'Secure link created and email sent successfully',
            'link_id': secure_link.id,
            'upload_url': secure_link.upload_url
        })
        
    except Exception as e:
        current_app.logger.error(f"Error creating secure link: {str(e)}")
        return jsonify({'error': str(e)}), 500

@secure_forms.route('/admin/manual-upload')
@login_required
def admin_manual_upload():
    """Admin interface for manually uploading received contracts"""
    if not current_user.has_permission('edit_students'):
        abort(403)
    
    return render_template('secure_forms/admin_manual_upload.html')

@secure_forms.route('/api/admin/manual-upload', methods=['POST'])
@login_required
def process_manual_upload():
    """Process manually uploaded contract by admin"""
    if not current_user.has_permission('edit_students'):
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        # Get form data
        student_id = request.form.get('student_id')
        document_type = request.form.get('document_type')  # 'tuition_contract', 'financial_aid_form', 'other'
        document_description = request.form.get('document_description', '')
        contract_id = request.form.get('contract_id')  # Optional TuitionContract ID
        
        # Validate required fields
        if not student_id:
            return jsonify({'error': 'Student ID is required'}), 400
        
        if not document_type:
            return jsonify({'error': 'Document type is required'}), 400
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate student exists
        from models import Student, TuitionContract, FinancialRecord, AcademicYear
        student = Student.query.get(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Process upload using the storage service
        from storage_service import StorageService
        storage_service = StorageService()
        
        upload_result = storage_service.upload_file(
            uploaded_file,
            uploaded_file.filename,
            folder='manual_uploads',
            student_id=student_id,
            form_type=document_type
        )
        
        file_path = upload_result['path']
        stored_filename = upload_result['filename']
        file_hash = upload_result['file_hash']
        
        # Create upload log
        upload_log = FormUploadLog(
            secure_link_id=None,  # No secure link for manual uploads
            student_id=student_id,
            original_filename=upload_result['original_filename'],
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=upload_result['file_size'],
            mime_type=uploaded_file.content_type,
            file_hash=file_hash,
            upload_ip=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            document_category=document_type,
            document_description=document_description,
            auto_processed=True,  # Admin uploads are considered processed
            processing_status='processed',
            reviewed_by=current_user.username,
            reviewed_at=datetime.utcnow(),
            processed_at=datetime.utcnow()
        )
        
        db.session.add(upload_log)
        
        # Update related records based on document type
        current_year = AcademicYear.query.filter_by(is_active=True).first()
        
        if document_type == 'tuition_contract':
            # Update TuitionContract if contract_id provided
            if contract_id:
                contract = TuitionContract.query.get(contract_id)
                if contract and contract.student_id == student_id:
                    contract.print_upload_completed = True
                    contract.print_upload_date = datetime.utcnow()
                    contract.signed_contract_path = file_path
                    contract.contract_status = 'Signed'
                    
                    # Set receipt method tracking
                    contract.receipt_method = 'manual_upload'
                    contract.received_by_user = current_user.username
                    contract.receipt_notes = f'Manually uploaded by {current_user.full_name}. {document_description}' if document_description else f'Manually uploaded by {current_user.full_name}'
                    
                    upload_log.processing_notes = f"Linked to TuitionContract #{contract_id}"
            
            # Also update FinancialRecord
            if current_year:
                financial_record = FinancialRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=current_year.id
                ).first()
                
                if financial_record:
                    financial_record.enhanced_contract_signed = True
                    financial_record.enhanced_contract_signed_date = datetime.utcnow()
        
        elif document_type == 'financial_aid_form':
            # Update FinancialAidApplication if exists
            from models import FinancialAidApplication
            aid_app = FinancialAidApplication.query.filter_by(
                student_id=student_id
            ).order_by(FinancialAidApplication.application_date.desc()).first()
            
            if aid_app:
                aid_app.application_status = 'Submitted'
                aid_app.submission_date = datetime.utcnow()
                upload_log.processing_notes = f"Linked to FinancialAidApplication #{aid_app.id}"
            
            # Update FinancialRecord
            if current_year:
                financial_record = FinancialRecord.query.filter_by(
                    student_id=student_id,
                    academic_year_id=current_year.id
                ).first()
                
                if financial_record:
                    financial_record.financial_aid_form_received = True
                    financial_record.financial_aid_form_received_date = datetime.utcnow()
        
        db.session.commit()
        
        # Send notification email to relevant staff
        try:
            from email_service import EmailService
            email_service = EmailService()
            
            subject = f"Manual Upload: {document_type.replace('_', ' ').title()} - {student.student_name}"
            
            html_content = f"""
            <h3>Manual Document Upload</h3>
            
            <p><strong>Uploaded by:</strong> {current_user.full_name} ({current_user.username})</p>
            <p><strong>Student:</strong> {student.student_name} (ID: {student_id})</p>
            <p><strong>Division:</strong> {student.division}</p>
            <p><strong>Document Type:</strong> {document_type.replace('_', ' ').title()}</p>
            <p><strong>File:</strong> {upload_log.original_filename}</p>
            <p><strong>Size:</strong> {upload_log.file_size_formatted}</p>
            <p><strong>Upload Time:</strong> {upload_log.uploaded_at.strftime('%B %d, %Y at %I:%M %p')}</p>
            
            {f'<p><strong>Description:</strong> {document_description}</p>' if document_description else ''}
            
            <p>The document has been automatically processed and linked to the student's record.</p>
            """
            
            # Send to financial office
            admin_email = current_app.config.get('FINANCIAL_ADMIN_EMAIL', 'admin@school.edu')
            email_service.send_email(
                to_email=admin_email,
                subject=subject,
                html_content=html_content
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to send manual upload notification: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'{document_type.replace("_", " ").title()} uploaded and processed successfully',
            'upload_id': upload_log.id,
            'file_path': file_path
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Manual upload error: {str(e)}")
        return jsonify({'error': 'An error occurred during upload. Please try again.'}), 500

@secure_forms.route('/api/admin/students/search')
@login_required
def search_students():
    """Search students for manual upload form"""
    if not current_user.has_permission('view_students'):
        return jsonify({'error': 'Permission denied'}), 403
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'students': []})
    
    from models import Student
    students = Student.query.filter(
        db.or_(
            Student.student_name.ilike(f'%{query}%'),
            Student.student_first_name.ilike(f'%{query}%'),
            Student.student_last_name.ilike(f'%{query}%'),
            Student.id.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    student_list = []
    for student in students:
        student_list.append({
            'id': student.id,
            'name': student.student_name,
            'division': student.division,
            'status': student.status
        })
    
    return jsonify({'students': student_list})

@secure_forms.route('/api/admin/students/<student_id>/contracts')
@login_required
def get_student_contracts():
    """Get student's contracts for manual upload linking"""
    if not current_user.has_permission('view_students'):
        return jsonify({'error': 'Permission denied'}), 403
    
    from models import TuitionContract, AcademicYear
    contracts = TuitionContract.query.filter_by(
        student_id=student_id
    ).join(AcademicYear).order_by(AcademicYear.start_date.desc()).all()
    
    contract_list = []
    for contract in contracts:
        contract_list.append({
            'id': contract.id,
            'academic_year': contract.academic_year.year_label,
            'division': contract.division,
            'status': contract.contract_status,
            'amount': float(contract.final_tuition_amount) if contract.final_tuition_amount else 0,
            'contract_type': contract.contract_type
        })
    
    return jsonify({'contracts': contract_list})

# Enrollment Response Routes (COMMENTED OUT - duplicates enrollment_email.py routes)
# The enrollment email service creates tokens with form_type='enrollment_decision'
# but these routes were looking for form_type='enrollment_response', causing conflicts

# @secure_forms.route('/enrollment-response/<token>')
# def student_enrollment_response_form(token):
#     """Show enrollment decision response form to students"""
#     try:
#         from models import SecureFormToken, Student, AcademicYear
#         
#         # Validate token
#         token_data = SecureFormToken.query.filter_by(
#             token=token, 
#             form_type='enrollment_response',
#             is_used=False
#         ).first()
#         
#         if not token_data:
#             return render_template('secure_forms/invalid_link.html',
#                                  error='Invalid or expired enrollment response link')
#         
#         if token_data.expires_at < datetime.utcnow():
#             return render_template('secure_forms/invalid_link.html',
#                                  error='This enrollment response link has expired')
#         
#         # Get student and academic year info
#         token_metadata = token_data.token_metadata or {}
#         student_id = token_metadata.get('student_id')
#         academic_year_id = token_metadata.get('academic_year_id')
#         
#         if not student_id or not academic_year_id:
#             return render_template('secure_forms/invalid_link.html',
#                                  error='Invalid link data')
#         
#         student = Student.query.get(student_id)
#         academic_year = AcademicYear.query.get(academic_year_id)
#         
#         if not student or not academic_year:
#             return render_template('secure_forms/invalid_link.html',
#                                  error='Student or academic year not found')
#         
#         return render_template('enrollment_email/response_form.html',
#                              student=student,
#                              academic_year=academic_year,
#                              token=token,
#                              expires_at=token_data.expires_at)
#         
#     except Exception as e:
#         current_app.logger.error(f"Error showing enrollment response form: {str(e)}")
#         return render_template('secure_forms/invalid_link.html',
#                              error='An error occurred while loading the response form')

# @secure_forms.route('/api/enrollment-response/<token>', methods=['POST'])
# def process_student_enrollment_response(token):
#     """Process student's enrollment decision response"""
#     try:
#         data = request.get_json() if request.is_json else request.form
#         decision = data.get('decision')
#         
#         if not decision:
#             return jsonify({'error': 'Enrollment decision is required'}), 400
#         
#         # Process the response
#         from services.enrollment_email_service import EnrollmentDecisionEmailService
#         service = EnrollmentDecisionEmailService()
#         result = service.process_student_enrollment_response(token, decision)
#         
#         if result['success']:
#             return jsonify({
#                 'success': True,
#                 'message': f"Thank you! Your enrollment decision has been recorded: {result['enrollment_status']}",
#                 'student_name': result['student_name'],
#                 'enrollment_status': result['enrollment_status']
#             })
#         else:
#             return jsonify({'error': result['error']}), 400
#         
#     except Exception as e:
#         current_app.logger.error(f"Error processing student enrollment response: {str(e)}")
#         return jsonify({'error': 'An error occurred while processing your response'}), 500

# @secure_forms.route('/enrollment-response/<token>/success')
# def enrollment_response_success(token):
#     """Show success page after student responds to enrollment"""
#     try:
#         from models import SecureFormToken, Student
#         
#         # Get token info to show success message
#         token_data = SecureFormToken.query.filter_by(token=token).first()
#         
#         if not token_data or not token_data.is_used:
#             return redirect(url_for('secure_forms.student_enrollment_response_form', token=token))
#         
#         token_metadata = token_data.token_metadata or {}
#         student_id = token_metadata.get('student_id')
#         
#         student = Student.query.get(student_id) if student_id else None
#         
#         return render_template('enrollment_email/response_success.html',
#                              student=student,
#                              used_at=token_data.used_at)
#         
#     except Exception as e:
#         current_app.logger.error(f"Error showing enrollment response success page: {str(e)}")
#         return render_template('enrollment_email/response_success.html') 