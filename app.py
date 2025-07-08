from flask import Flask, jsonify, request, render_template_string, render_template
from flask_login import current_user
from flask_mail import Message
from datetime import datetime
import hmac
import hashlib
import os
import json
import logging
import traceback
from logging.handlers import RotatingFileHandler
from logging_system import LogManager, PerformanceLogger, AuditLogger
from dotenv import load_dotenv
from config import config
from extensions import db, login_manager, mail, migrate
from models import User, Permission, init_db
from auth import auth as auth_blueprint
from main import main as main_blueprint
from flask_migrate import upgrade

# Import new blueprints
from blueprints.core import core as core_blueprint
from blueprints.students import students as students_blueprint
from blueprints.applications import applications as applications_blueprint
from blueprints.webhooks import webhooks as webhooks_blueprint
from blueprints.academic import academic as academic_blueprint
from blueprints.settings import settings as settings_blueprint
from blueprints.kollel import kollel as kollel_blueprint
from blueprints.dormitories import dormitories as dormitories_blueprint
from blueprints.reports import reports as reports_blueprint
from blueprints.files import files as files_blueprint
from blueprints.financial import financial as financial_blueprint
from blueprints.academic_year_transition import academic_year_transition as academic_year_transition_blueprint
from blueprints.enrollment import enrollment as enrollment_blueprint

# Load environment variables from .env file
load_dotenv()

# Debug: Print loaded environment variables
print("\nEnvironment Variables:")
print(f"FORMS_WEBHOOK_SECRET: {'[SET]' if os.environ.get('FORMS_WEBHOOK_SECRET') else '[NOT SET]'}")
print(f"FLASK_APP: {os.environ.get('FLASK_APP')}")
print(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
print(f"FLASK_DEBUG: {os.environ.get('FLASK_DEBUG')}\n")

def init_permissions(app):
    """Initialize permissions in the database"""
    from models import Permission
    
    for perm_name in Permission.get_all_permissions():
        if not Permission.query.filter_by(name=perm_name).first():
            perm = Permission(name=perm_name)
            db.session.add(perm)
    db.session.commit()

def create_app(config_name):
    app = Flask(__name__)
    
    # Initialize comprehensive logging system
    log_manager = LogManager(app)
    
    # Set up enhanced error handling
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Log the error with full context
        import traceback
        error_details = {
            'error_type': type(e).__name__,
            'error_message': str(e),
            'traceback': traceback.format_exc(),
            'url': request.url if request else None,
            'method': request.method if request else None,
            'user_agent': request.user_agent.string if request and request.user_agent else None,
            'remote_addr': request.remote_addr if request else None,
            'user': current_user.username if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else 'anonymous'
        }
        
        app.logger.error(f"UNHANDLED_EXCEPTION: {json.dumps(error_details, indent=2)}")
        
        # Return appropriate response
        if request and request.path.startswith('/api/'):
            return jsonify({
                'error': 'Internal server error',
                'error_type': type(e).__name__,
                'debug_info': error_details if app.debug else None
            }), 500
        else:
            return render_template('500.html'), 500
    
    app.logger.info('Student Management System startup with enhanced logging')
    
    # Add request/response logging for API endpoints
    @app.before_request
    def log_request():
        if request.path.startswith('/api/'):
            request_data = {
                'method': request.method,
                'url': request.url,
                'endpoint': request.endpoint,
                'remote_addr': request.remote_addr,
                'user_agent': request.user_agent.string[:200] if request.user_agent else None,
                'content_length': request.content_length,
                'user': current_user.username if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else 'anonymous'
            }
            
            # Log request body for POST/PUT requests (be careful with sensitive data)
            if request.method in ['POST', 'PUT', 'PATCH'] and request.is_json:
                try:
                    # Only log if it's not too large and doesn't contain sensitive fields
                    if request.content_length and request.content_length < 10000:  # Less than 10KB
                        data = request.get_json()
                        # Filter out sensitive fields
                        sensitive_fields = ['password', 'secret', 'token', 'key']
                        if data and not any(field in str(data).lower() for field in sensitive_fields):
                            request_data['body'] = data
                except:
                    pass
            
            app.logger.info(f"API_REQUEST: {json.dumps(request_data)}")
    
    @app.after_request
    def log_response(response):
        if request.path.startswith('/api/'):
            response_data = {
                'status_code': response.status_code,
                'content_length': response.content_length,
                'url': request.url,
                'method': request.method,
                'user': current_user.username if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else 'anonymous'
            }
            
            # Log response body for errors or if it's small
            if response.status_code >= 400 or (response.content_length and response.content_length < 1000):
                try:
                    if response.is_json:
                        response_data['body'] = response.get_json()
                except:
                    pass
            
            app.logger.info(f"API_RESPONSE: {json.dumps(response_data)}")
        
        return response
    
    # Load configuration
    if config_name == 'production':
        app.config.from_object('config.ProductionConfig')
    else:
        app.config.from_object('config.DevelopmentConfig')
    
    # Override config with environment variables
    app.config.from_envvar('FLASK_CONFIG_FILE', silent=True)
    
    # Load webhook secret from environment
    app.config['FORMS_WEBHOOK_SECRET'] = os.environ.get('FORMS_WEBHOOK_SECRET')
    if not app.config['FORMS_WEBHOOK_SECRET']:
        app.logger.error('FORMS_WEBHOOK_SECRET not set in environment variables')
    
    # Configure file uploads
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'attachments')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'
    
    # Import models
    from models import User, Permission
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Add custom template filters
    @app.template_filter('from_json')
    def from_json_filter(value):
        """Parse JSON string to Python object"""
        try:
            if isinstance(value, str):
                return json.loads(value)
            return value
        except (json.JSONDecodeError, TypeError):
            return {}
    
    # Register blueprints
    app.register_blueprint(auth_blueprint)
    # app.register_blueprint(main_blueprint)  # REMOVED: Migration complete - all routes moved to specific blueprints
    
    # Register new modularized blueprints
    app.register_blueprint(core_blueprint)
    app.register_blueprint(students_blueprint)
    app.register_blueprint(applications_blueprint)
    app.register_blueprint(webhooks_blueprint)
    app.register_blueprint(academic_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(kollel_blueprint)
    app.register_blueprint(dormitories_blueprint)
    app.register_blueprint(reports_blueprint)
    app.register_blueprint(files_blueprint)
    app.register_blueprint(financial_blueprint)
    app.register_blueprint(academic_year_transition_blueprint)
    app.register_blueprint(enrollment_blueprint)
    
    # Import and register secure forms blueprint
    from blueprints.secure_forms import secure_forms
    app.register_blueprint(secure_forms)
    
    # Import and register tuition components blueprint
    from blueprints.tuition_components import tuition_components
    app.register_blueprint(tuition_components)
    
    # Import and register PDF templates blueprint
    from blueprints.pdf_templates import pdf_templates
    app.register_blueprint(pdf_templates)
    
    # Import and register email templates blueprint
    from blueprints.email_templates import email_templates
    app.register_blueprint(email_templates)
    
    # Register error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500
    
    # Print registered routes for debugging
    print("Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"Route: {rule.endpoint} -> {rule.rule}")
    
    return app

# Create the application instance
app = create_app(os.getenv('FLASK_CONFIG') or 'default')

if __name__ == '__main__':
    print("\nStarting webhook server...")
    print("Web interface URL: http://localhost:5000")
    print("Webhook URL: http://localhost:5000/api/gravity-forms/webhook")
    print("Using webhook secret:", app.config['FORMS_WEBHOOK_SECRET'])
    app.run(debug=True) 