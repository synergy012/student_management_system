from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import (Student, AcademicYear, db, FinancialRecord, FinancialDocument)
from utils.decorators import permission_required
from datetime import datetime
import hashlib
import traceback

financial_documents = Blueprint('financial_documents', __name__)

@financial_documents.route('/api/financial/documents/upload', methods=['POST'])
@login_required
@permission_required('edit_students')
def upload_financial_document():
    """Upload a financial document for a specific financial record"""
    try:
        # Get form data
        financial_record_id = request.form.get('financial_record_id')
        document_type = request.form.get('document_type')
        description = request.form.get('description', '')
        
        # Validate required fields
        if not financial_record_id:
            return jsonify({'error': 'Financial record ID is required'}), 400
        
        if not document_type:
            return jsonify({'error': 'Document type is required'}), 400
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate financial record exists
        financial_record = FinancialRecord.query.get(financial_record_id)
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Get the student for additional validation
        student = financial_record.student
        if not student:
            return jsonify({'error': 'Student not found for this financial record'}), 404
        
        # Process upload using the storage service
        try:
            from storage_service import StorageService
            storage_service = StorageService()
            
            upload_result = storage_service.upload_file(
                uploaded_file,
                uploaded_file.filename,
                folder='financial_documents',
                student_id=str(student.id),
                form_type=document_type
            )
            
            file_path = upload_result['path']
            
        except Exception as e:
            current_app.logger.error(f"File upload failed: {str(e)}")
            return jsonify({'error': f'File upload failed: {str(e)}'}), 500
        
        # Create FinancialDocument record
        financial_document = FinancialDocument(
            financial_record_id=financial_record_id,
            document_type=document_type,
            filename=uploaded_file.filename,
            file_path=file_path,
            file_size=len(uploaded_file.read()),
            mime_type=uploaded_file.content_type,
            uploaded_by=current_user.username,
            description=description,
            encrypted=True
        )
        
        # Reset file pointer after reading for size
        uploaded_file.seek(0)
        
        # Generate checksum for security
        file_content = uploaded_file.read()
        checksum = hashlib.sha256(file_content).hexdigest()
        financial_document.checksum = checksum
        
        db.session.add(financial_document)
        
        # Update financial record based on document type
        if document_type == 'financial_aid_form':
            financial_record.financial_aid_form_received = True
            financial_record.financial_aid_form_received_date = datetime.utcnow()
        elif document_type == 'enrollment_contract':
            # Update both enhanced and enrollment contract fields for consistency
            financial_record.enhanced_contract_signed = True
            financial_record.enhanced_contract_signed_date = datetime.utcnow()
            financial_record.enrollment_contract_received = True
            financial_record.enrollment_contract_received_date = datetime.utcnow()
        
        db.session.commit()
        
        # Send notification email to relevant staff
        try:
            from email_service import EmailService
            email_service = EmailService()
            
            subject = f"Financial Document Uploaded - {student.student_name}"
            
            html_content = f"""
            <h3>Financial Document Upload</h3>
            
            <p><strong>Uploaded by:</strong> {current_user.full_name} ({current_user.username})</p>
            <p><strong>Student:</strong> {student.student_name} (ID: {student.id})</p>
            <p><strong>Division:</strong> {student.division}</p>
            <p><strong>Document Type:</strong> {document_type.replace('_', ' ').title()}</p>
            <p><strong>File:</strong> {uploaded_file.filename}</p>
            <p><strong>Size:</strong> {financial_document.file_size} bytes</p>
            <p><strong>Upload Time:</strong> {financial_document.uploaded_at.strftime('%B %d, %Y at %I:%M %p')}</p>
            
            {f'<p><strong>Description:</strong> {description}</p>' if description else ''}
            
            <p>The document has been securely stored and linked to the student's financial record.</p>
            """
            
            # Send to financial office
            admin_email = current_app.config.get('FINANCIAL_ADMIN_EMAIL', 'admin@school.edu')
            email_service.send_email(
                to_email=admin_email,
                subject=subject,
                html_content=html_content
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to send upload notification: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': f'{document_type.replace("_", " ").title()} uploaded successfully',
            'document_id': financial_document.id,
            'file_path': file_path
        })
        
    except Exception as e:
        current_app.logger.error(f"Error uploading financial document: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500



@financial_documents.route('/financial/records/<int:record_id>/documents')
@login_required
@permission_required('view_students')
def view_financial_documents(record_id):
    """View documents for a financial record"""
    financial_record = FinancialRecord.query.get_or_404(record_id)
    
    # Use the unified documents property that includes both manual and secure uploads
    documents = financial_record.all_documents
    
    return render_template('financial/documents.html',
                         financial_record=financial_record,
                         student=financial_record.student,
                         documents=documents)

@financial_documents.route('/api/financial/documents/<int:document_id>/download', methods=['GET'])
@login_required
@permission_required('view_students')
def download_financial_document(document_id):
    """Download a financial document"""
    try:
        document = FinancialDocument.query.get(document_id)
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if user has permission to view this document
        financial_record = document.financial_record
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Use storage service to serve the file
        try:
            from storage_service import StorageService
            storage_service = StorageService()
            
            return storage_service.serve_file(
                document.file_path,
                download_name=document.filename,
                mime_type=document.mime_type
            )
            
        except Exception as e:
            current_app.logger.error(f"Error serving document: {str(e)}")
            return jsonify({'error': 'Failed to download document'}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error downloading financial document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_documents.route('/api/financial/documents/<int:document_id>/delete', methods=['DELETE'])
@login_required
@permission_required('edit_students')
def delete_financial_document(document_id):
    """Delete a financial document"""
    try:
        document = FinancialDocument.query.get(document_id)
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Store document info for cleanup
        file_path = document.file_path
        document_type = document.document_type
        financial_record = document.financial_record
        
        # Delete from database first
        db.session.delete(document)
        
        # Update financial record status if needed
        if document_type == 'financial_aid_form':
            financial_record.financial_aid_form_received = False
            financial_record.financial_aid_form_received_date = None
        elif document_type == 'enrollment_contract':
            financial_record.enhanced_contract_signed = False
            financial_record.enhanced_contract_signed_date = None
            financial_record.enrollment_contract_received = False
            financial_record.enrollment_contract_received_date = None
        
        db.session.commit()
        
        # Clean up file from storage
        try:
            from storage_service import StorageService
            storage_service = StorageService()
            storage_service.delete_file(file_path)
        except Exception as e:
            current_app.logger.warning(f"Failed to delete file from storage: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'Document deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting financial document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_documents.route('/api/financial/documents/<int:document_id>/update', methods=['POST'])
@login_required
@permission_required('edit_students')
def update_financial_document(document_id):
    """Update financial document metadata"""
    try:
        document = FinancialDocument.query.get(document_id)
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        data = request.get_json()
        
        # Update allowed fields
        if 'description' in data:
            document.description = data['description']
        
        if 'document_type' in data:
            old_type = document.document_type
            document.document_type = data['document_type']
            
            # Update financial record status based on type change
            financial_record = document.financial_record
            
            # Remove old type status
            if old_type == 'financial_aid_form':
                financial_record.financial_aid_form_received = False
                financial_record.financial_aid_form_received_date = None
            elif old_type == 'enrollment_contract':
                financial_record.enhanced_contract_signed = False
                financial_record.enhanced_contract_signed_date = None
                financial_record.enrollment_contract_received = False
                financial_record.enrollment_contract_received_date = None
            
            # Set new type status
            if data['document_type'] == 'financial_aid_form':
                financial_record.financial_aid_form_received = True
                financial_record.financial_aid_form_received_date = datetime.utcnow()
            elif data['document_type'] == 'enrollment_contract':
                financial_record.enhanced_contract_signed = True
                financial_record.enhanced_contract_signed_date = datetime.utcnow()
                financial_record.enrollment_contract_received = True
                financial_record.enrollment_contract_received_date = datetime.utcnow()
        
        document.updated_at = datetime.utcnow()
        document.updated_by = current_user.username
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Document updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating financial document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@financial_documents.route('/api/financial/records/<int:record_id>/documents', methods=['GET'])
@login_required
@permission_required('view_students')
def get_financial_record_documents(record_id):
    """Get all documents for a financial record"""
    try:
        financial_record = FinancialRecord.query.get(record_id)
        if not financial_record:
            return jsonify({'error': 'Financial record not found'}), 404
        
        # Get all documents
        documents = financial_record.all_documents
        
        documents_data = []
        for doc in documents:
            doc_data = {
                'id': doc.id,
                'filename': doc.filename,
                'document_type': doc.document_type,
                'file_size': doc.file_size,
                'uploaded_at': doc.uploaded_at.isoformat() if hasattr(doc, 'uploaded_at') and doc.uploaded_at else None,
                'uploaded_by': doc.uploaded_by if hasattr(doc, 'uploaded_by') else None,
                'description': doc.description if hasattr(doc, 'description') else None,
                'source': 'manual' if hasattr(doc, 'financial_record_id') else 'secure_upload'
            }
            documents_data.append(doc_data)
        
        return jsonify({
            'success': True,
            'documents': documents_data,
            'total_count': len(documents_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting financial record documents: {str(e)}")
        return jsonify({'error': str(e)}), 500
