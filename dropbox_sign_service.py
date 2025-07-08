"""
Dropbox Sign Service - eSignature integration for student management
Replaces OpenSign functionality with Dropbox Sign API
"""

import os
import base64
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from flask import current_app

try:
    from dropbox_sign import ApiClient, ApiException, Configuration, apis, models
    DROPBOX_SIGN_AVAILABLE = True
except ImportError:
    DROPBOX_SIGN_AVAILABLE = False

logger = logging.getLogger(__name__)

class DropboxSignService:
    """Service for integrating with Dropbox Sign e-signature platform"""
    
    def __init__(self):
        self.api_key = os.getenv('DROPBOX_SIGN_API_KEY')
        self.client_id = os.getenv('DROPBOX_SIGN_CLIENT_ID')
        self.test_mode = os.getenv('DROPBOX_SIGN_TEST_MODE', 'true').lower() == 'true'
        self.webhook_secret = os.getenv('DROPBOX_SIGN_WEBHOOK_SECRET')
        
        # Initialize configuration
        self.configuration = None
        if DROPBOX_SIGN_AVAILABLE and self.api_key:
            self.configuration = Configuration(username=self.api_key)
    
    def is_available(self):
        """Check if Dropbox Sign is properly configured"""
        return DROPBOX_SIGN_AVAILABLE and self.api_key and self.client_id
    
    def create_signature_request(self, title: str, subject: str, message: str, 
                               signers: List[Dict[str, Any]], file_data: bytes,
                               expire_days: int = 30) -> Dict[str, Any]:
        """Create a signature request for signing"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                # Create signers list
                signers_list = []
                for index, signer in enumerate(signers):
                    signers_list.append(
                        models.SubSignatureRequestSigner(
                            email_address=signer.get('email'),
                            name=signer.get('name'),
                            order=index
                        )
                    )
                
                # Create a temporary file for the upload
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(file_data)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Create signature request
                    data = models.SignatureRequestSendRequest(
                        title=title,
                        subject=subject,
                        message=message,
                        signers=signers_list,
                        files=[open(tmp_file_path, 'rb')],
                        test_mode=self.test_mode
                    )
                    
                    response = signature_request_api.signature_request_send(data)
                    
                    # Clean up temporary file
                    os.unlink(tmp_file_path)
                    
                    return {
                        'success': True,
                        'signature_request_id': response.signature_request.signature_request_id,
                        'signatures': response.signature_request.signatures,
                        'message': 'Signature request created successfully'
                    }
                    
                except Exception as e:
                    # Clean up temporary file on error
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)
                    raise e
                    
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error creating signature request: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def create_embedded_signature_request(self, title: str, subject: str, message: str,
                                        signers: List[Dict[str, Any]], file_data: bytes,
                                        expire_days: int = 30) -> Dict[str, Any]:
        """Create an embedded signature request for signing"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                # Create signers list
                signers_list = []
                for index, signer in enumerate(signers):
                    signers_list.append(
                        models.SubSignatureRequestSigner(
                            email_address=signer.get('email'),
                            name=signer.get('name'),
                            order=index
                        )
                    )
                
                # Create a temporary file for the upload
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(file_data)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Create embedded signature request
                    data = models.SignatureRequestCreateEmbeddedRequest(
                        client_id=self.client_id,
                        title=title,
                        subject=subject,
                        message=message,
                        signers=signers_list,
                        files=[open(tmp_file_path, 'rb')],
                        test_mode=self.test_mode
                    )
                    
                    response = signature_request_api.signature_request_create_embedded(data)
                    
                    # Clean up temporary file
                    os.unlink(tmp_file_path)
                    
                    return {
                        'success': True,
                        'signature_request_id': response.signature_request.signature_request_id,
                        'signatures': response.signature_request.signatures,
                        'message': 'Embedded signature request created successfully'
                    }
                    
                except Exception as e:
                    # Clean up temporary file on error
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)
                    raise e
                    
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error creating embedded signature request: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_embedded_sign_url(self, signature_id: str) -> Dict[str, Any]:
        """Get embedded sign URL for a signature"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                embedded_api = apis.EmbeddedApi(api_client)
                
                response = embedded_api.embedded_sign_url(signature_id=signature_id)
                
                return {
                    'success': True,
                    'sign_url': response.embedded.sign_url,
                    'expires_at': response.embedded.expires_at
                }
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error getting embedded sign URL: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_signature_request(self, signature_request_id: str) -> Dict[str, Any]:
        """Get signature request details and status"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                response = signature_request_api.signature_request_get(signature_request_id)
                
                return {
                    'success': True,
                    'signature_request': response.signature_request,
                    'status': response.signature_request.status_code
                }
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error getting signature request: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def download_files(self, signature_request_id: str, file_type: str = 'pdf') -> bytes:
        """Download signed files from a signature request"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                response = signature_request_api.signature_request_files(
                    signature_request_id=signature_request_id,
                    file_type=file_type
                )
                
                return response
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            raise Exception(f"Failed to download files: {str(e)}")
        except Exception as e:
            logger.error(f"Error downloading files: {str(e)}")
            raise e
    
    def send_reminder(self, signature_request_id: str, email_address: str) -> bool:
        """Send reminder to signer"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                data = models.SignatureRequestRemindRequest(
                    email_address=email_address
                )
                
                response = signature_request_api.signature_request_remind(
                    signature_request_id=signature_request_id,
                    signature_request_remind_request=data
                )
                
                return True
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error sending reminder: {str(e)}")
            return False
    
    def cancel_signature_request(self, signature_request_id: str) -> bool:
        """Cancel a signature request"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                signature_request_api = apis.SignatureRequestApi(api_client)
                
                response = signature_request_api.signature_request_cancel(
                    signature_request_id=signature_request_id
                )
                
                return True
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error canceling signature request: {str(e)}")
            return False
    
    def send_tuition_contract(self, student_data: Dict[str, Any], tuition_amount: float,
                            parent_email: str = None) -> Dict[str, Any]:
        """Create and send tuition contract for signature using Dropbox Sign"""
        try:
            # Generate PDF content using existing PDF service
            from pdf_service import pdf_service
            
            contract_path = pdf_service.generate_tuition_contract_pdf(
                student_data, tuition_amount, f"tuition_contract_{student_data.get('id', '')}"
            )
            
            if not contract_path:
                logger.error("Failed to generate PDF contract")
                return {'success': False, 'error': 'Failed to generate PDF contract'}
            
            # Read the generated PDF
            with open(contract_path, 'rb') as f:
                pdf_data = f.read()
            
            # Prepare signers
            signers = [
                {
                    'name': f"{student_data.get('first_name', '')} {student_data.get('last_name', '')}",
                    'email': student_data.get('email', '')
                }
            ]
            
            # Add parent if provided
            if parent_email:
                signers.append({
                    'name': f"Parent/Guardian of {student_data.get('first_name', '')}",
                    'email': parent_email
                })
            
            # Create document name
            document_name = f"Tuition Contract - {student_data.get('first_name', '')} {student_data.get('last_name', '')}"
            
            # Create the signature request
            result = self.create_embedded_signature_request(
                title=document_name,
                subject=document_name,
                message=f"Please review and sign the tuition contract for {student_data.get('first_name', '')} {student_data.get('last_name', '')}.",
                signers=signers,
                file_data=pdf_data,
                expire_days=30
            )
            
            # Clean up temporary PDF file
            if os.path.exists(contract_path):
                os.remove(contract_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending tuition contract: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature for security"""
        if not self.webhook_secret:
            logger.warning("No webhook secret configured")
            return False
        
        import hmac
        import hashlib
        
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def send_for_signature(self, document_path: str, signers: List[Dict[str, Any]],
                          template_id: str = None, folder_id: str = None) -> Dict[str, Any]:
        """Send document for signature (compatibility method for replacing OpenSign)"""
        try:
            # Read the document
            with open(document_path, 'rb') as f:
                file_data = f.read()
            
            # Extract filename for title
            filename = os.path.basename(document_path)
            title = f"Signature Request - {filename}"
            
            # Create embedded signature request
            result = self.create_embedded_signature_request(
                title=title,
                subject=title,
                message="Please review and sign this document.",
                signers=signers,
                file_data=file_data
            )
            
            if result.get('success'):
                return {
                    'success': True,
                    'document_id': result['signature_request_id'],
                    'message': 'Document sent for signature successfully'
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error sending document for signature: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information for testing connection"""
        if not self.is_available():
            raise Exception("Dropbox Sign is not properly configured")
        
        try:
            with ApiClient(configuration=self.configuration) as api_client:
                account_api = apis.AccountApi(api_client)
                
                response = account_api.account_get()
                
                return {
                    'account_id': response.account.account_id,
                    'email_address': response.account.email_address,
                    'quota_documents_remaining': response.account.quota_documents_remaining,
                    'quota_documents_used': response.account.quota_documents_used,
                    'quota_api_signature_requests_remaining': response.account.quota_api_signature_requests_remaining,
                    'quota_api_signature_requests_used': response.account.quota_api_signature_requests_used
                }
                
        except ApiException as e:
            logger.error(f"Dropbox Sign API error: {str(e)}")
            raise Exception(f"Failed to get account info: {str(e)}")
        except Exception as e:
            logger.error(f"Error getting account info: {str(e)}")
            raise e

# Global instance
dropbox_sign_service = DropboxSignService() 