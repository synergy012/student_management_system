from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, send_file
from flask_login import login_required
from models import DivisionConfig, db
from extensions import mail
from utils.decorators import permission_required
from email_service import EmailService
from pdf_service import PDFService
from storage_service import StorageService
import subprocess
import sys
import time
import threading
import os
from datetime import datetime

settings = Blueprint('settings', __name__)

@settings.route('/settings')
@login_required
@permission_required('manage_users')
def settings_page():
    """Display the settings page."""
    # Get email configuration
    email_config = {
        'MAIL_SERVER': current_app.config.get('MAIL_SERVER', ''),
        'MAIL_PORT': current_app.config.get('MAIL_PORT', 587),
        'MAIL_USE_TLS': current_app.config.get('MAIL_USE_TLS', True),
        'MAIL_USE_SSL': current_app.config.get('MAIL_USE_SSL', False),
        'MAIL_USERNAME': current_app.config.get('MAIL_USERNAME', ''),
        'MAIL_DEFAULT_SENDER': current_app.config.get('MAIL_DEFAULT_SENDER', '')
    }
    
    # Get webhook configuration
    webhook_config = {
        'FORMS_WEBHOOK_SECRET': current_app.config.get('FORMS_WEBHOOK_SECRET', '')
    }
    
    # Get security configuration
    security_config = {
        'SECRET_KEY': current_app.config.get('SECRET_KEY', ''),
        'WTF_CSRF_SECRET_KEY': current_app.config.get('WTF_CSRF_SECRET_KEY', '')
    }
    
    # Get division configurations
    division_configs = {}
    for division in ['YZA', 'YOH', 'KOLLEL']:
        config = DivisionConfig.query.filter_by(division=division).first()
        if not config:
            # Create default config if it doesn't exist
            # Set default form IDs for each division
            default_form_ids = {'YZA': '1', 'YOH': '2', 'KOLLEL': '3'}
            config = DivisionConfig(
                division=division,
                form_id=default_form_ids.get(division, '1'),
                acceptance_email_body='',
                acceptance_email_subject=f'Acceptance to {division} Program',
                email_from_address=email_config['MAIL_DEFAULT_SENDER'],
                email_from_name='Yeshiva Administration'
            )
            db.session.add(config)
        division_configs[division] = config
    
    db.session.commit()
    
    # Get storage configuration
    storage_service = StorageService()
    storage_info = storage_service.get_storage_info()
    
    # Get Dropbox Sign configuration
    dropbox_sign_config = {
        'DROPBOX_SIGN_API_KEY': current_app.config.get('DROPBOX_SIGN_API_KEY', ''),
        'DROPBOX_SIGN_CLIENT_ID': current_app.config.get('DROPBOX_SIGN_CLIENT_ID', ''),
        'DROPBOX_SIGN_TEST_MODE': current_app.config.get('DROPBOX_SIGN_TEST_MODE', True),
        'DROPBOX_SIGN_WEBHOOK_SECRET': current_app.config.get('DROPBOX_SIGN_WEBHOOK_SECRET', '')
    }
    
    return render_template('settings.html', 
                         email_config=email_config,
                         webhook_config=webhook_config,
                         security_config=security_config,
                         division_configs=division_configs,
                         yza_config=division_configs.get('YZA'),
                         yoh_config=division_configs.get('YOH'),
                         kollel_config=division_configs.get('KOLLEL'),
                         storage_info=storage_info,
                         dropbox_sign_config=dropbox_sign_config)

