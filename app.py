from flask import Flask, jsonify, request, render_template_string, render_template
from flask_login import current_user
from flask_mail import Message
from datetime import datetime
import hmac
import hashlib
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from config import config
from extensions import db, login_manager, mail, migrate
from models import User, Permission, init_db
from auth import auth as auth_blueprint
from main import main as main_blueprint
from flask_migrate import upgrade

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
    
    # Set up logging
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Student Management System startup')
    
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
    
    # Register blueprints
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(main_blueprint)
    
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