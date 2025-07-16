import os
from datetime import timedelta

class Config:
    # Basic Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///student_management.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Mail Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@yourdomain.com')
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Password Reset Configuration
    RESET_TOKEN_EXPIRE_HOURS = 24
    
    # Security Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'csrf-secret-key-change-in-production'
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    UPLOAD_FOLDER = 'uploads'
    
    # Dropbox Configuration
    DROPBOX_ACCESS_TOKEN = os.environ.get('DROPBOX_ACCESS_TOKEN')
    DROPBOX_APP_KEY = os.environ.get('DROPBOX_APP_KEY')
    DROPBOX_APP_SECRET = os.environ.get('DROPBOX_APP_SECRET')
    DROPBOX_FOLDER_PREFIX = os.environ.get('DROPBOX_FOLDER_PREFIX', '/StudentManagement')
    USE_DROPBOX_STORAGE = os.environ.get('USE_DROPBOX_STORAGE', 'false').lower() in ['true', '1', 'yes']
    
    # Dropbox Sign Configuration
    DROPBOX_SIGN_API_KEY = os.environ.get('DROPBOX_SIGN_API_KEY')
    DROPBOX_SIGN_CLIENT_ID = os.environ.get('DROPBOX_SIGN_CLIENT_ID')
    DROPBOX_SIGN_TEST_MODE = os.environ.get('DROPBOX_SIGN_TEST_MODE', 'true').lower() in ['true', '1', 'yes']
    DROPBOX_SIGN_WEBHOOK_SECRET = os.environ.get('DROPBOX_SIGN_WEBHOOK_SECRET')

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    # Use instance folder for database (Flask best practice)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.abspath("instance/student_management_dev.db")}'
    # Server configuration for URL generation
    SERVER_NAME = 'localhost:5000'
    PREFERRED_URL_SCHEME = 'http'

class ProductionConfig(Config):
    DEBUG = False
    # In production, make sure to set these environment variables
    SECRET_KEY = os.environ.get('SECRET_KEY')
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 