@settings.route('/update-email-settings', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_email_settings():
    """Update email configuration."""
    try:
        # Update configuration
        current_app.config['MAIL_SERVER'] = request.form.get('mail_server', '')
        current_app.config['MAIL_PORT'] = int(request.form.get('mail_port', 587))
        current_app.config['MAIL_USE_TLS'] = request.form.get('mail_use_tls') == 'on'
        current_app.config['MAIL_USE_SSL'] = request.form.get('mail_use_ssl') == 'on'
        current_app.config['MAIL_USERNAME'] = request.form.get('mail_username', '')
        current_app.config['MAIL_PASSWORD'] = request.form.get('mail_password', '') if request.form.get('mail_password') else current_app.config.get('MAIL_PASSWORD', '')
        current_app.config['MAIL_DEFAULT_SENDER'] = request.form.get('mail_default_sender', '')
        
        # Update .env file
        env_content = []
        env_vars = {
            'MAIL_SERVER': current_app.config['MAIL_SERVER'],
            'MAIL_PORT': str(current_app.config['MAIL_PORT']),
            'MAIL_USE_TLS': str(current_app.config['MAIL_USE_TLS']),
            'MAIL_USE_SSL': str(current_app.config['MAIL_USE_SSL']),
            'MAIL_USERNAME': current_app.config['MAIL_USERNAME'],
            'MAIL_DEFAULT_SENDER': current_app.config['MAIL_DEFAULT_SENDER']
        }
        
        if request.form.get('mail_password'):
            env_vars['MAIL_PASSWORD'] = request.form.get('mail_password')
        
        # Read existing .env file
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    if '=' in line:
                        key = line.split('=')[0].strip()
                        if key not in env_vars:
                            env_content.append(line.rstrip())
        
        # Add/update email settings
        for key, value in env_vars.items():
            env_content.append(f'{key}={value}')
        
        # Write back to .env
        with open('.env', 'w') as f:
            f.write('\n'.join(env_content) + '\n')
        
        # Reinitialize mail
        mail.init_app(current_app)
        
        flash('Email settings updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating email settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-webhook-settings', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_webhook_settings():
    """Update webhook configuration."""
    try:
        webhook_secret = request.form.get('webhook_secret', '')
        
        # Update configuration
        current_app.config['FORMS_WEBHOOK_SECRET'] = webhook_secret
        
        # Update .env file
        env_content = []
        
        # Read existing .env file
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    if '=' in line:
                        key = line.split('=')[0].strip()
                        if key != 'FORMS_WEBHOOK_SECRET':
                            env_content.append(line.rstrip())
        
        # Add webhook secret
        env_content.append(f'FORMS_WEBHOOK_SECRET={webhook_secret}')
        
        # Write back to .env
        with open('.env', 'w') as f:
            f.write('\n'.join(env_content) + '\n')
        
        flash('Webhook settings updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating webhook settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-security-settings', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_security_settings():
    """Update security configuration."""
    try:
        secret_key = request.form.get('secret_key', '')
        
        if secret_key:
            # Update configuration
            current_app.config['SECRET_KEY'] = secret_key
            
            # Update .env file
            env_content = []
            
            # Read existing .env file
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        if '=' in line:
                            key = line.split('=')[0].strip()
                            if key != 'SECRET_KEY':
                                env_content.append(line.rstrip())
            
            # Add secret key
            env_content.append(f'SECRET_KEY={secret_key}')
            
            # Write back to .env
            with open('.env', 'w') as f:
                f.write('\n'.join(env_content) + '\n')
            
            flash('Security settings updated successfully! The application should be restarted for changes to take effect.', 'warning')
        else:
            flash('Secret key cannot be empty!', 'error')
    except Exception as e:
        flash(f'Error updating security settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-storage-settings', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_storage_settings():
    """Update storage configuration."""
    try:
        storage_backend = request.form.get('storage_backend', 'local')
        dropbox_token = request.form.get('dropbox_access_token', '')
        dropbox_folder = request.form.get('dropbox_folder_prefix', '/StudentManagement')
        
        # Update storage preference in database
        storage_service = StorageService()
        storage_service.set_storage_preference(storage_backend)
        
        # Update environment variables if provided
        env_content = []
        env_vars = {}
        
        if dropbox_token:
            env_vars['DROPBOX_ACCESS_TOKEN'] = dropbox_token
        if dropbox_folder:
            env_vars['DROPBOX_FOLDER_PREFIX'] = dropbox_folder
        
        if env_vars:
            # Read existing .env file
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        if '=' in line:
                            key = line.split('=')[0].strip()
                            if key not in env_vars:
                                env_content.append(line.rstrip())
            
            # Add/update storage settings
            for key, value in env_vars.items():
                env_content.append(f'{key}={value}')
            
            # Write back to .env
            with open('.env', 'w') as f:
                f.write('\n'.join(env_content) + '\n')
            
            # Update current app config
            current_app.config.update(env_vars)
        
        flash(f'Storage settings updated successfully! Now using {storage_backend} storage.', 'success')
        
        # Test connection if Dropbox is selected
        if storage_backend == 'dropbox':
            storage_service = StorageService()  # Reinitialize with new settings
            if storage_service.is_dropbox_available():
                flash('Dropbox connection verified successfully!', 'success')
            else:
                flash('Warning: Dropbox connection could not be verified. Please check your access token.', 'warning')
        
    except Exception as e:
        flash(f'Error updating storage settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-dropbox-sign-settings', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_dropbox_sign_settings():
    """Update Dropbox Sign configuration."""
    try:
        api_key = request.form.get('dropbox_sign_api_key', '')
        client_id = request.form.get('dropbox_sign_client_id', '')
        test_mode = request.form.get('dropbox_sign_test_mode') == 'on'
        webhook_secret = request.form.get('dropbox_sign_webhook_secret', '')
        
        # Update configuration
        current_app.config['DROPBOX_SIGN_API_KEY'] = api_key
        current_app.config['DROPBOX_SIGN_CLIENT_ID'] = client_id
        current_app.config['DROPBOX_SIGN_TEST_MODE'] = test_mode
        current_app.config['DROPBOX_SIGN_WEBHOOK_SECRET'] = webhook_secret
        
        # Update .env file
        env_content = []
        env_vars = {
            'DROPBOX_SIGN_API_KEY': api_key,
            'DROPBOX_SIGN_CLIENT_ID': client_id,
            'DROPBOX_SIGN_TEST_MODE': str(test_mode).lower(),
            'DROPBOX_SIGN_WEBHOOK_SECRET': webhook_secret
        }
        
        # Read existing .env file
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    if '=' in line:
                        key = line.split('=')[0].strip()
                        if key not in env_vars:
                            env_content.append(line.rstrip())
        
        # Add/update Dropbox Sign settings
        for key, value in env_vars.items():
            env_content.append(f'{key}={value}')
        
        # Write back to .env
        with open('.env', 'w') as f:
            f.write('\n'.join(env_content) + '\n')
        
        flash('Dropbox Sign settings updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating Dropbox Sign settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/test-dropbox-sign-connection', methods=['POST'])
@login_required
@permission_required('manage_users')
def test_dropbox_sign_connection():
    """Test Dropbox Sign API connection."""
    try:
        from dropbox_sign_service import DropboxSignService
        
        # Initialize service with current config
        service = DropboxSignService()
        
        # Test connection by getting account info
        account_info = service.get_account_info()
        
        if account_info:
            return jsonify({
                'success': True,
                'message': f'Connected successfully! Account: {account_info.get("email_address", "Unknown")}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not retrieve account information'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings.route('/dropbox-sign-quota', methods=['GET'])
@login_required
@permission_required('manage_users')
def get_dropbox_sign_quota():
    """Get Dropbox Sign API quota information."""
    try:
        from dropbox_sign_service import DropboxSignService
        
        # Initialize service with current config
        service = DropboxSignService()
        
        # Get account info including quota
        account_info = service.get_account_info()
        
        if account_info:
            return jsonify({
                'success': True,
                'quota': {
                    'documents_used': account_info.get('quota_documents_used', 0),
                    'documents_remaining': account_info.get('quota_documents_remaining', 0),
                    'api_requests_used': account_info.get('quota_api_signature_requests_used', 0),
                    'api_requests_remaining': account_info.get('quota_api_signature_requests_remaining', 0)
                },
                'account_email': account_info.get('email_address', 'Unknown')
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not retrieve account information'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings.route('/test-dropbox-connection', methods=['POST'])
@login_required
@permission_required('manage_users')
def test_dropbox_connection():
    """Test Dropbox connection."""
    try:
        storage_service = StorageService()
        result = storage_service.dropbox_service.test_connection()
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': f"Connected to Dropbox account: {result['name']} ({result['email']})",
                'account_info': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@settings.route('/upload-division-form/<division>', methods=['POST'])
@login_required
@permission_required('manage_users')
def upload_division_form(division):
    """Redirect to new PDF Templates system."""
    flash('Form template management has been moved to the PDF Templates system. Please upload your forms there.', 'info')
    return redirect(url_for('pdf_templates.template_manager'))

@settings.route('/download-division-form/<division>/<form_type>')
@login_required
@permission_required('manage_users')
def download_division_form(division, form_type):
    """Redirect to new PDF Templates system."""
    flash('Form templates are now managed in the PDF Templates system.', 'info')
    return redirect(url_for('pdf_templates.template_manager'))

@settings.route('/update-division-email/<division>', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_division_email(division):
    """Update division-specific email settings."""
    try:
        config = DivisionConfig.query.filter_by(division=division).first()
        if not config:
            # Set default form IDs for each division
            default_form_ids = {'YZA': '1', 'YOH': '2', 'KOLLEL': '3'}
            config = DivisionConfig(
                division=division,
                form_id=default_form_ids.get(division, '1')
            )
            db.session.add(config)
        
        config.email_from_address = request.form.get('email_from_address', '')
        config.email_from_name = request.form.get('email_from_name', '')
        config.email_reply_to = request.form.get('email_reply_to', '')
        
        db.session.commit()
        flash(f'{division} email settings updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating {division} email settings: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-acceptance-template/<division>', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_acceptance_template(division):
    """Update division-specific acceptance email template."""
    try:
        config = DivisionConfig.query.filter_by(division=division).first()
        if not config:
            # Set default form IDs for each division
            default_form_ids = {'YZA': '1', 'YOH': '2', 'KOLLEL': '3'}
            config = DivisionConfig(
                division=division,
                form_id=default_form_ids.get(division, '1')
            )
            db.session.add(config)
        
        config.acceptance_email_body = request.form.get('template', '')
        
        db.session.commit()
        flash(f'{division} acceptance email template updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating {division} acceptance email template: {str(e)}', 'error')
    
    return redirect(url_for('settings.settings_page'))

@settings.route('/update-pdf-template/<division>', methods=['POST'])
@login_required
@permission_required('manage_users')
def update_pdf_template(division):
    """Redirect to new PDF Templates system."""
    flash('PDF template configuration has been moved to the PDF Templates system. All template settings are now managed there.', 'info')
    return redirect(url_for('pdf_templates.template_manager'))

@settings.route('/api/division/<division>/email-config', methods=['GET', 'POST'])
@login_required
@permission_required('manage_users')
def manage_email_config(division):
    """API endpoint to manage division email configuration."""
    try:
        if request.method == 'GET':
            config = DivisionConfig.query.filter_by(division=division).first()
            if not config:
                return jsonify({
                    'division': division,
                    'from_email': current_app.config.get('MAIL_DEFAULT_SENDER', ''),
                    'from_name': 'Yeshiva Administration',
                    'acceptance_email_subject': f'Acceptance to {division} Program',
                    'acceptance_email_template': ''
                })
            
            return jsonify({
                'division': config.division,
                'from_email': config.email_from_address,
                'from_name': config.email_from_name,
                'acceptance_email_subject': config.acceptance_email_subject,
                'acceptance_email_template': config.acceptance_email_body
            })
        
        else:  # POST
            data = request.get_json()
            
            config = DivisionConfig.query.filter_by(division=division).first()
            if not config:
                # Set default form IDs for each division
                default_form_ids = {'YZA': '1', 'YOH': '2', 'KOLLEL': '3'}
                config = DivisionConfig(
                    division=division,
                    form_id=default_form_ids.get(division, '1')
                )
                db.session.add(config)
            
            if 'from_email' in data:
                config.email_from_address = data['from_email']
            if 'from_name' in data:
                config.email_from_name = data['from_name']
            if 'acceptance_email_subject' in data:
                config.acceptance_email_subject = data['acceptance_email_subject']
            if 'acceptance_email_template' in data:
                config.acceptance_email_body = data['acceptance_email_template']
            
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Configuration updated'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing email config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@settings.route('/clear-restart-flag', methods=['POST'])
@login_required
def clear_restart_flag():
    """Clear the restart flag file."""
    if os.path.exists('restart_in_progress.flag'):
        os.remove('restart_in_progress.flag')
    return '', 204

@settings.route('/restart-application', methods=['POST'])
@login_required
@permission_required('manage_users')
def restart_application():
    """Restart the Flask application."""
    try:
        # Create a flag file to indicate restart is in progress
        with open('restart_in_progress.flag', 'w') as f:
            f.write(str(time.time()))
        
        # Function to restart the app after a delay
        def delayed_restart():
            time.sleep(2)  # Give time for the response to be sent
            
            # Try to restart the application
            try:
                # For development server
                if current_app.debug:
                    # Touch a Python file to trigger reload
                    os.utime('app.py', None)
                else:
                    # For production, you might want to use a process manager
                    # This is a simple restart by replacing the current process
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                current_app.logger.error(f"Error during restart: {str(e)}")
                # Clean up the flag file if restart fails
                if os.path.exists('restart_in_progress.flag'):
                    os.remove('restart_in_progress.flag')
        
        # Start the restart in a background thread
        restart_thread = threading.Thread(target=delayed_restart)
        restart_thread.daemon = True
        restart_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Application restart initiated. Please wait a moment and refresh the page.'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@settings.route('/test-pdf-generation')
@login_required
@permission_required('manage_users')
def test_pdf_generation():
    """Test PDF generation with current settings."""
    try:
        # Get division from query parameter
        division = request.args.get('division', 'YZA')
        
        # Get division config
        config = DivisionConfig.query.filter_by(division=division).first()
        
        # Generate test PDF
        pdf_service = PDFService()
        
        # Test content
        test_content = f"""Dear Student,

This is a test PDF generation for the {division} division.

This PDF demonstrates the following features:
• Letterhead configuration
• Custom margins
• Font settings
• Line spacing
• Footer text

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

Best regards,
Yeshiva Administration"""
        
        # Generate PDF
        pdf_buffer = pdf_service.generate_acceptance_letter_pdf(
            content=test_content,
            student_name="Test Student",
            division=division,
            config=config
        )
        
        # Send the PDF
        from flask import send_file
        import io
        
        return send_file(
            io.BytesIO(pdf_buffer),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'test_pdf_{division}_{int(time.time())}.pdf'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error generating test PDF: {str(e)}")
        flash(f'Error generating test PDF: {str(e)}', 'error')
        return redirect(url_for('settings.settings_page'))

@settings.route('/send-test-emails/<email>')
@login_required
@permission_required('manage_users')
def send_test_emails(email):
    """Send test emails to verify configuration."""
    results = []
    
    # Test 1: Basic email functionality
    try:
        from flask_mail import Message
        msg = Message(
            'Test Email - Basic Functionality',
            recipients=[email],
            body='This is a basic test email to verify email configuration is working.'
        )
        mail.send(msg)
        results.append({'test': 'Basic Email', 'status': 'success', 'message': 'Email sent successfully'})
    except Exception as e:
        results.append({'test': 'Basic Email', 'status': 'error', 'message': str(e)})
    
    # Test 2: Email with HTML content
    try:
        msg = Message(
            'Test Email - HTML Content',
            recipients=[email],
            html='<h1>HTML Email Test</h1><p>This email contains <strong>HTML content</strong>.</p>'
        )
        mail.send(msg)
        results.append({'test': 'HTML Email', 'status': 'success', 'message': 'HTML email sent successfully'})
    except Exception as e:
        results.append({'test': 'HTML Email', 'status': 'error', 'message': str(e)})
    
    # Test 3: Division-specific email templates
    for division in ['YZA', 'YOH', 'KOLLEL']:
        try:
            config = DivisionConfig.query.filter_by(division=division).first()
            if config and config.acceptance_email_body:
                email_service = EmailService()
                email_content = email_service.generate_acceptance_email(
                    student_name="Test Student",
                    division=division,
                    email_template=config.acceptance_email_body
                )
                
                msg = Message(
                    f'Test Email - {division} Template',
                    recipients=[email],
                    body=email_content['body'],
                    sender=(config.email_from_name, config.email_from_address) if config.email_from_address else None
                )
                mail.send(msg)
                results.append({'test': f'{division} Template', 'status': 'success', 'message': 'Template email sent successfully'})
            else:
                results.append({'test': f'{division} Template', 'status': 'skipped', 'message': 'No template configured'})
        except Exception as e:
            results.append({'test': f'{division} Template', 'status': 'error', 'message': str(e)})
    
    return jsonify({
        'success': True,
        'results': results,
        'summary': f"Sent test emails to {email}"
    })

@settings.route('/api/divisions/<division>/email-recipient-settings', methods=['GET', 'PUT'])
@login_required
@permission_required('manage_users')
def manage_email_recipient_settings(division):
    """API endpoint to manage email recipient settings for a division."""
    try:
        if request.method == 'GET':
            config = DivisionConfig.query.filter_by(division=division).first()
            if not config:
                # Return default settings
                return jsonify({
                    'success': True,
                    'settings': {
                                'acceptance_email_default_recipients': ['student'],
        'financial_aid_email_default_recipients': ['student'],
        'tuition_contract_email_default_recipients': ['student'],
        'enhanced_contract_email_default_recipients': ['father', 'mother'],
        'general_email_default_recipients': ['student']
                    }
                })
            
            return jsonify({
                'success': True,
                'settings': {
                            'acceptance_email_default_recipients': config.acceptance_email_default_recipients or ['student'],
        'financial_aid_email_default_recipients': config.financial_aid_email_default_recipients or ['student'],
        'tuition_contract_email_default_recipients': config.tuition_contract_email_default_recipients or ['student'],
        'enhanced_contract_email_default_recipients': config.enhanced_contract_email_default_recipients or ['father', 'mother'],
        'general_email_default_recipients': config.general_email_default_recipients or ['student']
                }
            })
        
        else:  # PUT
            data = request.get_json()
            email_type = data.get('email_type')
            recipients = data.get('recipients', [])
            
            # Validate email type
            valid_email_types = ['acceptance_email', 'financial_aid_email', 'tuition_contract_email', 'enhanced_contract_email', 'general_email']
            if email_type not in valid_email_types:
                return jsonify({'success': False, 'error': 'Invalid email type'}), 400
            
            # Validate recipients
            valid_recipients = ['student', 'father', 'mother']
            if not recipients or not all(r in valid_recipients for r in recipients):
                return jsonify({'success': False, 'error': 'Invalid recipients'}), 400
            
            # Get or create config
            config = DivisionConfig.query.filter_by(division=division).first()
            if not config:
                # Set default form IDs for each division
                default_form_ids = {'YZA': '1', 'YOH': '2', 'KOLLEL': '3'}
                config = DivisionConfig(
                    division=division,
                    form_id=default_form_ids.get(division, '1')
                )
                db.session.add(config)
            
            # Update the specific email type recipients
            field_name = f'{email_type}_default_recipients'
            setattr(config, field_name, recipients)
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'{email_type} recipients updated for {division}',
                'recipients': recipients
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing email recipient settings: {str(e)}")
        return jsonify({'error': str(e)}), 500 
