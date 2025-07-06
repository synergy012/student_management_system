from flask import Blueprint, send_file, send_from_directory, abort, current_app
from flask_login import login_required
from utils.decorators import permission_required
import os
import mimetypes

files = Blueprint('files', __name__)

@files.route('/download/<path:filename>')
def download_file(filename):
    """Download a file from the uploads directory."""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            abort(404)
        
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            abort(404)
        
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        current_app.logger.error(f"Error downloading file {filename}: {str(e)}")
        abort(500)

@files.route('/attachments/<path:filename>')
@login_required
@permission_required('view_applications')
def serve_attachment(filename):
    """Serve an attachment file."""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            abort(404)
        
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            abort(404)
        
        # Determine content type
        mime_type = mimetypes.guess_type(filename)[0]
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # For images and PDFs, serve inline
        if mime_type.startswith('image/') or mime_type == 'application/pdf':
            return send_file(file_path, mimetype=mime_type)
        else:
            # For other files, force download
            return send_file(file_path, as_attachment=True, mimetype=mime_type)
    
    except Exception as e:
        current_app.logger.error(f"Error serving attachment {filename}: {str(e)}")
        abort(500)

@files.route('/attachments/<path:filename>/view')
@login_required
@permission_required('view_applications')
def view_attachment(filename):
    """View an attachment file inline."""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            abort(404)
        
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            abort(404)
        
        # Determine content type
        mime_type = mimetypes.guess_type(filename)[0]
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        # Always serve inline for viewing
        return send_file(file_path, mimetype=mime_type)
    
    except Exception as e:
        current_app.logger.error(f"Error viewing attachment {filename}: {str(e)}")
        abort(500) 