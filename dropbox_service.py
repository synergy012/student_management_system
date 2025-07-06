"""
Dropbox Storage Service - Secure cloud storage integration
Maintains all security features while using Dropbox for unlimited storage
"""

import os
import hashlib
from datetime import datetime
from flask import current_app

try:
    import dropbox
    from dropbox.exceptions import AuthError, ApiError
    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

class DropboxService:
    def __init__(self):
        self.access_token = current_app.config.get('DROPBOX_ACCESS_TOKEN')
        self.folder_prefix = current_app.config.get('DROPBOX_FOLDER_PREFIX', '/StudentManagement')
        self.client = None
        
        if DROPBOX_AVAILABLE and self.access_token:
            try:
                self.client = dropbox.Dropbox(self.access_token)
                # Test connection
                self.client.users_get_current_account()
                current_app.logger.info("Dropbox connection established successfully")
            except AuthError as e:
                current_app.logger.error(f"Dropbox authentication failed: {str(e)}")
                self.client = None
            except Exception as e:
                current_app.logger.error(f"Dropbox connection failed: {str(e)}")
                self.client = None
    
    def is_available(self):
        """Check if Dropbox is properly configured and available"""
        return DROPBOX_AVAILABLE and self.client is not None
    
    def upload_file(self, file_data, remote_path, overwrite=True):
        """Upload file to Dropbox"""
        if not self.is_available():
            raise Exception("Dropbox is not available")
        
        try:
            # Ensure remote path starts with folder prefix
            if not remote_path.startswith(self.folder_prefix):
                remote_path = f"{self.folder_prefix}/{remote_path.lstrip('/')}"
            
            # Create folders if they don't exist
            self._ensure_folder_exists(os.path.dirname(remote_path))
            
            # Handle file data
            if hasattr(file_data, 'read'):
                file_content = file_data.read()
                file_data.seek(0)  # Reset file pointer
            else:
                file_content = file_data
            
            # Upload mode
            mode = dropbox.files.WriteMode.overwrite if overwrite else dropbox.files.WriteMode.add
            
            # Upload file
            result = self.client.files_upload(
                file_content,
                remote_path,
                mode=mode,
                autorename=True
            )
            
            # Get file metadata
            metadata = {
                'path': result.path_display,
                'size': result.size,
                'hash': result.content_hash,
                'modified': result.server_modified,
                'id': result.id
            }
            
            current_app.logger.info(f"File uploaded to Dropbox: {remote_path}")
            return metadata
            
        except ApiError as e:
            current_app.logger.error(f"Dropbox API error uploading {remote_path}: {str(e)}")
            raise Exception(f"Failed to upload file to Dropbox: {str(e)}")
        except Exception as e:
            current_app.logger.error(f"Error uploading to Dropbox {remote_path}: {str(e)}")
            raise
    
    def download_file(self, remote_path):
        """Download file from Dropbox"""
        if not self.is_available():
            raise Exception("Dropbox is not available")
        
        try:
            # Ensure remote path starts with folder prefix
            if not remote_path.startswith(self.folder_prefix):
                remote_path = f"{self.folder_prefix}/{remote_path.lstrip('/')}"
            
            metadata, response = self.client.files_download(remote_path)
            return response.content
            
        except ApiError as e:
            current_app.logger.error(f"Dropbox API error downloading {remote_path}: {str(e)}")
            raise Exception(f"Failed to download file from Dropbox: {str(e)}")
        except Exception as e:
            current_app.logger.error(f"Error downloading from Dropbox {remote_path}: {str(e)}")
            raise
    
    def test_connection(self):
        """Test Dropbox connection and return account info"""
        if not DROPBOX_AVAILABLE:
            return {'error': 'Dropbox SDK not installed'}
        
        if not self.access_token:
            return {'error': 'No access token configured'}
        
        try:
            client = dropbox.Dropbox(self.access_token)
            account = client.users_get_current_account()
            
            return {
                'success': True,
                'account_id': account.account_id,
                'name': account.name.display_name,
                'email': account.email,
                'country': account.country
            }
            
        except AuthError as e:
            return {'error': f'Authentication failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Connection failed: {str(e)}'}
    
    def get_storage_usage(self):
        """Get Dropbox storage usage information"""
        if not self.is_available():
            return {'error': 'Dropbox not available'}
        
        try:
            usage = self.client.users_get_space_usage()
            
            return {
                'used': usage.used,
                'allocated': usage.allocation.get_individual().allocated,
                'used_formatted': self._format_bytes(usage.used),
                'allocated_formatted': self._format_bytes(usage.allocation.get_individual().allocated)
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting Dropbox storage usage: {str(e)}")
            return {'error': str(e)}
    
    def _ensure_folder_exists(self, folder_path):
        """Ensure folder exists in Dropbox, create if it doesn't"""
        if not folder_path or folder_path == '/':
            return
        
        try:
            self.client.files_get_metadata(folder_path)
        except ApiError:
            # Folder doesn't exist, create it
            try:
                self.client.files_create_folder_v2(folder_path)
                current_app.logger.info(f"Created Dropbox folder: {folder_path}")
            except ApiError as e:
                if 'path/conflict/folder' not in str(e):
                    current_app.logger.error(f"Error creating Dropbox folder {folder_path}: {str(e)}")
                    raise
    
    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
