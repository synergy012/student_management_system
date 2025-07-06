"""
Unified Storage Service - Handles both local and cloud storage
Allows users to choose storage backend through admin settings
"""

import os
import hashlib
import shutil
from datetime import datetime
from flask import current_app
from werkzeug.utils import secure_filename
from dropbox_service import DropboxService
from models import db, DivisionConfig

class StorageService:
    def __init__(self):
        self.dropbox_service = DropboxService()
        self._storage_preference = None
    
    @property
    def storage_preference(self):
        """Get current storage preference from database or config"""
        if self._storage_preference is None:
            # Try to get from database first (user setting)
            try:
                config = DivisionConfig.query.filter_by(
                    division='SYSTEM',
                    config_key='storage_backend'
                ).first()
                
                if config:
                    self._storage_preference = config.config_value
                else:
                    # Fall back to environment variable
                    self._storage_preference = 'dropbox' if current_app.config.get('USE_DROPBOX_STORAGE') else 'local'
            except:
                # If database not available, use config
                self._storage_preference = 'dropbox' if current_app.config.get('USE_DROPBOX_STORAGE') else 'local'
        
        return self._storage_preference
    
    def set_storage_preference(self, preference):
        """Set storage preference and save to database"""
        if preference not in ['local', 'dropbox']:
            raise ValueError("Storage preference must be 'local' or 'dropbox'")
        
        # Save to database
        config = DivisionConfig.query.filter_by(
            division='SYSTEM',
            config_key='storage_backend'
        ).first()
        
        if not config:
            config = DivisionConfig(
                division='SYSTEM',
                config_key='storage_backend',
                config_value=preference,
                description='File storage backend preference'
            )
            db.session.add(config)
        else:
            config.config_value = preference
        
        db.session.commit()
        self._storage_preference = preference
        
        current_app.logger.info(f"Storage preference changed to: {preference}")
    
    def is_dropbox_available(self):
        """Check if Dropbox is properly configured"""
        return self.dropbox_service.is_available()
    
    def upload_file(self, file_data, filename, folder='secure_forms', 
                   student_id=None, form_type=None, preserve_extension=True):
        """
        Upload file using the configured storage backend
        
        Args:
            file_data: File data (bytes or file-like object)
            filename: Original filename
            folder: Storage folder/category
            student_id: Student ID for organized storage
            form_type: Form type for organized storage
            preserve_extension: Whether to preserve original file extension
        
        Returns:
            dict: Upload result with storage path and metadata
        """
        # Generate secure filename
        secure_name = secure_filename(filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Build organized path
        path_parts = [folder]
        if student_id:
            path_parts.append(str(student_id))
        if form_type:
            path_parts.append(form_type)
        
        # Generate unique filename
        if preserve_extension:
            name, ext = os.path.splitext(secure_name)
            stored_filename = f"{timestamp}_{name}{ext}"
        else:
            stored_filename = f"{timestamp}_{secure_name}"
        
        path_parts.append(stored_filename)
        relative_path = '/'.join(path_parts)
        
        # Calculate file hash for integrity
        if hasattr(file_data, 'read'):
            file_content = file_data.read()
            file_data.seek(0)  # Reset file pointer
        else:
            file_content = file_data
        
        file_hash = hashlib.sha256(file_content).hexdigest()
        file_size = len(file_content)
        
        try:
            if self.storage_preference == 'dropbox' and self.is_dropbox_available():
                # Upload to Dropbox
                metadata = self.dropbox_service.upload_file(file_content, relative_path)
                
                return {
                    'success': True,
                    'storage_type': 'dropbox',
                    'path': relative_path,
                    'dropbox_path': metadata['path'],
                    'filename': stored_filename,
                    'original_filename': filename,
                    'file_size': file_size,
                    'file_hash': file_hash,
                    'dropbox_hash': metadata.get('hash'),
                    'uploaded_at': datetime.utcnow()
                }
            else:
                # Upload to local storage
                local_folder = os.path.join(current_app.root_path, 'uploads', folder)
                if student_id:
                    local_folder = os.path.join(local_folder, str(student_id))
                if form_type:
                    local_folder = os.path.join(local_folder, form_type)
                
                # Ensure directory exists
                os.makedirs(local_folder, exist_ok=True)
                
                local_path = os.path.join(local_folder, stored_filename)
                
                # Write file
                with open(local_path, 'wb') as f:
                    f.write(file_content)
                
                return {
                    'success': True,
                    'storage_type': 'local',
                    'path': relative_path,
                    'local_path': local_path,
                    'filename': stored_filename,
                    'original_filename': filename,
                    'file_size': file_size,
                    'file_hash': file_hash,
                    'uploaded_at': datetime.utcnow()
                }
                
        except Exception as e:
            current_app.logger.error(f"Storage upload error: {str(e)}")
            raise Exception(f"Failed to upload file: {str(e)}")
    
    def download_file(self, storage_path, storage_type=None):
        """
        Download file from storage
        
        Args:
            storage_path: Path to file in storage
            storage_type: Force specific storage type, or auto-detect
        
        Returns:
            bytes: File content
        """
        if storage_type is None:
            storage_type = self.storage_preference
        
        try:
            if storage_type == 'dropbox':
                return self.dropbox_service.download_file(storage_path)
            else:
                # Local storage
                if not storage_path.startswith('/'):
                    local_path = os.path.join(current_app.root_path, 'uploads', storage_path)
                else:
                    local_path = storage_path
                
                with open(local_path, 'rb') as f:
                    return f.read()
                    
        except Exception as e:
            current_app.logger.error(f"Storage download error: {str(e)}")
            raise Exception(f"Failed to download file: {str(e)}")
    
    def get_storage_info(self):
        """
        Get information about current storage configuration
        
        Returns:
            dict: Storage information
        """
        info = {
            'current_backend': self.storage_preference,
            'dropbox_available': self.is_dropbox_available(),
            'local_available': True  # Local storage is always available
        }
        
        # Add Dropbox-specific info if available
        if self.is_dropbox_available():
            dropbox_info = self.dropbox_service.test_connection()
            info['dropbox_account'] = dropbox_info
            
            if dropbox_info.get('success'):
                usage_info = self.dropbox_service.get_storage_usage()
                info['dropbox_usage'] = usage_info
        
        # Add local storage info
        try:
            upload_folder = os.path.join(current_app.root_path, 'uploads')
            if os.path.exists(upload_folder):
                total_size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(upload_folder)
                    for filename in filenames
                )
                info['local_storage_used'] = total_size
                info['local_storage_used_formatted'] = self._format_bytes(total_size)
            else:
                info['local_storage_used'] = 0
                info['local_storage_used_formatted'] = '0 B'
        except Exception as e:
            info['local_storage_error'] = str(e)
        
        return info
    
    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
