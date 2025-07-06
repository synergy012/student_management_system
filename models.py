from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from extensions import db
import json
import os

# Association table for user permissions
user_permissions = db.Table('user_permissions',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)

class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    
    VIEW_STUDENTS = 'view_students'
    EDIT_STUDENTS = 'edit_students'
    DELETE_STUDENTS = 'delete_students'
    VIEW_APPLICATIONS = 'view_applications'
    PROCESS_APPLICATIONS = 'process_applications'
    VIEW_COURSES = 'view_courses'
    EDIT_COURSES = 'edit_courses'
    MANAGE_USERS = 'manage_users'  # Admin only

    @staticmethod
    def get_all_permissions():
        return [
            Permission.VIEW_STUDENTS,
            Permission.EDIT_STUDENTS,
            Permission.DELETE_STUDENTS,
            Permission.VIEW_APPLICATIONS,
            Permission.PROCESS_APPLICATIONS,
            Permission.VIEW_COURSES,
            Permission.EDIT_COURSES,
            Permission.MANAGE_USERS
        ]

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'<Permission {self.name}>'

class UserActivity(db.Model):
    __tablename__ = 'user_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('activities', lazy='dynamic'))

    def __repr__(self):
        return f'<UserActivity {self.activity_type}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expiry = db.Column(db.DateTime)
    
    # Many-to-many relationship with permissions
    permissions = db.relationship('Permission', secondary=user_permissions, 
                                backref=db.backref('users', lazy='dynamic'))

    # Add new fields for security
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    account_locked_until = db.Column(db.DateTime)
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    password_history = db.Column(db.JSON, default=list)

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if kwargs.get('is_admin'):
            # Add all permissions for admin users
            for perm_name in Permission.get_all_permissions():
                perm = Permission.query.filter_by(name=perm_name).first()
                if perm and perm not in self.permissions:
                    self.permissions.append(perm)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission_name):
        if self.is_admin:
            return True
        return any(p.name == permission_name for p in self.permissions)

    def add_permission(self, permission_name):
        perm = Permission.query.filter_by(name=permission_name).first()
        if perm and not self.has_permission(permission_name):
            self.permissions.append(perm)

    def remove_permission(self, permission_name):
        perm = Permission.query.filter_by(name=permission_name).first()
        if perm and perm in self.permissions:
            self.permissions.remove(perm)

    def get_all_permissions(self):
        return [perm.name for perm in self.permissions]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f'<User {self.username}>'

    def log_activity(self, activity_type, description=None, ip_address=None, user_agent=None):
        activity = UserActivity(
            user_id=self.id,
            activity_type=activity_type,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(activity)
        db.session.commit()
    
    def is_account_locked(self):
        if self.account_locked_until and self.account_locked_until > datetime.utcnow():
            return True
        return False
    
    def increment_failed_login(self):
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        
        # Lock account after 5 failed attempts
        if self.failed_login_attempts >= 5:
            self.account_locked_until = datetime.utcnow() + timedelta(minutes=30)
        
        db.session.commit()
    
    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.account_locked_until = None
        db.session.commit()
    
    def add_password_to_history(self, password_hash):
        history = self.password_history or []
        history.append({
            'password': password_hash,
            'timestamp': datetime.utcnow().isoformat()
        })
        # Keep only last 5 passwords
        self.password_history = history[-5:]
        db.session.commit()
    
    def is_password_in_history(self, password):
        if not self.password_history:
            return False
        
        for hist in self.password_history:
            if check_password_hash(hist['password'], password):
                return True
        return False

class Application(db.Model):
    __tablename__ = 'applications'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    student_id = db.Column(db.String(36))  # UUID
    submitted_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')  # Pending, Accepted, Rejected
    division = db.Column(db.String(10), default='YZA')  # YZA or YOH
    
    # Basic Student Information
    student_first_name = db.Column(db.String(50))
    student_middle_name = db.Column(db.String(50))
    student_last_name = db.Column(db.String(50))
    student_name = db.Column(db.String(150))  # Combined name for backward compatibility
    hebrew_name = db.Column(db.String(100))
    informal_name = db.Column(db.String(50))
    date_of_birth = db.Column(db.Date)
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(120))
    
    # Address Information (Student)
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    address_city = db.Column(db.String(100))
    address_state = db.Column(db.String(50))
    address_zip = db.Column(db.String(20))
    address_country = db.Column(db.String(50))
    
    # Alternate Address
    alt_address_line1 = db.Column(db.String(200))
    alt_address_line2 = db.Column(db.String(200))
    alt_address_city = db.Column(db.String(100))
    alt_address_state = db.Column(db.String(50))
    alt_address_zip = db.Column(db.String(20))
    alt_address_country = db.Column(db.String(50))
    
    # Personal Information
    marital_status = db.Column(db.String(20))
    spouse_name = db.Column(db.String(100))
    citizenship = db.Column(db.String(50))
    social_security_number = db.Column(db.String(20))
    high_school_graduate = db.Column(db.String(10))
    
    # Father Information
    father_title = db.Column(db.String(10))
    father_first_name = db.Column(db.String(50))
    father_last_name = db.Column(db.String(50))
    father_phone = db.Column(db.String(20))
    father_email = db.Column(db.String(120))
    father_occupation = db.Column(db.String(100))
    
    # Mother Information
    mother_title = db.Column(db.String(10))
    mother_first_name = db.Column(db.String(50))
    mother_last_name = db.Column(db.String(50))
    mother_phone = db.Column(db.String(20))
    mother_email = db.Column(db.String(120))
    mother_occupation = db.Column(db.String(100))
    
    # In-laws Information (Unified)
    inlaws_first_name = db.Column(db.String(50))
    inlaws_last_name = db.Column(db.String(50))
    inlaws_phone = db.Column(db.String(20))
    inlaws_email = db.Column(db.String(100))
    inlaws_address_line1 = db.Column(db.String(200))
    inlaws_address_city = db.Column(db.String(100))
    inlaws_address_state = db.Column(db.String(50))
    inlaws_address_zip = db.Column(db.String(20))
    
    # Grandparents - Paternal
    paternal_grandfather_first_name = db.Column(db.String(50))
    paternal_grandfather_last_name = db.Column(db.String(50))
    paternal_grandfather_phone = db.Column(db.String(20))
    paternal_grandfather_email = db.Column(db.String(120))
    paternal_grandfather_address_line1 = db.Column(db.String(200))
    paternal_grandfather_address_city = db.Column(db.String(100))
    paternal_grandfather_address_state = db.Column(db.String(50))
    paternal_grandfather_address_zip = db.Column(db.String(20))
    
    # Grandparents - Maternal
    maternal_grandfather_first_name = db.Column(db.String(50))
    maternal_grandfather_last_name = db.Column(db.String(50))
    maternal_grandfather_phone = db.Column(db.String(20))
    maternal_grandfather_email = db.Column(db.String(120))
    maternal_grandfather_address_line1 = db.Column(db.String(200))
    maternal_grandfather_address_city = db.Column(db.String(100))
    maternal_grandfather_address_state = db.Column(db.String(50))
    maternal_grandfather_address_zip = db.Column(db.String(20))
    
    # Education Information
    college_attending = db.Column(db.String(10))  # Yes/No
    college_name = db.Column(db.String(200))
    college_major = db.Column(db.String(100))
    college_expected_graduation = db.Column(db.String(20))
    
    # Learning Information
    last_rebbe_name = db.Column(db.String(100))
    last_rebbe_phone = db.Column(db.String(20))
    gemora_sedorim_daily_count = db.Column(db.String(10))
    gemora_sedorim_length = db.Column(db.String(10))
    learning_evaluation = db.Column(db.String(200))
    
    # Medical Information
    medical_conditions = db.Column(db.String(500))
    insurance_company = db.Column(db.String(100))
    blood_type = db.Column(db.String(10))
    
    # Financial Information
    tuition_payment_status = db.Column(db.String(50))  # "Full Tuition", "Not Full Tuition", etc.
    amount_can_pay = db.Column(db.Numeric(10, 2))
    scholarship_amount_requested = db.Column(db.Numeric(10, 2))
    financial_aid_explanation = db.Column(db.Text)
    
    # History Information
    past_jobs = db.Column(db.Text)
    summer_activities = db.Column(db.Text)
    
    # Additional Information
    additional_info = db.Column(db.Text)
    
    # High School Information (stored as JSON for multiple schools)
    high_school_info = db.Column(db.JSON)
    
    # Seminary Information (stored as JSON for multiple schools)
    seminary_info = db.Column(db.JSON)
    
    # Documents (stored as JSON for file references)
    documents = db.Column(db.JSON)
    
    # Custom fields for any additional unmapped data
    custom_fields = db.Column(db.JSON)
    
    # Division-specific data (for YOH fields that don't exist in YZA, etc.)
    division_specific_data = db.Column(db.JSON)
    
    # Relationship to file attachments
    attachments = db.relationship('FileAttachment', backref='application', lazy='dynamic', cascade='all, delete-orphan')

    # Dormitory and Meals Option - NEW FIELD
    dormitory_meals_option = db.Column(db.String(200))

    def __repr__(self):
        return f'<Application {self.student_name}>'
    
    @property
    def status_color(self):
        status_colors = {
            'Pending': 'warning',
            'Accepted': 'success',
            'Rejected': 'danger'
        }
        return status_colors.get(self.status, 'secondary')
    
    @property
    def division_color(self):
        division_colors = {
            'YZA': 'primary',
            'YOH': 'info'
        }
        return division_colors.get(self.division, 'secondary')
    
    @property
    def division_badge(self):
        return f'<span class="badge bg-{self.division_color}">{self.division}</span>'
    
    @property
    def parents(self):
        """Get parent information"""
        return {
            'father': {
                'title': self.father_title or '',
                'first_name': self.father_first_name or '',
                'last_name': self.father_last_name or '',
                'phone': self.father_phone or '',
                'email': self.father_email or '',
                'occupation': self.father_occupation or ''
            },
            'mother': {
                'title': self.mother_title or '',
                'first_name': self.mother_first_name or '',
                'last_name': self.mother_last_name or '',
                'phone': self.mother_phone or '',
                'email': self.mother_email or '',
                'occupation': self.mother_occupation or ''
            }
        }
    
    @property
    def father(self):
        """Get father's information"""
        return {
            'title': self.father_title or '',
            'first_name': self.father_first_name or '',
            'last_name': self.father_last_name or '',
            'phone': self.father_phone or '',
            'email': self.father_email or '',
            'occupation': self.father_occupation or ''
        }
    
    @property
    def mother(self):
        """Get mother's information"""
        return {
            'title': self.mother_title or '',
            'first_name': self.mother_first_name or '',
            'last_name': self.mother_last_name or '',
            'phone': self.mother_phone or '',
            'email': self.mother_email or '',
            'occupation': self.mother_occupation or ''
        }
    
    @property
    def grandparents(self):
        """Get grandparents information"""
        return {
            'paternal': {
                'first_name': self.paternal_grandfather_first_name or '',
                'last_name': self.paternal_grandfather_last_name or '',
                'phone': self.paternal_grandfather_phone or '',
                'email': self.paternal_grandfather_email or '',
                'address': {
                    'line1': self.paternal_grandfather_address_line1 or '',
                    'city': self.paternal_grandfather_address_city or '',
                    'state': self.paternal_grandfather_address_state or '',
                    'zip': self.paternal_grandfather_address_zip or ''
                }
            },
            'maternal': {
                'first_name': self.maternal_grandfather_first_name or '',
                'last_name': self.maternal_grandfather_last_name or '',
                'phone': self.maternal_grandfather_phone or '',
                'email': self.maternal_grandfather_email or '',
                'address': {
                    'line1': self.maternal_grandfather_address_line1 or '',
                    'city': self.maternal_grandfather_address_city or '',
                    'state': self.maternal_grandfather_address_state or '',
                    'zip': self.maternal_grandfather_address_zip or ''
                }
            }
        }
    
    @property
    def in_laws(self):
        """Get in-laws information (unified)"""
        return {
            'first_name': self.inlaws_first_name or '',
            'last_name': self.inlaws_last_name or '',
            'phone': self.inlaws_phone or '',
            'email': self.inlaws_email or '',
            'address': {
                'line1': self.inlaws_address_line1 or '',
                'city': self.inlaws_address_city or '',
                'state': self.inlaws_address_state or '',
                'zip': self.inlaws_address_zip or ''
            }
        }
    
    @property
    def date_of_birth_str(self):
        """Get date of birth as string"""
        if self.date_of_birth:
            return self.date_of_birth.strftime('%Y-%m-%d')
        return 'N/A'
    
    @property
    def high_school_graduate_status(self):
        """Get high school graduate status"""
        return self.high_school_graduate or 'N/A'
    
    @property
    def financial_aid(self):
        """Get financial aid information"""
        return {
            'status': self.tuition_payment_status or 'N/A',
            'amount_can_pay': str(self.amount_can_pay) if self.amount_can_pay else '0',
            'scholarship_amount': str(self.scholarship_amount_requested) if self.scholarship_amount_requested else '0',
            'explanation': self.financial_aid_explanation or ''
        }
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student_name,
            'student_first_name': self.student_first_name,
            'student_middle_name': self.student_middle_name,
            'student_last_name': self.student_last_name,
            'hebrew_name': self.hebrew_name,
            'informal_name': self.informal_name,
            'date_of_birth': self.date_of_birth_str,
            'submitted_date': self.submitted_date.strftime('%Y-%m-%d') if self.submitted_date else '',
            'status': self.status,
            'status_color': self.status_color,
            'phone_number': self.phone_number,
            'email': self.email,
            'marital_status': self.marital_status,
            'spouse_name': self.spouse_name,
            'citizenship': self.citizenship,
            'address': {
                'line1': self.address_line1,
                'line2': self.address_line2,
                'city': self.address_city,
                'state': self.address_state,
                'zip': self.address_zip,
                'country': self.address_country
            },
            'parents': self.parents,
            'grandparents': self.grandparents,
            'in_laws': self.in_laws,
            'financial_aid': self.financial_aid,
            'custom_fields': self.custom_fields or {},
            'dormitory_meals_option': self.dormitory_meals_option
        }

class FileAttachment(db.Model):
    __tablename__ = 'file_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.String(36), db.ForeignKey('applications.id'), nullable=True)  # Made nullable for student attachments
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=True)  # Added: Support for student attachments
    field_id = db.Column(db.String(10), nullable=False)  # Gravity Forms field ID (151, 152, 153)
    field_name = db.Column(db.String(100), nullable=False)  # Human readable name
    original_url = db.Column(db.String(500), nullable=False)  # Original URL from Gravity Forms
    original_filename = db.Column(db.String(255), nullable=False)
    local_filename = db.Column(db.String(255), nullable=False)  # Stored filename on our server
    file_size = db.Column(db.Integer)  # File size in bytes
    mime_type = db.Column(db.String(100))
    download_status = db.Column(db.String(20), default='pending')  # pending, downloaded, failed
    downloaded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<FileAttachment {self.original_filename}>'
    
    @property
    def download_path(self):
        """Get the full path to the downloaded file"""
        return f"attachments/{self.local_filename}"
    
    @property
    def file_size_formatted(self):
        """Get human-readable file size"""
        if not self.file_size:
            return "Unknown size"
        
        try:
            # Handle both string and numeric file sizes
            if isinstance(self.file_size, str):
                # If it's a string that doesn't represent a number, return unknown
                if not self.file_size.replace('.', '').replace('-', '').isdigit():
                    return "Unknown size"
            
            size = float(self.file_size)
            
            # Handle negative or zero sizes
            if size <= 0:
                return "Unknown size"
            
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
            
        except (ValueError, TypeError):
            # If conversion fails, return unknown size
            return "Unknown size"

    @property
    def is_viewable(self):
        """Check if file can be viewed inline (images and PDFs)"""
        if not self.mime_type:
            return False
        
        # Clean mime type (remove any parameters like "; qs=0.001")
        mime_type = self.mime_type.split(';')[0].strip().lower()
        
        return (mime_type.startswith('image/') or 
                mime_type == 'application/pdf')
    
    @property
    def file_type_icon(self):
        """Get appropriate icon for file type"""
        if not self.mime_type:
            return 'fas fa-file'
        
        # Clean mime type (remove any parameters like "; qs=0.001")
        mime_type = self.mime_type.split(';')[0].strip().lower()
        
        if mime_type.startswith('image/'):
            return 'fas fa-image'
        elif mime_type == 'application/pdf':
            return 'fas fa-file-pdf'
        elif mime_type.startswith('text/'):
            return 'fas fa-file-alt'
        elif 'word' in mime_type or 'document' in mime_type:
            return 'fas fa-file-word'
        elif 'excel' in mime_type or 'spreadsheet' in mime_type:
            return 'fas fa-file-excel'
        else:
            return 'fas fa-file'
    
    @property
    def display_name(self):
        """Get human-readable display name for the attachment"""
        # Due to data corruption, field_id often contains the human-readable name
        # while field_name contains URLs. Try to use the most appropriate one.
        
        if self.field_id and not self.field_id.startswith(('http://', 'https://')):
            # field_id contains meaningful name like "High School Graduation Proof"
            return self.field_id
        elif self.field_name and not self.field_name.startswith(('http://', 'https://')):
            # field_name contains meaningful name
            return self.field_name
        else:
            # Both contain URLs or are empty, create a name from filename
            if self.original_filename:
                name, ext = os.path.splitext(self.original_filename)
                return name.replace('_', ' ').replace('-', ' ').title()
            else:
                return "Document"

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    application_id = db.Column(db.String(36), db.ForeignKey('applications.id'))  # Reference to original application
    accepted_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Active')  # Active, Inactive, Graduated, Withdrawn
    division = db.Column(db.String(10), default='YZA')  # YZA or YOH
    
    # Application-specific fields (copied from original application)
    student_id = db.Column(db.String(36))  # UUID from original application
    submitted_date = db.Column(db.DateTime)  # When the original application was submitted
    
    # Basic Student Information - Same as Application
    student_first_name = db.Column(db.String(50))
    student_middle_name = db.Column(db.String(50))
    student_last_name = db.Column(db.String(50))
    student_name = db.Column(db.String(150))  # Combined name for backward compatibility
    informal_name = db.Column(db.String(50))
    hebrew_name = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date)
    email = db.Column(db.String(120))  # Fixed: Match Application table size
    phone_number = db.Column(db.String(20))
    social_security_number = db.Column(db.String(20))  # Fixed: Match Application table size
    
    # Address Information
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    address_city = db.Column(db.String(100))
    address_state = db.Column(db.String(50))
    address_zip = db.Column(db.String(20))
    address_country = db.Column(db.String(100))
    
    # Alternative/Mailing Address
    alt_address_line1 = db.Column(db.String(200))
    alt_address_line2 = db.Column(db.String(200))
    alt_address_city = db.Column(db.String(100))
    alt_address_state = db.Column(db.String(50))
    alt_address_zip = db.Column(db.String(20))
    alt_address_country = db.Column(db.String(100))
    
    # Citizenship and Status Information
    citizenship = db.Column(db.String(50))
    high_school_graduate = db.Column(db.String(10))
    
    # Father Information
    father_title = db.Column(db.String(10))
    father_first_name = db.Column(db.String(50))
    father_last_name = db.Column(db.String(50))
    father_occupation = db.Column(db.String(100))
    father_phone = db.Column(db.String(20))
    father_email = db.Column(db.String(100))
    
    # Mother Information
    mother_title = db.Column(db.String(10))
    mother_first_name = db.Column(db.String(50))
    mother_last_name = db.Column(db.String(50))
    mother_occupation = db.Column(db.String(100))
    mother_phone = db.Column(db.String(20))
    mother_email = db.Column(db.String(100))
    
    # Marital Status and Spouse
    marital_status = db.Column(db.String(20))
    spouse_name = db.Column(db.String(100))
    
    # In-laws Information (Unified)
    inlaws_first_name = db.Column(db.String(50))
    inlaws_last_name = db.Column(db.String(50))
    inlaws_phone = db.Column(db.String(20))
    inlaws_email = db.Column(db.String(100))
    inlaws_address_line1 = db.Column(db.String(200))
    inlaws_address_city = db.Column(db.String(100))
    inlaws_address_state = db.Column(db.String(50))
    inlaws_address_zip = db.Column(db.String(20))
    
    # Paternal Grandparents
    paternal_grandfather_first_name = db.Column(db.String(50))
    paternal_grandfather_last_name = db.Column(db.String(50))
    paternal_grandfather_phone = db.Column(db.String(20))
    paternal_grandfather_email = db.Column(db.String(100))
    paternal_grandfather_address_line1 = db.Column(db.String(200))
    paternal_grandfather_address_city = db.Column(db.String(100))
    paternal_grandfather_address_state = db.Column(db.String(50))
    paternal_grandfather_address_zip = db.Column(db.String(20))
    
    # Maternal Grandparents
    maternal_grandfather_first_name = db.Column(db.String(50))
    maternal_grandfather_last_name = db.Column(db.String(50))
    maternal_grandfather_phone = db.Column(db.String(20))
    maternal_grandfather_email = db.Column(db.String(100))
    maternal_grandfather_address_line1 = db.Column(db.String(200))
    maternal_grandfather_address_city = db.Column(db.String(100))
    maternal_grandfather_address_state = db.Column(db.String(50))
    maternal_grandfather_address_zip = db.Column(db.String(20))
    
    # Medical Information
    medical_conditions = db.Column(db.Text)
    insurance_company = db.Column(db.String(100))
    blood_type = db.Column(db.String(10))
    
    # Learning Information
    last_rebbe_name = db.Column(db.String(100))
    last_rebbe_phone = db.Column(db.String(20))
    gemora_sedorim_daily_count = db.Column(db.String(20))
    gemora_sedorim_length = db.Column(db.String(50))
    learning_evaluation = db.Column(db.Text)
    
    # College Information
    college_attending = db.Column(db.String(10))
    college_name = db.Column(db.String(100))
    college_major = db.Column(db.String(100))
    college_expected_graduation = db.Column(db.String(50))
    
    # Work and Activities
    past_jobs = db.Column(db.Text)
    summer_activities = db.Column(db.Text)
    
    # Education Information (stored as JSON or text)
    high_school_info = db.Column(db.Text)  # JSON encoded list
    seminary_info = db.Column(db.Text)     # JSON encoded list
    
    # Financial Information
    tuition_payment_status = db.Column(db.String(200))
    scholarship_amount_requested = db.Column(db.Numeric(10, 2))  # Fixed: Match Application table type
    amount_can_pay = db.Column(db.Numeric(10, 2))  # Fixed: Match Application table type
    financial_aid_explanation = db.Column(db.Text)  # Added: Missing from Student table
    
    # Enhanced Financial Information - NEW FIELDS
    financial_aid_type = db.Column(db.String(50), default='Full Tuition')  # 'Full Tuition', 'Financial Aid'
    financial_aid_app_sent = db.Column(db.Boolean, default=False)  # Whether financial aid application was sent
    financial_aid_app_sent_date = db.Column(db.DateTime)  # When financial aid app was sent
    financial_aid_app_received = db.Column(db.Boolean, default=False)  # Whether application was received back
    financial_aid_app_received_date = db.Column(db.DateTime)  # When application was received back
    tuition_determination = db.Column(db.Numeric(10, 2))  # Final tuition amount determined
    tuition_determination_notes = db.Column(db.Text)  # Notes about tuition determination
    tuition_contract_generated = db.Column(db.Boolean, default=False)  # Whether contract was generated
    tuition_contract_generated_date = db.Column(db.DateTime)  # When contract was generated
    tuition_contract_sent = db.Column(db.Boolean, default=False)  # Whether contract was sent
    tuition_contract_sent_date = db.Column(db.DateTime)  # When contract was sent
    tuition_contract_signed = db.Column(db.Boolean, default=False)  # Whether contract was signed
    tuition_contract_signed_date = db.Column(db.DateTime)  # When contract was signed
    tuition_contract_pdf_path = db.Column(db.String(500))  # Path to saved tuition contract PDF
    
    # Dropbox Sign E-Signature Integration Fields
    dropbox_sign_signature_request_id = db.Column(db.String(100))  # Dropbox Sign signature request ID for contract tracking
    dropbox_sign_status = db.Column(db.String(20))  # 'pending', 'completed', 'declined', 'expired'
    dropbox_sign_signed_url = db.Column(db.String(500))  # URL to download signed document from Dropbox Sign
    dropbox_sign_files_url = db.Column(db.String(500))  # URL to download files from Dropbox Sign
    dropbox_sign_template_id = db.Column(db.String(100))  # Dropbox Sign template ID if using templates
    
    # FAFSA Information
    fafsa_eligible = db.Column(db.String(20))  # 'Eligible', 'Not Eligible', 'Unknown'
    fafsa_required = db.Column(db.Boolean, default=False)  # Whether FAFSA is required
    fafsa_applied = db.Column(db.Boolean, default=False)  # Whether student applied for FAFSA
    fafsa_application_date = db.Column(db.DateTime)  # When FAFSA application was submitted
    fafsa_status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Accepted', 'Rejected'
    fafsa_amount_awarded = db.Column(db.Numeric(10, 2))  # Amount awarded through FAFSA
    fafsa_notes = db.Column(db.Text)  # Additional notes about FAFSA
    
    # Dormitory and Meals Option - NEW FIELD
    dormitory_meals_option = db.Column(db.String(200))
    
    # Additional Information
    additional_info = db.Column(db.Text)
    
    # Documents (stored as JSON for file references) - Added: Missing from Student table
    documents = db.Column(db.JSON)
    
    # Custom fields for storing additional structured data (JSON)
    custom_fields = db.Column(db.Text)  # JSON encoded
    
    # Division-specific data (for YOH fields that don't exist in YZA, etc.)
    division_specific_data = db.Column(db.JSON)
    
    # Email tracking fields
    acceptance_email_sent = db.Column(db.Boolean, default=False)
    acceptance_email_sent_date = db.Column(db.DateTime)
    acceptance_email_sent_by = db.Column(db.String(100))
    acceptance_letter_pdf_path = db.Column(db.String(500))  # Path to saved acceptance letter PDF

    # Relationship to original application
    application = db.relationship('Application', backref=db.backref('student', uselist=False))
    
    # Relationship to file attachments
    attachments = db.relationship('FileAttachment', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
    # Relationship to tuition records
    tuition_records = db.relationship('TuitionRecord', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
    # Financial tracking fields
    current_year_tuition = db.Column(db.Numeric(10, 2))
    prior_year_tuition = db.Column(db.Numeric(10, 2))
    financial_aid_form_sent = db.Column(db.Boolean, default=False)
    financial_aid_form_sent_date = db.Column(db.DateTime)
    financial_aid_form_received = db.Column(db.Boolean, default=False)
    financial_aid_form_received_date = db.Column(db.DateTime)
    enrollment_contract_sent = db.Column(db.Boolean, default=False)
    enrollment_contract_sent_date = db.Column(db.DateTime)
    enrollment_contract_received = db.Column(db.Boolean, default=False)
    enrollment_contract_received_date = db.Column(db.DateTime)
    admire_charges_setup = db.Column(db.Boolean, default=False)
    admire_charges_setup_date = db.Column(db.DateTime)
    fafsa_required = db.Column(db.Boolean, default=False)
    fafsa_status = db.Column(db.String(50))  # Not Started, In Progress, Submitted, Approved
    pell_grant_received = db.Column(db.Boolean, default=False)
    pell_grant_amount = db.Column(db.Numeric(10, 2))
    tuition_type = db.Column(db.String(20))  # Full, Reduced, Scholarship
    tuition_discount_percentage = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<Student {self.student_name}>'
    
    @property
    def status_color(self):
        """Return Bootstrap color class for status"""
        status_colors = {
            'Active': 'success',
            'Inactive': 'warning', 
            'Graduated': 'info',
            'Withdrawn': 'danger'
        }
        return status_colors.get(self.status, 'secondary')
    
    @property
    def division_color(self):
        """Return Bootstrap color class for division"""
        return 'primary' if self.division == 'YZA' else 'success'
    
    @property
    def division_badge(self):
        """Return formatted division badge text"""
        return f'Division {self.division}'
    
    @property
    def parents(self):
        """Return formatted parent information"""
        father = {
            'title': self.father_title,
            'first_name': self.father_first_name,
            'last_name': self.father_last_name,
            'full_name': f"{self.father_title or ''} {self.father_first_name or ''} {self.father_last_name or ''}".strip(),
            'phone': self.father_phone,
            'email': self.father_email,
            'occupation': self.father_occupation
        }
        
        mother = {
            'title': self.mother_title,
            'first_name': self.mother_first_name,
            'last_name': self.mother_last_name,
            'full_name': f"{self.mother_title or ''} {self.mother_first_name or ''} {self.mother_last_name or ''}".strip(),
            'phone': self.mother_phone,
            'email': self.mother_email,
            'occupation': self.mother_occupation
        }
        
        return {'father': father, 'mother': mother}
    
    @property
    def date_of_birth_str(self):
        """Return formatted date of birth"""
        return self.date_of_birth.strftime('%B %d, %Y') if self.date_of_birth else ''
    
    @property
    def submitted_date_str(self):
        """Return formatted submission date"""
        return self.submitted_date.strftime('%B %d, %Y at %I:%M %p') if self.submitted_date else ''
    
    def get_tuition_record(self, academic_year_id=None):
        """Get tuition record for a specific academic year or active year"""
        if academic_year_id:
            return self.tuition_records.filter_by(academic_year_id=academic_year_id).first()
        else:
            # Get active academic year
            active_year = AcademicYear.get_active_year()
            if active_year:
                return self.tuition_records.filter_by(academic_year_id=active_year.id).first()
        return None
    
    def get_tuition_history(self):
        """Get all tuition records ordered by academic year"""
        return self.tuition_records.join(AcademicYear).order_by(AcademicYear.start_date.desc()).all()
    
    def create_tuition_record(self, academic_year_id):
        """Create a new tuition record for a specific academic year"""
        # Check if record already exists
        existing = self.tuition_records.filter_by(academic_year_id=academic_year_id).first()
        if existing:
            return existing
        
        # Create new record with current matriculation status
        tuition_record = TuitionRecord(
            student_id=self.id,
            academic_year_id=academic_year_id,
            matriculation_status_for_year=self.computed_matriculation_status
        )
        db.session.add(tuition_record)
        db.session.commit()
        return tuition_record
    
    def get_computed_matriculation_status(self):
        """Compute matriculation status based on graduation dates"""
        from datetime import date
        
        # If manually overridden, return the override value
        if self.matriculation_override and self.matriculation_status in ['Matriculating', 'Non-Matriculating']:
            return self.matriculation_status
        
        # Auto-determine based on graduation dates
        today = date.today()
        
        # Check if graduated high school
        if not self.high_school_graduation_date:
            return 'Non-Matriculating'  # No high school graduation date
        
        # Not yet graduated high school
        if self.high_school_graduation_date > today:
            return 'Non-Matriculating'
        
        # Check if already graduated our program
        if self.program_graduation_date and self.program_graduation_date <= today:
            return 'Non-Matriculating'  # Already graduated our program
        
        # Graduated high school but not our program = Matriculating
        return 'Matriculating'
    
    @property
    def computed_matriculation_status(self):
        """Get the computed matriculation status"""
        return self.get_computed_matriculation_status()
    
    @property
    def matriculation_status_badge_color(self):
        """Get Bootstrap color class for matriculation status"""
        status = self.computed_matriculation_status
        colors = {
            'Matriculating': 'success',
            'Non-Matriculating': 'warning'
        }
        return colors.get(status, 'secondary')
    
    @property
    def matriculation_info(self):
        """Get comprehensive matriculation information"""
        return {
            'status': self.computed_matriculation_status,
            'is_override': self.matriculation_override,
            'high_school_graduation': self.high_school_graduation_date.isoformat() if self.high_school_graduation_date else None,
            'program_graduation': self.program_graduation_date.isoformat() if self.program_graduation_date else None,
            'notes': self.matriculation_notes or '',
            'badge_color': self.matriculation_status_badge_color
        }

    @property
    def financial_aid(self):
        """Get financial aid information for active academic year"""
        tuition_record = self.get_tuition_record()
        
        if tuition_record:
            # Return data from tuition record as an object
            return type('FinancialAid', (), tuition_record.financial_aid_info)()
        else:
            # Return legacy data from student record as an object (for backward compatibility)
            return type('FinancialAid', (), {
                'payment_status': self.tuition_payment_status or '',
                'amount_can_pay': float(self.amount_can_pay) if self.amount_can_pay else 0.0,
                'scholarship_requested': float(self.scholarship_amount_requested) if self.scholarship_amount_requested else 0.0,
                'explanation': self.financial_aid_explanation or '',
                'financial_aid_type': self.financial_aid_type or 'Full Tuition',
                'financial_aid_app_sent': self.financial_aid_app_sent,
                'financial_aid_app_received': self.financial_aid_app_received,
                'tuition_determination': float(self.tuition_determination) if self.tuition_determination else 0.0,
                'tuition_determination_notes': self.tuition_determination_notes or '',
                'tuition_contract_generated': self.tuition_contract_generated,
                'tuition_contract_sent': self.tuition_contract_sent,
                'tuition_contract_signed': self.tuition_contract_signed,
                'opensign_document_id': self.opensign_document_id,
                'opensign_document_status': self.opensign_document_status,
                'opensign_signed_url': self.opensign_signed_url,
                'opensign_certificate_url': self.opensign_certificate_url,
                'fafsa_eligible': self.fafsa_eligible or 'Unknown',
                'fafsa_required': self.fafsa_required,
                'fafsa_applied': self.fafsa_applied,
                'fafsa_status': self.fafsa_status or 'Pending',
                'fafsa_amount_awarded': float(self.fafsa_amount_awarded) if self.fafsa_amount_awarded else 0.0,
                'fafsa_notes': self.fafsa_notes or '',
                'tuition_contract_pdf_path': self.tuition_contract_pdf_path or ''
            })()
    
    @property
    def address(self):
        """Get structured address information"""
        return type('Address', (), {
            'line1': self.address_line1 or '',
            'line2': self.address_line2 or '',
            'city': self.address_city or '',
            'state': self.address_state or '',
            'zip': self.address_zip or '',
            'country': self.address_country or ''
        })()
    
    @property
    def in_laws(self):
        """Get structured in-laws information"""
        return type('InLaws', (), {
            'first_name': self.inlaws_first_name or '',
            'last_name': self.inlaws_last_name or '',
            'phone': self.inlaws_phone or '',
            'email': self.inlaws_email or '',
            'address': type('Address', (), {
                'line1': self.inlaws_address_line1 or '',
                'city': self.inlaws_address_city or '',
                'state': self.inlaws_address_state or '',
                'zip': self.inlaws_address_zip or ''
            })()
        })()
    
    @property
    def grandparents(self):
        """Get structured grandparents information"""
        return type('Grandparents', (), {
            'paternal': type('PaternalGrandparent', (), {
                'first_name': self.paternal_grandfather_first_name or '',
                'last_name': self.paternal_grandfather_last_name or '',
                'phone': self.paternal_grandfather_phone or '',
                'email': self.paternal_grandfather_email or '',
                'address': type('Address', (), {
                    'line1': self.paternal_grandfather_address_line1 or '',
                    'city': self.paternal_grandfather_address_city or '',
                    'state': self.paternal_grandfather_address_state or '',
                    'zip': self.paternal_grandfather_address_zip or ''
                })()
            })(),
            'maternal': type('MaternalGrandparent', (), {
                'first_name': self.maternal_grandfather_first_name or '',
                'last_name': self.maternal_grandfather_last_name or '',
                'phone': self.maternal_grandfather_phone or '',
                'email': self.maternal_grandfather_email or '',  
                'address': type('Address', (), {
                    'line1': self.maternal_grandfather_address_line1 or '',
                    'city': self.maternal_grandfather_address_city or '',
                    'state': self.maternal_grandfather_address_state or '',
                    'zip': self.maternal_grandfather_address_zip or ''
                })()
            })()
        })()
    
    @property
    def alt_address(self):
        """Get structured alternative address information"""
        return type('AltAddress', (), {
            'line1': self.alt_address_line1 or '',
            'line2': self.alt_address_line2 or '',
            'city': self.alt_address_city or '',
            'state': self.alt_address_state or '',
            'zip': self.alt_address_zip or '',
            'country': self.alt_address_country or ''
        })()
    
    @property
    def parents(self):
        """Get structured parents information"""
        return type('Parents', (), {
            'father': type('Father', (), {
                'title': self.father_title or '',
                'first_name': self.father_first_name or '',
                'last_name': self.father_last_name or '',
                'phone': self.father_phone or '',
                'email': self.father_email or '',
                'occupation': self.father_occupation or ''
            })(),
            'mother': type('Mother', (), {
                'title': self.mother_title or '',
                'first_name': self.mother_first_name or '',
                'last_name': self.mother_last_name or '',
                'phone': self.mother_phone or '',
                'email': self.mother_email or '',
                'occupation': self.mother_occupation or ''
            })()
        })()
    
    @property
    def spouse(self):
        """Get structured spouse information"""
        # Parse spouse_name into parts if it exists
        spouse_parts = []
        if self.spouse_name:
            spouse_parts = self.spouse_name.strip().split()
        
        first_name = spouse_parts[0] if spouse_parts else ''
        last_name = ' '.join(spouse_parts[1:]) if len(spouse_parts) > 1 else ''
        
        return type('Spouse', (), {
            'first_name': first_name,
            'last_name': last_name,
            'phone': '',  # No separate spouse phone field in model
            'email': '',  # No separate spouse email field in model  
            'occupation': ''  # No separate spouse occupation field in model
        })()
    
    @property
    def education(self):
        """Get structured education information"""
        return type('Education', (), {
            'high_school_info': self.high_school_info or '',
            'seminary_info': self.seminary_info or '',
            'college_attending': self.college_attending or '',
            'college_name': self.college_name or '',
            'college_major': self.college_major or '',
            'college_expected_graduation': self.college_expected_graduation or ''
        })()
    
    @property
    def learning(self):
        """Get structured learning information"""
        return type('Learning', (), {
            'last_rebbe_name': self.last_rebbe_name or '',
            'last_rebbe_phone': self.last_rebbe_phone or '',
            'gemora_sedorim_daily_count': self.gemora_sedorim_daily_count or '',
            'gemora_sedorim_length': self.gemora_sedorim_length or '',
            'learning_evaluation': self.learning_evaluation or ''
        })()
    
    @property
    def medical(self):
        """Get structured medical information"""
        return type('Medical', (), {
            'conditions': self.medical_conditions or '',
            'insurance_company': self.insurance_company or '',
            'blood_type': self.blood_type or ''
        })()
    
    @property
    def activities(self):
        """Get structured activities information"""
        return type('Activities', (), {
            'past_jobs': self.past_jobs or '',
            'summer_activities': self.summer_activities or ''
        })()
    
    def to_dict(self):
        """Convert student to dictionary"""
        return {
            'id': self.id,
            'application_id': self.application_id,
            'status': self.status,
            'division': self.division,
            'student_name': self.student_name,
            'phone_number': self.phone_number,
            'email': self.email,
            'date_of_birth': self.date_of_birth_str,
            'accepted_date': self.accepted_date.strftime('%Y-%m-%d') if self.accepted_date else None,
            'custom_fields': self.custom_fields or {}
        }
    
    @classmethod
    def create_from_application(cls, application):
        """Create a new Student from an accepted Application"""
        import uuid
        import json
        
        # Serialize list/dict fields to JSON strings for SQLite compatibility
        high_school_info_json = json.dumps(application.high_school_info) if application.high_school_info else None
        seminary_info_json = json.dumps(application.seminary_info) if application.seminary_info else None
        custom_fields_json = json.dumps(application.custom_fields) if application.custom_fields else None
        
        student = cls(
            id=str(uuid.uuid4()),
            application_id=application.id,
            division=application.division,
            
            # Application-specific fields
            student_id=application.student_id,
            submitted_date=application.submitted_date,
            
            # Copy all application fields
            student_first_name=application.student_first_name,
            student_middle_name=application.student_middle_name,
            student_last_name=application.student_last_name,
            student_name=application.student_name,
            informal_name=application.informal_name,
            hebrew_name=application.hebrew_name,
            date_of_birth=application.date_of_birth,
            phone_number=application.phone_number,
            email=application.email,
            social_security_number=application.social_security_number,
            
            # Address Information
            address_line1=application.address_line1,
            address_line2=application.address_line2,
            address_city=application.address_city,
            address_state=application.address_state,
            address_zip=application.address_zip,
            address_country=application.address_country,
            
            # Alternative/Mailing Address
            alt_address_line1=application.alt_address_line1,
            alt_address_line2=application.alt_address_line2,
            alt_address_city=application.alt_address_city,
            alt_address_state=application.alt_address_state,
            alt_address_zip=application.alt_address_zip,
            alt_address_country=application.alt_address_country,
            
            # Citizenship and Status Information
            citizenship=application.citizenship,
            high_school_graduate=application.high_school_graduate,
            
            # Marital Status and Spouse
            marital_status=application.marital_status,
            spouse_name=application.spouse_name,
            
            # Father Information
            father_title=application.father_title,
            father_first_name=application.father_first_name,
            father_last_name=application.father_last_name,
            father_phone=application.father_phone,
            father_email=application.father_email,
            father_occupation=application.father_occupation,
            
            # Mother Information
            mother_title=application.mother_title,
            mother_first_name=application.mother_first_name,
            mother_last_name=application.mother_last_name,
            mother_phone=application.mother_phone,
            mother_email=application.mother_email,
            mother_occupation=application.mother_occupation,
            
            # In-laws Information
            inlaws_first_name=application.inlaws_first_name,
            inlaws_last_name=application.inlaws_last_name,
            inlaws_phone=application.inlaws_phone,
            inlaws_email=application.inlaws_email,
            inlaws_address_line1=application.inlaws_address_line1,
            inlaws_address_city=application.inlaws_address_city,
            inlaws_address_state=application.inlaws_address_state,
            inlaws_address_zip=application.inlaws_address_zip,
            
            # Paternal Grandparents
            paternal_grandfather_first_name=application.paternal_grandfather_first_name,
            paternal_grandfather_last_name=application.paternal_grandfather_last_name,
            paternal_grandfather_phone=application.paternal_grandfather_phone,
            paternal_grandfather_email=application.paternal_grandfather_email,
            paternal_grandfather_address_line1=application.paternal_grandfather_address_line1,
            paternal_grandfather_address_city=application.paternal_grandfather_address_city,
            paternal_grandfather_address_state=application.paternal_grandfather_address_state,
            paternal_grandfather_address_zip=application.paternal_grandfather_address_zip,
            
            # Maternal Grandparents
            maternal_grandfather_first_name=application.maternal_grandfather_first_name,
            maternal_grandfather_last_name=application.maternal_grandfather_last_name,
            maternal_grandfather_phone=application.maternal_grandfather_phone,
            maternal_grandfather_email=application.maternal_grandfather_email,
            maternal_grandfather_address_line1=application.maternal_grandfather_address_line1,
            maternal_grandfather_address_city=application.maternal_grandfather_address_city,
            maternal_grandfather_address_state=application.maternal_grandfather_address_state,
            maternal_grandfather_address_zip=application.maternal_grandfather_address_zip,
            
            # Medical Information
            medical_conditions=application.medical_conditions,
            insurance_company=application.insurance_company,
            blood_type=application.blood_type,
            
            # Learning Information
            last_rebbe_name=application.last_rebbe_name,
            last_rebbe_phone=application.last_rebbe_phone,
            gemora_sedorim_daily_count=application.gemora_sedorim_daily_count,
            gemora_sedorim_length=application.gemora_sedorim_length,
            learning_evaluation=application.learning_evaluation,
            
            # College Information
            college_attending=application.college_attending,
            college_name=application.college_name,
            college_major=application.college_major,
            college_expected_graduation=application.college_expected_graduation,
            
            # Work and Activities
            past_jobs=application.past_jobs,
            summer_activities=application.summer_activities,
            
            # Education Information - FIXED: Serialize to JSON strings
            high_school_info=high_school_info_json,
            seminary_info=seminary_info_json,
            
            # Financial Information
            tuition_payment_status=application.tuition_payment_status,
            scholarship_amount_requested=application.scholarship_amount_requested,
            amount_can_pay=application.amount_can_pay,
            financial_aid_explanation=application.financial_aid_explanation,
            
            # Dormitory and Meals Option - NEW FIELD
            dormitory_meals_option=application.dormitory_meals_option,
            
            # Additional Information
            additional_info=application.additional_info,
            
            # Documents (copy from application)
            documents=application.documents,
            
            custom_fields=custom_fields_json  # FIXED: Serialize to JSON string
        )
        
        # Copy file attachments from application to student
        # Note: This will be handled separately after the student is saved to the database
        # to avoid circular reference issues
        
        return student
    
    def copy_attachments_from_application(self):
        """Copy file attachments from the associated application to this student"""
        if not self.application:
            return
        
        # Get all attachments from the application
        app_attachments = self.application.attachments.all()
        
        for app_attachment in app_attachments:
            # Create a copy of the attachment for the student
            student_attachment = FileAttachment(
                student_id=self.id,
                field_id=app_attachment.field_id,
                field_name=app_attachment.field_name,
                original_url=app_attachment.original_url,
                original_filename=app_attachment.original_filename,
                local_filename=app_attachment.local_filename,
                file_size=app_attachment.file_size,
                mime_type=app_attachment.mime_type,
                download_status=app_attachment.download_status,
                downloaded_at=app_attachment.downloaded_at
            )
            db.session.add(student_attachment)
        
        db.session.commit()

class DivisionConfig(db.Model):
    """Configuration for each division's requirements"""
    __tablename__ = 'division_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(10), unique=True, nullable=False)  # YZA, YOH
    form_id = db.Column(db.String(10), nullable=False)  # Gravity Forms form ID
    webhook_url = db.Column(db.String(500))  # Custom webhook URL if needed
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Email configuration fields
    email_from_address = db.Column(db.String(120))  # Division-specific from email
    email_from_name = db.Column(db.String(100))     # Display name for from field
    email_reply_to = db.Column(db.String(120))      # Reply-to address
    email_bcc = db.Column(db.String(500))           # BCC addresses (comma-separated)
    
    # Email template fields
    acceptance_email_subject = db.Column(db.String(200))  # Custom email subject
    acceptance_email_body = db.Column(db.Text)            # Custom email body template
    
    # Email recipient settings
    acceptance_email_default_recipients = db.Column(db.JSON)  # ['student', 'father', 'mother']
    financial_aid_email_default_recipients = db.Column(db.JSON)  # ['student', 'father', 'mother']
    tuition_contract_email_default_recipients = db.Column(db.JSON)  # ['student', 'father', 'mother']
    enhanced_contract_email_default_recipients = db.Column(db.JSON)  # ['student', 'father', 'mother']
    general_email_default_recipients = db.Column(db.JSON)  # ['student', 'father', 'mother']
    
    # PDF template fields
    pdf_letterhead_title = db.Column(db.String(200))      # School name for PDF header
    pdf_letterhead_subtitle = db.Column(db.String(200))   # Subtitle/tagline for PDF
    pdf_letterhead_logo_path = db.Column(db.String(500))  # Path to letterhead logo image
    pdf_letterhead_logo_width = db.Column(db.Integer)     # Logo width in points (default: 150)
    pdf_letterhead_logo_height = db.Column(db.Integer)    # Logo height in points (default: 75)
    pdf_letterhead_full_width = db.Column(db.Boolean)     # Use full page width for letterhead
    pdf_letterhead_layout = db.Column(db.String(20))      # Layout: 'logo_only', 'text_only', 'logo_above_text', 'logo_beside_text'
    pdf_letterhead_background_color = db.Column(db.String(7)) # Header background color (hex)
    pdf_letterhead_text_color = db.Column(db.String(7))   # Header text color (hex)
    pdf_letterhead_margin_top = db.Column(db.Integer)     # Top margin for letterhead (default: 0)
    pdf_letterhead_margin_bottom = db.Column(db.Integer)  # Bottom margin after letterhead (default: 20)
    pdf_greeting_text = db.Column(db.Text)                # Custom greeting paragraph
    pdf_main_content = db.Column(db.Text)                 # Main acceptance content
    pdf_next_steps = db.Column(db.Text)                   # Next steps section
    pdf_closing_text = db.Column(db.Text)                 # Closing paragraph
    pdf_signature_name = db.Column(db.String(100))       # Signatory name
    pdf_signature_title = db.Column(db.String(100))      # Signatory title
    pdf_signature_image_path = db.Column(db.String(500)) # Path to signature image
    pdf_contact_info = db.Column(db.Text)                 # Footer contact information
    pdf_footer_image_path = db.Column(db.String(500))    # Path to footer letterhead image
    pdf_footer_image_width = db.Column(db.Integer)       # Footer image width in points
    pdf_footer_image_height = db.Column(db.Integer)      # Footer image height in points
    pdf_footer_background_color = db.Column(db.String(7)) # Footer background color (hex)
    
    # Kollel stipend settings (for KOLLEL division only)
    kollel_base_stipend_options = db.Column(db.String(100))      # Comma-separated options like "500,600,700"
    kollel_first_tier_credit_amount = db.Column(db.Integer)      # Amount per credit for first tier (default: 20)
    kollel_first_tier_credit_count = db.Column(db.Integer)       # Number of credits in first tier (default: 10)
    kollel_second_tier_credit_amount = db.Column(db.Integer)     # Amount per additional credit (default: 25)
    kollel_base_incentive_cap = db.Column(db.Integer)            # Cap for base + incentive (default: 1000)
    kollel_elyon_bonus = db.Column(db.Integer)                   # Kollel Elyon bonus amount (default: 1000)
    kollel_mussar_chabura_bonus = db.Column(db.Integer)          # Mussar Chabura bonus amount (default: 25)
    kollel_default_iyun_chabura_bonus = db.Column(db.Integer)    # Default Iyun Chabura bonus (default: 100)
    
    # Form Template paths
    financial_aid_form_path = db.Column(db.String(500))  # Path to uploaded financial aid form PDF
    tuition_contract_form_path = db.Column(db.String(500))  # Path to uploaded tuition contract form PDF
    
    # Tuition configuration
    requires_tuition = db.Column(db.Boolean, default=True)  # Whether this division requires tuition payment
    
    # Relationship to field mappings
    field_mappings = db.relationship('FieldMapping', backref='division_config', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<DivisionConfig {self.division}>'

class FieldMapping(db.Model):
    """Maps Gravity Forms fields to database fields for each division"""
    __tablename__ = 'field_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    division_config_id = db.Column(db.Integer, db.ForeignKey('division_configs.id'), nullable=False)
    
    # Gravity Forms field info
    gravity_field_id = db.Column(db.String(20), nullable=False)  # e.g., "95.3" for name first
    gravity_field_label = db.Column(db.String(200), nullable=False)  # Human readable
    
    # Database mapping
    database_table = db.Column(db.String(50), nullable=False)  # applications, students
    database_field = db.Column(db.String(100), nullable=False)  # student_first_name
    
    # Field properties
    field_type = db.Column(db.String(20), nullable=False)  # text, email, phone, date, etc.
    is_required = db.Column(db.Boolean, default=False)
    default_value = db.Column(db.String(500))
    validation_rules = db.Column(db.JSON)  # Custom validation rules
    
    # Processing rules
    processing_function = db.Column(db.String(100))  # Custom processing function name
    conditional_logic = db.Column(db.JSON)  # When this field should be processed
    
    # Metadata
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<FieldMapping {self.gravity_field_id} -> {self.database_field}>'

class CustomField(db.Model):
    """Custom fields that can be added to applications/students dynamically"""
    __tablename__ = 'custom_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(100), unique=True, nullable=False)  # internal name
    display_name = db.Column(db.String(200), nullable=False)  # user-friendly name
    field_type = db.Column(db.String(20), nullable=False)  # text, number, date, boolean, json
    default_value = db.Column(db.Text)
    is_required = db.Column(db.Boolean, default=False)
    validation_rules = db.Column(db.JSON)
    
    # Which divisions use this field
    divisions = db.Column(db.JSON)  # ["YZA", "YOH"] or ["YOH"] etc.
    
    # Storage location
    storage_location = db.Column(db.String(50), default='division_specific_data')  # JSON field name
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CustomField {self.field_name}>'

class AcademicYear(db.Model):
    """Academic year configuration and management"""
    __tablename__ = 'academic_years'
    
    id = db.Column(db.Integer, primary_key=True)
    year_label = db.Column(db.String(20), unique=True, nullable=False)  # "2025-2026"
    start_date = db.Column(db.Date, nullable=False)  # Academic year start date
    end_date = db.Column(db.Date, nullable=False)    # Academic year end date
    is_active = db.Column(db.Boolean, default=False)  # Currently active year
    is_current = db.Column(db.Boolean, default=False)  # Current enrollment year
    tuition_due_date = db.Column(db.Date)  # When tuition is due for this year
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to tuition records
    tuition_records = db.relationship('TuitionRecord', backref='academic_year', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AcademicYear {self.year_label}>'
    
    @property
    def status_badge(self):
        """Return status for display"""
        if self.is_active:
            return 'Active'
        elif self.is_current:
            return 'Current'
        else:
            return 'Archived'
    
    @property
    def status_color(self):
        """Return Bootstrap color class"""
        if self.is_active:
            return 'success'
        elif self.is_current:
            return 'primary'
        else:
            return 'secondary'
    
    @classmethod
    def get_active_year(cls):
        """Get the currently active academic year"""
        return cls.query.filter_by(is_active=True).first()
    
    @classmethod
    def get_current_year(cls):
        """Get the current enrollment year"""
        return cls.query.filter_by(is_current=True).first()
    
    @classmethod
    def create_next_year(cls):
        """Create the next academic year automatically"""
        current_year = cls.get_current_year()
        if not current_year:
            # If no current year, create 2024-2025 as starting point
            start_year = 2024
        else:
            # Extract year from current year label (e.g., "2024-2025" -> 2025)
            start_year = int(current_year.year_label.split('-')[1])
        
        next_year_label = f"{start_year}-{start_year + 1}"
        
        # Check if next year already exists
        if cls.query.filter_by(year_label=next_year_label).first():
            return None
        
        from datetime import date
        next_year = cls(
            year_label=next_year_label,
            start_date=date(start_year, 8, 1),  # August 1st
            end_date=date(start_year + 1, 7, 31),  # July 31st
            tuition_due_date=date(start_year, 6, 1)  # June 1st
        )
        
        db.session.add(next_year)
        db.session.commit()
        return next_year

class TuitionRecord(db.Model):
    """Tuition record for a specific student and academic year"""
    __tablename__ = 'tuition_records'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Financial Aid Information
    financial_aid_type = db.Column(db.String(50), default='Full Tuition')  # 'Full Tuition', 'Financial Aid'
    financial_aid_app_sent = db.Column(db.Boolean, default=False)
    financial_aid_app_sent_date = db.Column(db.DateTime)
    financial_aid_app_received = db.Column(db.Boolean, default=False)
    financial_aid_app_received_date = db.Column(db.DateTime)
    
    # Tuition Determination
    tuition_determination = db.Column(db.Numeric(10, 2))  # Final tuition amount
    tuition_amount = db.Column(db.Numeric(10, 2))  # Alias for tuition_determination for compatibility
    tuition_determination_notes = db.Column(db.Text)
    tuition_determination_date = db.Column(db.DateTime)
    tuition_type = db.Column(db.String(50))  # 'Full Tuition', 'Reduced Tuition', 'Full Scholarship'
    
    # Contract & E-Signature
    tuition_contract_generated = db.Column(db.Boolean, default=False)
    tuition_contract_generated_date = db.Column(db.DateTime)
    tuition_contract_sent = db.Column(db.Boolean, default=False)
    tuition_contract_sent_date = db.Column(db.DateTime)
    tuition_contract_signed = db.Column(db.Boolean, default=False)
    tuition_contract_signed_date = db.Column(db.DateTime)
    tuition_contract_pdf_path = db.Column(db.String(500))
    
    # OpenSign Integration
    dropbox_sign_signature_request_id = db.Column(db.String(100))
    dropbox_sign_status = db.Column(db.String(20))
    dropbox_sign_signed_url = db.Column(db.String(500))
    dropbox_sign_files_url = db.Column(db.String(500))
    dropbox_sign_template_id = db.Column(db.String(100))
    
    # Matriculation Status
    matriculation_status = db.Column(db.String(20), default='Auto')  # 'Matriculating', 'Non-Matriculating', 'Auto'
    matriculation_override = db.Column(db.Boolean, default=False)  # Manual override flag
    high_school_graduation_date = db.Column(db.Date)  # When they graduated high school
    program_graduation_date = db.Column(db.Date)  # When they graduated our program
    matriculation_notes = db.Column(db.Text)  # Additional notes about matriculation status
    
    # FAFSA Information
    fafsa_eligible = db.Column(db.String(20))  # 'Eligible', 'Not Eligible', 'Unknown'
    fafsa_required = db.Column(db.Boolean, default=False)
    fafsa_applied = db.Column(db.Boolean, default=False)
    fafsa_application_date = db.Column(db.DateTime)
    fafsa_status = db.Column(db.String(20), default='Pending')
    fafsa_amount_awarded = db.Column(db.Numeric(10, 2))
    fafsa_notes = db.Column(db.Text)
    
    # Payment Information
    payment_status = db.Column(db.String(50))  # 'Paid', 'Partial', 'Pending', 'Overdue'
    amount_paid = db.Column(db.Numeric(10, 2), default=0)
    payment_plan = db.Column(db.String(50))  # 'Full', 'Installments', 'Monthly'
    payment_due_date = db.Column(db.Date)
    
    # Matriculation Status for this Academic Year
    matriculation_status_for_year = db.Column(db.String(20))  # 'Matriculating', 'Non-Matriculating' - captured at time of record creation
    
    # Enhanced contract terms (JSON storage for payment schedule, terms, etc.)
    contract_terms = db.Column(db.JSON)  # Store enhanced contract terms as JSON
    final_tuition_amount = db.Column(db.Numeric(10, 2))  # Final calculated tuition (after adjustments)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint to prevent duplicate records for same student/year
    __table_args__ = (db.UniqueConstraint('student_id', 'academic_year_id', name='unique_student_year'),)
    
    def __repr__(self):
        return f'<TuitionRecord {self.student_id} - {self.academic_year.year_label}>'
    
    @property
    def payment_status_color(self):
        """Return Bootstrap color class for payment status"""
        colors = {
            'Paid': 'success',
            'Partial': 'warning',
            'Pending': 'info',
            'Overdue': 'danger'
        }
        return colors.get(self.payment_status, 'secondary')
    
    @property
    def contract_status(self):
        """Get comprehensive contract status"""
        if self.opensign_document_status == 'completed':
            return 'Signed'
        elif self.opensign_document_status == 'pending':
            return 'Pending Signature'
        elif self.opensign_document_status == 'declined':
            return 'Declined'
        elif self.opensign_document_status == 'expired':
            return 'Expired'
        elif self.tuition_contract_sent:
            return 'Sent'
        elif self.tuition_contract_generated:
            return 'Generated'
        else:
            return 'Not Generated'
    
    @property
    def financial_aid_info(self):
        """Get formatted financial aid information"""
        return {
            'payment_status': self.payment_status or 'Pending',
            'amount_can_pay': 0.0,  # Not stored in TuitionRecord
            'scholarship_requested': 0.0,  # Not stored in TuitionRecord
            'explanation': '',  # Not stored in TuitionRecord
            'financial_aid_type': self.financial_aid_type or 'Full Tuition',
            'financial_aid_app_sent': self.financial_aid_app_sent,
            'financial_aid_app_received': self.financial_aid_app_received,
            'tuition_determination': float(self.tuition_determination) if self.tuition_determination else 0.0,
            'tuition_determination_notes': self.tuition_determination_notes or '',
            'tuition_contract_generated': self.tuition_contract_generated,
            'tuition_contract_sent': self.tuition_contract_sent,
            'tuition_contract_signed': self.tuition_contract_signed,
            'opensign_document_id': self.opensign_document_id,
            'opensign_document_status': self.opensign_document_status,
            'opensign_signed_url': self.opensign_signed_url,
            'opensign_certificate_url': self.opensign_certificate_url,
            'fafsa_eligible': self.fafsa_eligible or 'Unknown',
            'fafsa_required': self.fafsa_required,
            'fafsa_applied': self.fafsa_applied,
            'fafsa_status': self.fafsa_status or 'Pending',
            'fafsa_amount_awarded': float(self.fafsa_amount_awarded) if self.fafsa_amount_awarded else 0.0,
            'fafsa_notes': self.fafsa_notes or '',
            'tuition_contract_pdf_path': self.tuition_contract_pdf_path or ''
        }
    
    @property
    def tuition_components_summary(self):
        """Get summary of tuition components for this record"""
        components = StudentTuitionComponent.query.filter_by(
            student_id=self.student_id,
            academic_year_id=self.academic_year_id,
            is_active=True
        ).join(TuitionComponent).order_by(TuitionComponent.display_order).all()
        
        total_amount = 0
        total_paid = 0
        total_balance = 0
        
        component_details = []
        for comp in components:
            calculated_amount = comp.calculated_amount
            total_amount += calculated_amount
            total_paid += (comp.amount_paid or 0)
            total_balance += comp.calculate_balance()
            
            component_details.append({
                'name': comp.component.name,
                'type': comp.component.component_type,
                'original_amount': float(comp.original_amount or 0),
                'amount': float(calculated_amount),
                'discount_amount': float(comp.discount_amount or 0),
                'discount_percentage': float(comp.discount_percentage or 0),
                'is_prorated': comp.is_prorated,
                'proration_percentage': float(comp.proration_percentage or 100),
                'amount_paid': float(comp.amount_paid or 0),
                'balance_due': float(comp.calculate_balance()),
                'is_override': comp.is_override,
                'override_reason': comp.override_reason or '',
                'notes': comp.notes or ''
            })
        
        return {
            'components': component_details,
            'total_amount': float(total_amount),
            'total_paid': float(total_paid),
            'total_balance': float(total_balance),
            'component_count': len(component_details)
        }

def init_db():
    """Initialize the database with default data"""
    from extensions import db
    
    # Create all tables
    db.create_all()
    
    # Create default permissions
    for perm_name in Permission.get_all_permissions():
        existing_perm = Permission.query.filter_by(name=perm_name).first()
        if not existing_perm:
            perm = Permission(perm_name)
            db.session.add(perm)
    
    # Create default admin user if not exists
    admin_user = User.query.filter_by(email='admin@example.com').first()
    if not admin_user:
        admin_user = User(
            email='admin@example.com',
            username='admin',
            first_name='System',
            last_name='Administrator',
            is_admin=True
        )
        admin_user.password = 'admin123'  # Change this in production
        db.session.add(admin_user)
    
    # Create default dormitories if none exist
    Dormitory.create_default_dormitories()
    
    db.session.commit()
    print("Database initialized successfully!")

class KollelBreak(db.Model):
    """Tracks scheduled breaks during the academic year for pro-rated credit calculations"""
    __tablename__ = 'kollel_breaks'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Winter Break", "Pesach Break", etc.
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    prorated_credits_per_student = db.Column(db.Numeric(5, 2), default=0)  # Credits to assign during break
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    academic_year = db.relationship('AcademicYear', backref='kollel_breaks')
    
    def __repr__(self):
        return f'<KollelBreak {self.name} ({self.start_date} - {self.end_date})>'
    
    @property
    def duration_days(self):
        """Calculate the duration of the break in days"""
        return (self.end_date - self.start_date).days + 1
    
    def is_date_in_break(self, check_date):
        """Check if a given date falls within this break period"""
        return self.start_date <= check_date <= self.end_date

class KollelStudent(db.Model):
    """Kollel-specific student information and settings"""
    __tablename__ = 'kollel_students'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False, unique=True)
    
    # Base stipend settings
    base_stipend_amount = db.Column(db.Numeric(8, 2), nullable=False)  # 500, 600, or 700
    
    # Kollel level and bonus eligibility
    is_kollel_elyon = db.Column(db.Boolean, default=False)  # Eligible for 1000 bonus
    retufin_pay_eligible = db.Column(db.Boolean, default=False)  # Eligible for retufin pay
    mussar_chabura_eligible = db.Column(db.Boolean, default=False)  # Eligible for mussar chabura (25)
    iyun_chabura_eligible = db.Column(db.Boolean, default=False)  # Eligible for iyun chabura
    
    # Default amounts (can be overridden per month)
    default_retufin_amount = db.Column(db.Numeric(8, 2), default=0)
    default_iyun_chabura_amount = db.Column(db.Numeric(8, 2), default=0)
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    date_joined_kollel = db.Column(db.Date)
    date_left_kollel = db.Column(db.Date)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='kollel_info')
    stipend_records = db.relationship('KollelStipend', backref='kollel_student', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<KollelStudent {self.student.student_name if self.student else "Unknown"}>'
    
    @property
    def kollel_elyon_bonus(self):
        """Return Kollel Elyon bonus amount (1000 if eligible)"""
        return 1000 if self.is_kollel_elyon else 0
    
    @property
    def mussar_chabura_amount(self):
        """Return Mussar Chabura amount (25 if eligible)"""
        return 25 if self.mussar_chabura_eligible else 0

class KollelStipend(db.Model):
    """Monthly stipend record for Kollel students"""
    __tablename__ = 'kollel_stipends'
    
    id = db.Column(db.Integer, primary_key=True)
    kollel_student_id = db.Column(db.Integer, db.ForeignKey('kollel_students.id'), nullable=False)
    
    # Time period
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)   # 2024, 2025, etc.
    
    # Credit tracking
    actual_credits_earned = db.Column(db.Numeric(5, 2), default=0)  # Credits earned during regular time
    prorated_credits = db.Column(db.Numeric(5, 2), default=0)      # Credits from break pro-ration
    total_credits = db.Column(db.Numeric(5, 2), default=0)         # actual + prorated
    credits_override = db.Column(db.Boolean, default=False)        # Manual override flag
    credits_override_reason = db.Column(db.Text)                   # Reason for override
    
    # Base stipend
    base_stipend_amount = db.Column(db.Numeric(8, 2), nullable=False)  # 500, 600, or 700
    
    # Incentive calculation
    incentive_credits = db.Column(db.Numeric(5, 2), default=0)     # Credits used for incentive calculation
    incentive_amount = db.Column(db.Numeric(8, 2), default=0)     # Calculated incentive pay
    base_plus_incentive = db.Column(db.Numeric(8, 2), default=0)  # Base + incentive (capped at 1000)
    
    # Bonus payments
    kollel_elyon_bonus = db.Column(db.Numeric(8, 2), default=0)   # 1000 if eligible
    retufin_pay = db.Column(db.Numeric(8, 2), default=0)          # Variable amount
    mussar_chabura_pay = db.Column(db.Numeric(8, 2), default=0)   # 25 if eligible
    iyun_chabura_pay = db.Column(db.Numeric(8, 2), default=0)     # Variable amount
    special_pay = db.Column(db.Numeric(8, 2), default=0)          # Work study, etc.
    
    # Deductions
    missed_time_deduction = db.Column(db.Numeric(8, 2), default=0)  # Deduction for missed time
    other_deductions = db.Column(db.Numeric(8, 2), default=0)       # Other deductions
    deduction_notes = db.Column(db.Text)                            # Notes about deductions
    
    # Calculated totals
    total_bonus = db.Column(db.Numeric(8, 2), default=0)           # Sum of all bonuses
    total_deductions = db.Column(db.Numeric(8, 2), default=0)      # Sum of all deductions
    final_amount = db.Column(db.Numeric(8, 2), default=0)          # Final stipend amount
    
    # Payment tracking
    payment_status = db.Column(db.String(20), default='Pending')   # 'Pending', 'Paid', 'Cancelled'
    payment_date = db.Column(db.Date)                              # When payment was made
    payment_method = db.Column(db.String(50))                      # 'Check', 'Direct Deposit', etc.
    payment_reference = db.Column(db.String(100))                  # Check number, transaction ID, etc.
    
    # Administrative fields
    notes = db.Column(db.Text)                                     # Additional notes
    created_by = db.Column(db.String(100))                         # User who created the record
    approved_by = db.Column(db.String(100))                        # User who approved payment
    approved_date = db.Column(db.DateTime)                         # When payment was approved
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint to prevent duplicate records for same student/month/year
    __table_args__ = (db.UniqueConstraint('kollel_student_id', 'month', 'year', name='unique_student_month_year'),)
    
    def __repr__(self):
        return f'<KollelStipend {self.kollel_student.student.student_name if self.kollel_student and self.kollel_student.student else "Unknown"} {self.month}/{self.year}>'
    
    @property
    def month_year_display(self):
        """Return formatted month/year display"""
        month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']
        return f"{month_names[self.month]} {self.year}"
    
    @property
    def payment_status_color(self):
        """Return Bootstrap color class for payment status"""
        status_colors = {
            'Pending': 'warning',
            'Paid': 'success',
            'Cancelled': 'danger'
        }
        return status_colors.get(self.payment_status, 'secondary')
    
    def calculate_incentive_pay(self):
        """Calculate incentive pay based on credits - must earn at least 10 credits to get any incentive"""
        if self.total_credits < 10:
            # No incentive if under 10 credits
            self.incentive_amount = 0
        elif self.total_credits == 10:
            # Base incentive for exactly 10 credits
            self.incentive_amount = 200
        else:
            # Base 200 for first 10 credits, then 25 per additional credit
            additional_credits = self.total_credits - 10
            self.incentive_amount = 200 + (additional_credits * 25)
        
        # Calculate base + incentive (capped at 1000)
        self.base_plus_incentive = min(self.base_stipend_amount + self.incentive_amount, 1000)
        
        return self.incentive_amount
    
    def calculate_totals(self):
        """Calculate all totals for this stipend record"""
        from decimal import Decimal, ROUND_DOWN
        
        # Calculate total credits using floored prorated credits for payment purposes
        # but preserve the decimal value in prorated_credits for display/special exceptions
        prorated_for_payment = Decimal(str(self.prorated_credits or 0)).quantize(Decimal('1'), rounding=ROUND_DOWN)
        self.total_credits = (self.actual_credits_earned or 0) + prorated_for_payment
        
        # Calculate incentive pay using the floored total credits
        self.calculate_incentive_pay()
        
        # Calculate total bonus
        self.total_bonus = (self.kollel_elyon_bonus + self.retufin_pay + 
                           self.mussar_chabura_pay + self.iyun_chabura_pay)
        
        # Calculate total deductions
        self.total_deductions = self.missed_time_deduction + self.other_deductions
        
        # Calculate final amount
        self.final_amount = self.base_plus_incentive + self.total_bonus + (self.special_pay or 0) - self.total_deductions
        
        return self.final_amount
    
    def apply_prorated_credits(self, prorated_amount):
        """Apply pro-rated credits from break periods"""
        self.prorated_credits = prorated_amount
        self.total_credits = self.actual_credits_earned + self.prorated_credits
        self.calculate_totals()
    
    @classmethod
    def get_or_create_for_month(cls, kollel_student_id, month, year):
        """Get existing record or create new one for the specified month/year"""
        existing = cls.query.filter_by(
            kollel_student_id=kollel_student_id,
            month=month,
            year=year
        ).first()
        
        if existing:
            return existing
        
        # Get the KollelStudent record to set defaults
        kollel_student = KollelStudent.query.get(kollel_student_id)
        if not kollel_student:
            return None
        
        # Create new record with default values
        new_record = cls(
            kollel_student_id=kollel_student_id,
            month=month,
            year=year,
            base_stipend_amount=kollel_student.base_stipend_amount,
            kollel_elyon_bonus=kollel_student.kollel_elyon_bonus,
            retufin_pay=kollel_student.default_retufin_amount,
            mussar_chabura_pay=kollel_student.mussar_chabura_amount,
            iyun_chabura_pay=kollel_student.default_iyun_chabura_amount
        )
        
        db.session.add(new_record)
        db.session.commit()
        
        return new_record
    
    @classmethod
    def calculate_prorated_credits_for_breaks(cls, month, year, academic_year_id):
        """Calculate pro-rated credits for all students based on breaks in the specified month"""
        from datetime import date, timedelta
        import calendar
        
        # Get all breaks for the academic year that overlap with this month
        breaks = KollelBreak.query.filter_by(
            academic_year_id=academic_year_id,
            is_active=True
        ).all()
        
        # Calculate the month's date range
        month_start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        month_end = date(year, month, last_day)
        
        # Find breaks that overlap with this month
        overlapping_breaks = []
        for break_obj in breaks:
            if (break_obj.start_date <= month_end and break_obj.end_date >= month_start):
                # Calculate overlap days
                overlap_start = max(break_obj.start_date, month_start)
                overlap_end = min(break_obj.end_date, month_end)
                overlap_days = (overlap_end - overlap_start).days + 1
                
                overlapping_breaks.append({
                    'break': break_obj,
                    'overlap_days': overlap_days
                })
        
        if not overlapping_breaks:
            return 0  # No breaks in this month
        
        # Calculate pro-rated credits based on previous 5 months
        # This is a simplified calculation - you may want to make this more sophisticated
        total_prorated_credits = 0
        for break_info in overlapping_breaks:
            # For now, use the prorated_credits_per_student from the break record
            # In a more sophisticated system, you'd calculate this based on 
            # the student's average credits from the previous 5 months
            daily_prorated = break_info['break'].prorated_credits_per_student / break_info['break'].duration_days
            total_prorated_credits += daily_prorated * break_info['overlap_days']
        
        return total_prorated_credits 

# Create aliases for kollel models to support both naming conventions
MonthlyStipend = KollelStipend  # Alias for backward compatibility
KollelBreakCredit = KollelBreak  # Alias for backward compatibility

class StipendHistory(db.Model):
    """Audit log for monthly stipend changes"""
    __tablename__ = 'stipend_history'
    
    id = db.Column(db.Integer, primary_key=True)
    monthly_stipend_id = db.Column(db.Integer, db.ForeignKey('kollel_stipends.id'), nullable=False)
    
    # Change information
    change_type = db.Column(db.String(20), nullable=False)  # 'CREATE', 'UPDATE', 'DELETE'
    change_description = db.Column(db.Text)  # Human-readable description
    changed_fields = db.Column(db.JSON)  # JSON object of field changes
    
    # User tracking
    changed_by = db.Column(db.String(100), nullable=False)  # Username who made the change
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Additional metadata
    ip_address = db.Column(db.String(45))  # IP address of user
    user_agent = db.Column(db.String(255))  # Browser/client info
    
    # Relationship
    monthly_stipend = db.relationship('KollelStipend', backref='history_records')
    
    def __repr__(self):
        return f'<StipendHistory {self.change_type} by {self.changed_by} at {self.changed_at}>'

# ========================= DORMITORY MANAGEMENT SYSTEM =========================

class Dormitory(db.Model):
    """Dormitory building management"""
    __tablename__ = 'dormitories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # "Beis Medrash", "Main Building", etc.
    display_name = db.Column(db.String(150))  # Optional display name for UI
    description = db.Column(db.Text)  # Optional description
    address = db.Column(db.String(500))  # Physical address
    capacity = db.Column(db.Integer, default=0)  # Total bed capacity (calculated)
    
    # Visual settings for map display
    map_color = db.Column(db.String(7), default='#3498db')  # Hex color for visual representation
    map_position_x = db.Column(db.Integer, default=0)  # X position on visual map
    map_position_y = db.Column(db.Integer, default=0)  # Y position on visual map
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    allows_assignments = db.Column(db.Boolean, default=True)  # Whether students can be assigned
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    rooms = db.relationship('Room', backref='dormitory', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Dormitory {self.name}>'
    
    @property
    def total_rooms(self):
        """Get total number of rooms in this dormitory"""
        return self.rooms.count()
    
    @property
    def total_beds(self):
        """Get total number of beds in this dormitory"""
        return sum(room.bed_count for room in self.rooms)
    
    @property
    def occupied_beds(self):
        """Get number of occupied beds in this dormitory"""
        return sum(room.occupied_beds for room in self.rooms)
    
    @property
    def available_beds(self):
        """Get number of available beds in this dormitory"""
        return self.total_beds - self.occupied_beds
    
    @property
    def occupancy_rate(self):
        """Get occupancy rate as percentage"""
        if self.total_beds == 0:
            return 0
        return round((self.occupied_beds / self.total_beds) * 100, 1)
    
    @property
    def status_color(self):
        """Get status color based on occupancy"""
        rate = self.occupancy_rate
        if rate >= 90:
            return 'danger'  # Nearly full
        elif rate >= 75:
            return 'warning'  # Getting full
        elif rate >= 50:
            return 'info'  # Half full
        else:
            return 'success'  # Plenty of space
    
    def get_room_by_number(self, room_number):
        """Get room by room number"""
        return self.rooms.filter_by(room_number=room_number).first()
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name or self.name,
            'description': self.description,
            'address': self.address,
            'total_rooms': self.total_rooms,
            'total_beds': self.total_beds,
            'occupied_beds': self.occupied_beds,
            'available_beds': self.available_beds,
            'occupancy_rate': self.occupancy_rate,
            'status_color': self.status_color,
            'map_color': self.map_color,
            'map_position_x': self.map_position_x,
            'map_position_y': self.map_position_y,
            'is_active': self.is_active,
            'allows_assignments': self.allows_assignments,
            'notes': self.notes
        }
    
    @classmethod
    def create_default_dormitories(cls):
        """Create default dormitories if none exist"""
        if cls.query.count() == 0:
            dormitories = [
                cls(name='Main Building', description='Primary dormitory building', map_position_x=100, map_position_y=100),
                cls(name='Beis Medrash Building', description='Study hall dormitory', map_position_x=300, map_position_y=100),
                cls(name='Auxiliary Building', description='Additional dormitory space', map_position_x=200, map_position_y=250)
            ]
            
            for dorm in dormitories:
                db.session.add(dorm)
            
            db.session.commit()
            return dormitories
        return []

class Room(db.Model):
    """Room within a dormitory"""
    __tablename__ = 'rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    dormitory_id = db.Column(db.Integer, db.ForeignKey('dormitories.id'), nullable=False)
    room_number = db.Column(db.String(20), nullable=False)  # "101", "A-15", etc.
    room_name = db.Column(db.String(100))  # Optional friendly name
    floor = db.Column(db.Integer)  # Floor number
    room_type = db.Column(db.String(50), default='Standard')  # Standard, Suite, Single, etc.
    
    # Capacity and features
    bed_count = db.Column(db.Integer, default=2)  # Number of beds in this room
    has_private_bathroom = db.Column(db.Boolean, default=False)
    has_air_conditioning = db.Column(db.Boolean, default=True)
    has_heating = db.Column(db.Boolean, default=True)
    amenities = db.Column(db.JSON)  # List of amenities like ["Desk", "Chair", "Closet"]
    
    # Visual settings for map display
    map_position_x = db.Column(db.Integer, default=0)  # X position within dormitory layout
    map_position_y = db.Column(db.Integer, default=0)  # Y position within dormitory layout
    map_width = db.Column(db.Integer, default=80)  # Width for visual representation
    map_height = db.Column(db.Integer, default=60)  # Height for visual representation
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    allows_assignments = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    beds = db.relationship('Bed', backref='room', lazy='dynamic', cascade='all, delete-orphan')
    
    # Unique constraint within dormitory
    __table_args__ = (db.UniqueConstraint('dormitory_id', 'room_number', name='unique_room_number_per_dorm'),)
    
    def __repr__(self):
        return f'<Room {self.dormitory.name} - {self.room_number}>'
    
    @property
    def full_room_name(self):
        """Get full room identifier"""
        return f"{self.dormitory.name} - Room {self.room_number}"
    
    @property
    def occupied_beds(self):
        """Get number of occupied beds in this room"""
        return self.beds.join(BedAssignment).filter(BedAssignment.is_active == True).count()
    
    @property
    def available_beds(self):
        """Get number of available beds in this room"""
        return self.bed_count - self.occupied_beds
    
    @property
    def occupancy_rate(self):
        """Get occupancy rate as percentage"""
        if self.bed_count == 0:
            return 0
        return round((self.occupied_beds / self.bed_count) * 100, 1)
    
    @property
    def status_color(self):
        """Get status color based on occupancy"""
        if self.occupied_beds == self.bed_count:
            return 'danger'  # Full
        elif self.occupied_beds > 0:
            return 'warning'  # Partially occupied
        else:
            return 'success'  # Available
    
    @property
    def current_occupants(self):
        """Get list of current student occupants"""
        assignments = BedAssignment.query.join(Bed).filter(
            Bed.room_id == self.id,
            BedAssignment.is_active == True
        ).all()
        return [assignment.student for assignment in assignments if assignment.student]
    
    def get_bed_by_number(self, bed_number):
        """Get bed by bed number"""
        return self.beds.filter_by(bed_number=bed_number).first()
    
    def create_beds(self):
        """Create beds based on bed_count"""
        # Remove excess beds if bed_count was reduced
        current_beds = self.beds.count()
        if current_beds > self.bed_count:
            excess_beds = self.beds.offset(self.bed_count).all()
            for bed in excess_beds:
                db.session.delete(bed)
        
        # Add beds if bed_count was increased
        elif current_beds < self.bed_count:
            for i in range(current_beds + 1, self.bed_count + 1):
                bed = Bed(
                    room_id=self.id,
                    bed_number=str(i),
                    bed_type='Standard'
                )
                db.session.add(bed)
        
        db.session.commit()
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'dormitory_id': self.dormitory_id,
            'dormitory_name': self.dormitory.name,
            'room_number': self.room_number,
            'room_name': self.room_name,
            'full_room_name': self.full_room_name,
            'floor': self.floor,
            'room_type': self.room_type,
            'bed_count': self.bed_count,
            'occupied_beds': self.occupied_beds,
            'available_beds': self.available_beds,
            'occupancy_rate': self.occupancy_rate,
            'status_color': self.status_color,
            'has_private_bathroom': self.has_private_bathroom,
            'has_air_conditioning': self.has_air_conditioning,
            'has_heating': self.has_heating,
            'amenities': self.amenities or [],
            'map_position_x': self.map_position_x,
            'map_position_y': self.map_position_y,
            'map_width': self.map_width,
            'map_height': self.map_height,
            'is_active': self.is_active,
            'allows_assignments': self.allows_assignments,
            'notes': self.notes,
            'current_occupants': [student.student_name for student in self.current_occupants]
        }

class Bed(db.Model):
    """Individual bed within a room"""
    __tablename__ = 'beds'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    bed_number = db.Column(db.String(10), nullable=False)  # "1", "2", "A", "B", etc.
    bed_type = db.Column(db.String(50), default='Standard')  # Standard, Twin, Full, Bunk, etc.
    
    # Bed features
    is_top_bunk = db.Column(db.Boolean, default=False)  # For bunk beds
    is_bottom_bunk = db.Column(db.Boolean, default=False)  # For bunk beds
    has_desk = db.Column(db.Boolean, default=True)
    has_dresser = db.Column(db.Boolean, default=True)
    has_closet = db.Column(db.Boolean, default=True)
    
    # Visual settings for room layout
    map_position_x = db.Column(db.Integer, default=0)  # X position within room
    map_position_y = db.Column(db.Integer, default=0)  # Y position within room
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    allows_assignments = db.Column(db.Boolean, default=True)
    condition = db.Column(db.String(20), default='Good')  # Good, Fair, Needs Repair, Out of Order
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    assignments = db.relationship('BedAssignment', backref='bed', lazy='dynamic', cascade='all, delete-orphan')
    
    # Unique constraint within room
    __table_args__ = (db.UniqueConstraint('room_id', 'bed_number', name='unique_bed_number_per_room'),)
    
    def __repr__(self):
        return f'<Bed {self.room.full_room_name} - Bed {self.bed_number}>'
    
    @property
    def full_bed_name(self):
        """Get full bed identifier"""
        return f"{self.room.full_room_name} - Bed {self.bed_number}"
    
    @property
    def is_occupied(self):
        """Check if bed is currently occupied"""
        return self.assignments.filter_by(is_active=True).first() is not None
    
    @property
    def current_assignment(self):
        """Get current active assignment"""
        return self.assignments.filter_by(is_active=True).first()
    
    @property
    def current_occupant(self):
        """Get current student occupant"""
        assignment = self.current_assignment
        return assignment.student if assignment else None
    
    @property
    def status_color(self):
        """Get status color based on occupancy and condition"""
        if not self.allows_assignments or self.condition == 'Out of Order':
            return 'secondary'  # Unavailable
        elif self.is_occupied:
            return 'danger'  # Occupied
        elif self.condition in ['Needs Repair', 'Fair']:
            return 'warning'  # Available but needs attention
        else:
            return 'success'  # Available and ready
    
    @property
    def status_text(self):
        """Get human-readable status"""
        if not self.allows_assignments:
            return 'Not Available'
        elif self.condition == 'Out of Order':
            return 'Out of Order'
        elif self.is_occupied:
            occupant = self.current_occupant
            return f'Occupied by {occupant.student_name}' if occupant else 'Occupied'
        else:
            return 'Available'
    
    def assign_student(self, student_id, start_date=None, assigned_by=None, notes=None):
        """Assign a student to this bed"""
        from datetime import date
        
        if self.is_occupied:
            raise ValueError(f"Bed {self.full_bed_name} is already occupied")
        
        if not self.allows_assignments or self.condition == 'Out of Order':
            raise ValueError(f"Bed {self.full_bed_name} is not available for assignment")
        
        # Create new assignment
        assignment = BedAssignment(
            student_id=student_id,
            bed_id=self.id,
            start_date=start_date or date.today(),
            assigned_by=assigned_by,
            notes=notes
        )
        
        db.session.add(assignment)
        return assignment
    
    def unassign_current_occupant(self, end_date=None, reason=None, ended_by=None):
        """End current assignment"""
        from datetime import date
        
        current = self.current_assignment
        if not current:
            raise ValueError(f"Bed {self.full_bed_name} is not currently occupied")
        
        current.end_date = end_date or date.today()
        current.end_reason = reason or 'Manual Unassignment'
        current.ended_by = ended_by
        current.is_active = False
        
        return current
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        current_assignment = self.current_assignment
        return {
            'id': self.id,
            'room_id': self.room_id,
            'room_name': self.room.full_room_name,
            'bed_number': self.bed_number,
            'full_bed_name': self.full_bed_name,
            'bed_type': self.bed_type,
            'is_top_bunk': self.is_top_bunk,
            'is_bottom_bunk': self.is_bottom_bunk,
            'has_desk': self.has_desk,
            'has_dresser': self.has_dresser,
            'has_closet': self.has_closet,
            'map_position_x': self.map_position_x,
            'map_position_y': self.map_position_y,
            'is_active': self.is_active,
            'allows_assignments': self.allows_assignments,
            'condition': self.condition,
            'is_occupied': self.is_occupied,
            'status_color': self.status_color,
            'status_text': self.status_text,
            'notes': self.notes,
            'current_occupant': {
                'id': current_assignment.student.id,
                'name': current_assignment.student.student_name,
                'division': current_assignment.student.division,
                'start_date': current_assignment.start_date.isoformat() if current_assignment.start_date else None
            } if current_assignment and current_assignment.student else None
        }

class BedAssignment(db.Model):
    """Assignment of a student to a bed"""
    __tablename__ = 'bed_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'), nullable=False)
    
    # Assignment period
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)  # NULL for active assignments
    is_active = db.Column(db.Boolean, default=True)
    
    # Assignment management
    assigned_by = db.Column(db.String(100))  # Username who made the assignment
    ended_by = db.Column(db.String(100))  # Username who ended the assignment
    end_reason = db.Column(db.String(100))  # Reason for ending assignment
    
    # Additional information
    notes = db.Column(db.Text)
    priority = db.Column(db.Integer, default=1)  # For handling conflicts
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='bed_assignments')
    
    def __repr__(self):
        return f'<BedAssignment {self.student.student_name if self.student else "Unknown"} -> {self.bed.full_bed_name if self.bed else "Unknown"}>'
    
    @property
    def duration_days(self):
        """Calculate assignment duration in days"""
        from datetime import date
        end_date = self.end_date or date.today()
        return (end_date - self.start_date).days + 1
    
    @property
    def status_text(self):
        """Get human-readable status"""
        if self.is_active:
            return 'Active'
        elif self.end_date:
            return f'Ended on {self.end_date.strftime("%Y-%m-%d")}'
        else:
            return 'Inactive'
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': self.student.student_name if self.student else None,
            'student_division': self.student.division if self.student else None,
            'bed_id': self.bed_id,
            'bed_name': self.bed.full_bed_name if self.bed else None,
            'room_name': self.bed.room.full_room_name if self.bed and self.bed.room else None,
            'dormitory_name': self.bed.room.dormitory.name if self.bed and self.bed.room and self.bed.room.dormitory else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'is_active': self.is_active,
            'duration_days': self.duration_days,
            'status_text': self.status_text,
            'assigned_by': self.assigned_by,
            'ended_by': self.ended_by,
            'end_reason': self.end_reason,
            'notes': self.notes,
            'priority': self.priority
        }
    
    @classmethod
    def get_current_assignment_for_student(cls, student_id):
        """Get current active bed assignment for a student"""
        return cls.query.filter_by(student_id=student_id, is_active=True).first()
    
    @classmethod
    def get_assignment_history_for_student(cls, student_id):
        """Get all bed assignments for a student (current and past)"""
        return cls.query.filter_by(student_id=student_id).order_by(cls.start_date.desc()).all()
    
    @classmethod
    def get_assignments_for_bed(cls, bed_id):
        """Get all assignments for a specific bed"""
        return cls.query.filter_by(bed_id=bed_id).order_by(cls.start_date.desc()).all()

class ReportTemplate(db.Model):
    """Model for storing saved report templates"""
    __tablename__ = 'report_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    report_type = db.Column(db.String(100), nullable=False)  # 'students', 'applications', 'financial', 'dormitory', etc.
    
    # Report configuration stored as JSON
    fields = db.Column(db.JSON)  # List of field names to include
    filters = db.Column(db.JSON)  # Filter conditions
    sorting = db.Column(db.JSON)  # Sort configuration
    grouping = db.Column(db.JSON)  # Grouping configuration
    formatting = db.Column(db.JSON)  # Display formatting options
    
    # Metadata
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used = db.Column(db.DateTime)
    use_count = db.Column(db.Integer, default=0)
    
    # Access control
    is_public = db.Column(db.Boolean, default=False)  # Can be used by other users
    allowed_users = db.Column(db.JSON)  # List of usernames who can access this template
    allowed_roles = db.Column(db.JSON)  # List of roles that can access this template
    
    # Settings
    is_active = db.Column(db.Boolean, default=True)
    auto_refresh = db.Column(db.Boolean, default=True)  # Whether to refresh data each time
    
    # Relationships
    executions = db.relationship('ReportExecution', backref='template', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'report_type': self.report_type,
            'fields': self.fields or [],
            'filters': self.filters or {},
            'sorting': self.sorting or {},
            'grouping': self.grouping or {},
            'formatting': self.formatting or {},
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'use_count': self.use_count,
            'is_public': self.is_public,
            'allowed_users': self.allowed_users or [],
            'allowed_roles': self.allowed_roles or [],
            'is_active': self.is_active,
            'auto_refresh': self.auto_refresh
        }
    
    def can_access(self, username, user_roles=None):
        """Check if a user can access this report template"""
        if not self.is_active:
            return False
        
        # Creator can always access
        if self.created_by == username:
            return True
        
        # Public reports can be accessed by anyone
        if self.is_public:
            return True
        
        # Check if user is in allowed users list
        if self.allowed_users and username in self.allowed_users:
            return True
        
        # Check if user has required roles
        if self.allowed_roles and user_roles:
            if any(role in self.allowed_roles for role in user_roles):
                return True
        
        return False
    
    def increment_usage(self):
        """Increment usage counter and update last used timestamp"""
        self.use_count = (self.use_count or 0) + 1
        self.last_used = datetime.utcnow()

class ReportExecution(db.Model):
    """Model for tracking report execution history"""
    __tablename__ = 'report_executions'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=True)
    
    # Execution details
    report_name = db.Column(db.String(200), nullable=False)
    report_type = db.Column(db.String(100), nullable=False)
    export_format = db.Column(db.String(20), nullable=False)  # 'pdf', 'csv', 'excel'
    
    # Configuration used (stored in case template changes)
    fields_used = db.Column(db.JSON)
    filters_used = db.Column(db.JSON)
    sorting_used = db.Column(db.JSON)
    
    # Results
    total_records = db.Column(db.Integer)
    filtered_records = db.Column(db.Integer)
    file_size = db.Column(db.Integer)  # in bytes
    file_path = db.Column(db.String(500))  # relative path to generated file
    
    # Execution metadata
    executed_by = db.Column(db.String(100), nullable=False)
    executed_at = db.Column(db.DateTime, default=datetime.utcnow)
    execution_time = db.Column(db.Float)  # time in seconds
    
    # Status
    status = db.Column(db.String(50), default='completed')  # 'pending', 'running', 'completed', 'failed'
    error_message = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'template_id': self.template_id,
            'report_name': self.report_name,
            'report_type': self.report_type,
            'export_format': self.export_format,
            'fields_used': self.fields_used or [],
            'filters_used': self.filters_used or {},
            'sorting_used': self.sorting_used or {},
            'total_records': self.total_records,
            'filtered_records': self.filtered_records,
            'file_size': self.file_size,
            'file_path': self.file_path,
            'executed_by': self.executed_by,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'execution_time': self.execution_time,
            'status': self.status,
            'error_message': self.error_message
        }

class ReportField(db.Model):
    """Model for defining available fields for different report types"""
    __tablename__ = 'report_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(100), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)
    field_type = db.Column(db.String(50), nullable=False)  # 'string', 'number', 'date', 'boolean', 'json'
    
    # Field configuration
    is_filterable = db.Column(db.Boolean, default=True)
    is_sortable = db.Column(db.Boolean, default=True)
    is_groupable = db.Column(db.Boolean, default=False)
    is_aggregatable = db.Column(db.Boolean, default=False)  # For numeric fields
    
    # Display configuration
    default_width = db.Column(db.Integer, default=100)  # for CSV/Excel column width
    format_pattern = db.Column(db.String(100))  # for dates, numbers, etc.
    category = db.Column(db.String(100))  # Group related fields
    
    # Database configuration
    table_name = db.Column(db.String(100))  # Source table
    column_name = db.Column(db.String(100))  # Source column
    join_path = db.Column(db.JSON)  # For related tables
    
    # Metadata
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.UniqueConstraint('report_type', 'field_name', name='unique_field_per_report_type'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'report_type': self.report_type,
            'field_name': self.field_name,
            'display_name': self.display_name,
            'field_type': self.field_type,
            'is_filterable': self.is_filterable,
            'is_sortable': self.is_sortable,
            'is_groupable': self.is_groupable,
            'is_aggregatable': self.is_aggregatable,
            'category': self.category,
            'description': self.description
        }

# ========================= ACADEMIC SYSTEM MODELS =========================

class Shiur(db.Model):
    """Academic classes/shiurim management"""
    __tablename__ = 'shiurim'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Rabbi Shaya Cohen", "Rabbi Yehuda Cohen", etc.
    display_name = db.Column(db.String(150))  # Optional display name for UI
    description = db.Column(db.Text)  # Description of the shiur
    
    # Instructor information
    instructor_name = db.Column(db.String(100), nullable=False)
    instructor_title = db.Column(db.String(50))  # "Rabbi", "Rebbe", etc.
    instructor_email = db.Column(db.String(120))
    instructor_phone = db.Column(db.String(20))
    
    # Shiur details
    subject = db.Column(db.String(100))  # "Gemara", "Halacha", "Mussar", etc.
    level = db.Column(db.String(50))  # "Beginner", "Intermediate", "Advanced"
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    
    # Schedule information
    schedule_days = db.Column(db.JSON)  # ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    schedule_times = db.Column(db.JSON)  # [{"start": "09:00", "end": "10:30"}, ...]
    location = db.Column(db.String(100))  # "Beis Medrash", "Room 201", etc.
    
    # Academic year association
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Attendance tracking settings
    requires_attendance = db.Column(db.Boolean, default=True)
    attendance_threshold = db.Column(db.Float, default=0.80)  # 80% minimum attendance
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    max_students = db.Column(db.Integer, default=25)  # Maximum enrollment
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    academic_year = db.relationship('AcademicYear', backref='shiurim')
    student_assignments = db.relationship('StudentShiurAssignment', backref='shiur', lazy='dynamic', cascade='all, delete-orphan')
    attendance_records = db.relationship('Attendance', backref='shiur', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Shiur {self.name} - {self.instructor_name}>'
    
    @property
    def full_name(self):
        """Return full shiur name with instructor"""
        return f"{self.name} ({self.instructor_name})"
    
    @property
    def current_enrollment(self):
        """Get current number of enrolled students"""
        return self.student_assignments.filter_by(is_active=True).count()
    
    @property
    def available_spots(self):
        """Get number of available spots"""
        return max(0, self.max_students - self.current_enrollment)
    
    @property
    def is_full(self):
        """Check if shiur is at capacity"""
        return self.current_enrollment >= self.max_students
    
    @property
    def schedule_display(self):
        """Format schedule for display"""
        if not self.schedule_days or not self.schedule_times:
            return "Schedule not set"
        
        days = ", ".join(self.schedule_days)
        if self.schedule_times and len(self.schedule_times) > 0:
            time_info = self.schedule_times[0]
            time_str = f"{time_info.get('start', '')} - {time_info.get('end', '')}"
            return f"{days} {time_str}"
        return days
    
    def get_enrolled_students(self):
        """Get all currently enrolled students"""
        return [assignment.student for assignment in 
                self.student_assignments.filter_by(is_active=True).all()]
    
    def get_attendance_statistics(self, start_date=None, end_date=None):
        """Get attendance statistics for this shiur"""
        query = self.attendance_records
        
        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)
        
        total_records = query.count()
        present_records = query.filter(Attendance.status.in_(['present', 'late'])).count()
        
        attendance_rate = (present_records / total_records * 100) if total_records > 0 else 0
        
        return {
            'total_sessions': total_records,
            'present_count': present_records,
            'attendance_rate': round(attendance_rate, 2)
        }
    
    @classmethod
    def create_default_shiurim(cls, academic_year_id):
        """Create default shiurim for an academic year"""
        default_shiurim = [
            {
                'name': 'Rabbi Shaya Cohen Shiur',
                'instructor_name': 'Rabbi Shaya Cohen',
                'instructor_title': 'Rabbi',
                'subject': 'Gemara',
                'level': 'Advanced',
                'division': 'YZA',
                'schedule_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                'schedule_times': [{'start': '09:00', 'end': '10:30'}],
                'location': 'Main Beis Medrash'
            },
            {
                'name': 'Rabbi Yehuda Cohen Shiur',
                'instructor_name': 'Rabbi Yehuda Cohen',
                'instructor_title': 'Rabbi',
                'subject': 'Gemara',
                'level': 'Intermediate',
                'division': 'YZA',
                'schedule_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                'schedule_times': [{'start': '11:00', 'end': '12:30'}],
                'location': 'Main Beis Medrash'
            },
            {
                'name': 'Rabbi Schuler Shiur',
                'instructor_name': 'Rabbi Schuler',
                'instructor_title': 'Rabbi',
                'subject': 'Gemara',
                'level': 'Beginner',
                'division': 'YZA',
                'schedule_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                'schedule_times': [{'start': '14:00', 'end': '15:30'}],
                'location': 'Room 201'
            },
            {
                'name': 'Bais Medrash Learning',
                'instructor_name': 'Self-Directed',
                'instructor_title': '',
                'subject': 'Independent Study',
                'level': 'All Levels',
                'division': 'YZA',
                'schedule_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                'schedule_times': [{'start': '16:00', 'end': '18:00'}],
                'location': 'Bais Medrash'
            },
            {
                'name': 'Kollel Shiur',
                'instructor_name': 'Kollel Rosh',
                'instructor_title': 'Rabbi',
                'subject': 'Advanced Gemara',
                'level': 'Kollel Level',
                'division': 'KOLLEL',
                'schedule_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                'schedule_times': [{'start': '10:00', 'end': '12:00'}],
                'location': 'Kollel Beis Medrash'
            }
        ]
        
        created_shiurim = []
        for shiur_data in default_shiurim:
            # Check if shiur already exists
            existing = cls.query.filter_by(
                name=shiur_data['name'],
                academic_year_id=academic_year_id
            ).first()
            
            if not existing:
                shiur = cls(academic_year_id=academic_year_id, **shiur_data)
                db.session.add(shiur)
                created_shiurim.append(shiur)
        
        db.session.commit()
        return created_shiurim

class AttendancePeriod(db.Model):
    """Configurable time periods for attendance tracking"""
    __tablename__ = 'attendance_periods'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Morning Seder", "Afternoon Seder", "Evening Seder"
    display_name = db.Column(db.String(150))  # Optional display name
    description = db.Column(db.Text)
    
    # Time period details
    start_time = db.Column(db.Time, nullable=False)  # 09:00
    end_time = db.Column(db.Time, nullable=False)    # 12:00
    grace_period_minutes = db.Column(db.Integer, default=10)  # Late arrival grace period
    
    # Applicable days
    applicable_days = db.Column(db.JSON)  # ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
    
    # Division and year association
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Settings
    is_mandatory = db.Column(db.Boolean, default=True)
    weight = db.Column(db.Float, default=1.0)  # Weight for attendance calculations
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    academic_year = db.relationship('AcademicYear', backref='attendance_periods')
    attendance_records = db.relationship('Attendance', backref='attendance_period', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AttendancePeriod {self.name} - {self.division}>'
    
    @property
    def time_display(self):
        """Format time period for display"""
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
    
    @property
    def days_display(self):
        """Format applicable days for display"""
        if not self.applicable_days:
            return "No days set"
        return ", ".join(self.applicable_days)
    
    def is_applicable_today(self):
        """Check if this period applies to today"""
        today = datetime.now().strftime('%A')  # Monday, Tuesday, etc.
        return self.applicable_days and today in self.applicable_days
    
    def is_currently_active(self):
        """Check if we're currently in this time period"""
        if not self.is_applicable_today():
            return False
        
        now = datetime.now().time()
        return self.start_time <= now <= self.end_time
    
    @classmethod
    def create_default_periods(cls, academic_year_id, division='YZA'):
        """Create default attendance periods for a division"""
        default_periods = {
            'YZA': [
                {
                    'name': 'Morning Seder',
                    'start_time': '09:00',
                    'end_time': '12:00',
                    'applicable_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                    'is_mandatory': True,
                    'weight': 1.0
                },
                {
                    'name': 'Afternoon Seder',
                    'start_time': '14:00',
                    'end_time': '17:00',
                    'applicable_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                    'is_mandatory': True,
                    'weight': 1.0
                },
                {
                    'name': 'Evening Seder',
                    'start_time': '20:00',
                    'end_time': '22:00',
                    'applicable_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                    'is_mandatory': False,
                    'weight': 0.5
                }
            ],
            'KOLLEL': [
                {
                    'name': 'Morning Kollel',
                    'start_time': '08:30',
                    'end_time': '12:30',
                    'applicable_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                    'is_mandatory': True,
                    'weight': 1.0
                },
                {
                    'name': 'Afternoon Kollel',
                    'start_time': '15:00',
                    'end_time': '18:00',
                    'applicable_days': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
                    'is_mandatory': True,
                    'weight': 1.0
                }
            ]
        }
        
        periods_data = default_periods.get(division, default_periods['YZA'])
        created_periods = []
        
        for period_data in periods_data:
            # Convert time strings to time objects
            start_time = datetime.strptime(period_data['start_time'], '%H:%M').time()
            end_time = datetime.strptime(period_data['end_time'], '%H:%M').time()
            
            # Check if period already exists
            existing = cls.query.filter_by(
                name=period_data['name'],
                division=division,
                academic_year_id=academic_year_id
            ).first()
            
            if not existing:
                period = cls(
                    name=period_data['name'],
                    start_time=start_time,
                    end_time=end_time,
                    applicable_days=period_data['applicable_days'],
                    is_mandatory=period_data['is_mandatory'],
                    weight=period_data['weight'],
                    division=division,
                    academic_year_id=academic_year_id
                )
                db.session.add(period)
                created_periods.append(period)
        
        db.session.commit()
        return created_periods

class Attendance(db.Model):
    """Individual attendance records for students"""
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    shiur_id = db.Column(db.Integer, db.ForeignKey('shiurim.id'), nullable=True)  # Optional shiur association
    attendance_period_id = db.Column(db.Integer, db.ForeignKey('attendance_periods.id'), nullable=False)
    
    # Attendance details
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'present', 'absent', 'late', 'excused', 'sick'
    arrival_time = db.Column(db.Time)  # Actual arrival time
    departure_time = db.Column(db.Time)  # Actual departure time
    
    # Additional information
    notes = db.Column(db.Text)  # Additional notes about attendance
    excuse_reason = db.Column(db.String(200))  # Reason for absence/lateness
    is_makeup_required = db.Column(db.Boolean, default=False)  # Whether makeup session is required
    makeup_completed = db.Column(db.Boolean, default=False)  # Whether makeup was completed
    
    # Recording information
    recorded_by = db.Column(db.String(100))  # Who recorded this attendance
    recording_method = db.Column(db.String(50), default='manual')  # 'manual', 'automatic', 'imported'
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='attendance_records')
    
    # Unique constraint to prevent duplicate records
    __table_args__ = (
        db.UniqueConstraint('student_id', 'attendance_period_id', 'date', name='unique_student_period_date'),
    )
    
    def __repr__(self):
        return f'<Attendance {self.student.student_name if self.student else "Unknown"} - {self.date} - {self.status}>'
    
    @property
    def status_color(self):
        """Return Bootstrap color class for attendance status"""
        status_colors = {
            'present': 'success',
            'late': 'warning',
            'absent': 'danger',
            'excused': 'info',
            'sick': 'secondary'
        }
        return status_colors.get(self.status, 'secondary')
    
    @property
    def status_icon(self):
        """Return icon class for attendance status"""
        status_icons = {
            'present': 'fas fa-check-circle',
            'late': 'fas fa-clock',
            'absent': 'fas fa-times-circle',
            'excused': 'fas fa-info-circle',
            'sick': 'fas fa-hospital'
        }
        return status_icons.get(self.status, 'fas fa-question-circle')
    
    @property
    def is_late(self):
        """Check if student was late based on arrival time"""
        if not self.arrival_time or not self.attendance_period:
            return False
        
        grace_period = timedelta(minutes=self.attendance_period.grace_period_minutes)
        allowed_time = (datetime.combine(self.date, self.attendance_period.start_time) + grace_period).time()
        
        return self.arrival_time > allowed_time
    
    def calculate_attendance_weight(self):
        """Calculate weighted attendance value"""
        if self.status in ['present']:
            return self.attendance_period.weight
        elif self.status in ['late']:
            return self.attendance_period.weight * 0.5  # Half weight for late
        else:
            return 0  # No weight for absent/excused/sick
    
    @classmethod
    def get_student_attendance_summary(cls, student_id, start_date=None, end_date=None, academic_year_id=None):
        """Get attendance summary for a student"""
        query = cls.query.filter_by(student_id=student_id)
        
        if start_date:
            query = query.filter(cls.date >= start_date)
        if end_date:
            query = query.filter(cls.date <= end_date)
        if academic_year_id:
            query = query.join(AttendancePeriod).filter(AttendancePeriod.academic_year_id == academic_year_id)
        
        records = query.all()
        
        total_sessions = len(records)
        present_count = len([r for r in records if r.status == 'present'])
        late_count = len([r for r in records if r.status == 'late'])
        absent_count = len([r for r in records if r.status == 'absent'])
        excused_count = len([r for r in records if r.status in ['excused', 'sick']])
        
        # Calculate weighted attendance
        total_weight = sum(r.attendance_period.weight for r in records)
        earned_weight = sum(r.calculate_attendance_weight() for r in records)
        weighted_percentage = (earned_weight / total_weight * 100) if total_weight > 0 else 0
        
        # Simple attendance percentage
        simple_percentage = (present_count / total_sessions * 100) if total_sessions > 0 else 0
        
        return {
            'total_sessions': total_sessions,
            'present_count': present_count,
            'late_count': late_count,
            'absent_count': absent_count,
            'excused_count': excused_count,
            'simple_percentage': round(simple_percentage, 2),
            'weighted_percentage': round(weighted_percentage, 2),
            'records': records
        }

class MatriculationLevel(db.Model):
    """Matriculation levels with associated instructors"""
    __tablename__ = 'matriculation_levels'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Level 1", "Beginner", "Advanced", etc.
    display_name = db.Column(db.String(150))  # Optional display name
    description = db.Column(db.Text)  # Description of the level
    
    # Level hierarchy
    level_order = db.Column(db.Integer, default=1)  # 1 = lowest, higher numbers = higher levels
    prerequisites = db.Column(db.JSON)  # List of prerequisite level IDs
    
    # Instructor information
    instructor_name = db.Column(db.String(100), nullable=False)
    instructor_title = db.Column(db.String(50))  # "Rabbi", "Dr.", "Professor", etc.
    instructor_email = db.Column(db.String(120))
    instructor_phone = db.Column(db.String(20))
    instructor_bio = db.Column(db.Text)  # Brief biography/qualifications
    
    # Level details
    subject_areas = db.Column(db.JSON)  # ["Gemara", "Halacha", "Hashkafa"]
    duration_weeks = db.Column(db.Integer)  # Expected duration to complete level
    credit_hours = db.Column(db.Integer)  # Academic credit hours for this level
    
    # Requirements
    attendance_requirement = db.Column(db.Float, default=0.80)  # 80% minimum attendance
    assignment_requirements = db.Column(db.JSON)  # List of required assignments/tests
    final_assessment_required = db.Column(db.Boolean, default=True)
    
    # Division and year association
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Administrative settings
    is_active = db.Column(db.Boolean, default=True)
    max_students = db.Column(db.Integer, default=15)  # Maximum students per level
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    academic_year = db.relationship('AcademicYear', backref='matriculation_levels')
    student_assignments = db.relationship('StudentMatriculationAssignment', backref='matriculation_level', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<MatriculationLevel {self.name} - {self.instructor_name}>'
    
    @property
    def full_name(self):
        """Return full level name with instructor"""
        return f"{self.name} ({self.instructor_name})"
    
    @property
    def current_enrollment(self):
        """Get current number of enrolled students"""
        return self.student_assignments.filter_by(is_active=True).count()
    
    @property
    def available_spots(self):
        """Get number of available spots"""
        return max(0, self.max_students - self.current_enrollment)
    
    @property
    def is_full(self):
        """Check if level is at capacity"""
        return self.current_enrollment >= self.max_students
    
    def get_enrolled_students(self):
        """Get all currently enrolled students"""
        return [assignment.student for assignment in 
                self.student_assignments.filter_by(is_active=True).all()]
    
    def get_completed_students(self):
        """Get students who completed this level"""
        return [assignment.student for assignment in 
                self.student_assignments.filter_by(status='completed').all()]
    
    @classmethod
    def create_default_levels(cls, academic_year_id, division='YZA'):
        """Create default matriculation levels for a division"""
        default_levels = {
            'YZA': [
                {
                    'name': 'Foundation Level',
                    'level_order': 1,
                    'instructor_name': 'Rabbi Goldstein',
                    'instructor_title': 'Rabbi',
                    'subject_areas': ['Basic Gemara', 'Hebrew Reading'],
                    'duration_weeks': 16,
                    'credit_hours': 6,
                    'attendance_requirement': 0.85,
                    'description': 'Foundational level for new students'
                },
                {
                    'name': 'Intermediate Level',
                    'level_order': 2,
                    'instructor_name': 'Rabbi Silver',
                    'instructor_title': 'Rabbi',
                    'subject_areas': ['Intermediate Gemara', 'Rashi'],
                    'duration_weeks': 20,
                    'credit_hours': 8,
                    'attendance_requirement': 0.80,
                    'description': 'Intermediate level with focus on Rashi'
                },
                {
                    'name': 'Advanced Level',
                    'level_order': 3,
                    'instructor_name': 'Rabbi Cohen',
                    'instructor_title': 'Rabbi',
                    'subject_areas': ['Advanced Gemara', 'Tosafos', 'Halacha'],
                    'duration_weeks': 24,
                    'credit_hours': 12,
                    'attendance_requirement': 0.80,
                    'description': 'Advanced level with Tosafos and practical Halacha'
                }
            ],
            'KOLLEL': [
                {
                    'name': 'Kollel Foundation',
                    'level_order': 1,
                    'instructor_name': 'Kollel Rosh',
                    'instructor_title': 'Rabbi',
                    'subject_areas': ['Independent Learning', 'Research Methods'],
                    'duration_weeks': 12,
                    'credit_hours': 4,
                    'attendance_requirement': 0.75,
                    'description': 'Foundation for independent Kollel learning'
                },
                {
                    'name': 'Advanced Kollel',
                    'level_order': 2,
                    'instructor_name': 'Senior Kollel Member',
                    'instructor_title': 'Rabbi',
                    'subject_areas': ['Advanced Independent Study', 'Teaching Skills'],
                    'duration_weeks': 20,
                    'credit_hours': 8,
                    'attendance_requirement': 0.75,
                    'description': 'Advanced level with teaching preparation'
                }
            ]
        }
        
        levels_data = default_levels.get(division, default_levels['YZA'])
        created_levels = []
        
        for level_data in levels_data:
            # Check if level already exists
            existing = cls.query.filter_by(
                name=level_data['name'],
                division=division,
                academic_year_id=academic_year_id
            ).first()
            
            if not existing:
                level = cls(
                    division=division,
                    academic_year_id=academic_year_id,
                    **level_data
                )
                db.session.add(level)
                created_levels.append(level)
        
        db.session.commit()
        return created_levels

class StudentShiurAssignment(db.Model):
    """Assignment of students to shiurim"""
    __tablename__ = 'student_shiur_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    shiur_id = db.Column(db.Integer, db.ForeignKey('shiurim.id'), nullable=False)
    
    # Assignment period
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)  # NULL for active assignments
    is_active = db.Column(db.Boolean, default=True)
    
    # Assignment management
    assigned_by = db.Column(db.String(100))  # Username who made the assignment
    assignment_reason = db.Column(db.String(200))  # Reason for assignment
    ended_by = db.Column(db.String(100))  # Username who ended the assignment
    end_reason = db.Column(db.String(200))  # Reason for ending assignment
    
    # Academic performance in this shiur
    current_grade = db.Column(db.String(5))  # A, B, C, D, F
    participation_score = db.Column(db.Integer)  # 1-100
    attendance_percentage = db.Column(db.Float)  # Calculated attendance for this shiur
    
    # Additional information
    notes = db.Column(db.Text)
    priority = db.Column(db.Integer, default=1)  # For handling conflicts
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='shiur_assignments')
    
    # Unique constraint for active assignments
    __table_args__ = (
        db.Index('idx_student_active_shiur', 'student_id', 'is_active'),
    )
    
    def __repr__(self):
        return f'<StudentShiurAssignment {self.student.student_name if self.student else "Unknown"} - {self.shiur.name if self.shiur else "Unknown"}>'
    
    @property
    def duration_days(self):
        """Calculate assignment duration"""
        end_date = self.end_date or datetime.now().date()
        return (end_date - self.start_date).days
    
    @property
    def status_display(self):
        """Get status for display"""
        if self.is_active:
            return 'Active'
        else:
            return 'Ended'
    
    @property
    def grade_color(self):
        """Return color class for grade"""
        grade_colors = {
            'A': 'success',
            'B': 'info',
            'C': 'warning',
            'D': 'orange',
            'F': 'danger'
        }
        return grade_colors.get(self.current_grade, 'secondary')
    
    def calculate_attendance_percentage(self):
        """Calculate attendance percentage for this shiur assignment"""
        from models import Attendance
        
        # Get attendance records for this student and shiur during assignment period
        query = Attendance.query.filter_by(
            student_id=self.student_id,
            shiur_id=self.shiur_id
        ).filter(
            Attendance.date >= self.start_date
        )
        
        if self.end_date:
            query = query.filter(Attendance.date <= self.end_date)
        
        records = query.all()
        
        if not records:
            return 0.0
        
        present_count = len([r for r in records if r.status in ['present', 'late']])
        total_count = len(records)
        
        self.attendance_percentage = (present_count / total_count * 100) if total_count > 0 else 0
        return self.attendance_percentage
    
    @classmethod
    def get_current_assignment_for_student(cls, student_id):
        """Get current shiur assignment for a student"""
        return cls.query.filter_by(student_id=student_id, is_active=True).first()

class StudentMatriculationAssignment(db.Model):
    """Assignment of students to matriculation levels"""
    __tablename__ = 'student_matriculation_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    matriculation_level_id = db.Column(db.Integer, db.ForeignKey('matriculation_levels.id'), nullable=False)
    
    # Assignment period
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)  # NULL for active assignments
    is_active = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default='in_progress')  # 'in_progress', 'completed', 'dropped', 'failed'
    
    # Assignment management
    assigned_by = db.Column(db.String(100))  # Username who made the assignment
    assignment_reason = db.Column(db.String(200))  # Reason for assignment
    ended_by = db.Column(db.String(100))  # Username who ended the assignment
    end_reason = db.Column(db.String(200))  # Reason for ending assignment
    
    # Academic progress
    completion_percentage = db.Column(db.Float, default=0.0)  # 0-100%
    current_grade = db.Column(db.String(5))  # A, B, C, D, F
    final_grade = db.Column(db.String(5))  # Final grade upon completion
    credit_hours_earned = db.Column(db.Integer, default=0)
    
    # Assessment results
    assignments_completed = db.Column(db.JSON)  # List of completed assignments
    final_assessment_score = db.Column(db.Float)  # Final assessment score
    final_assessment_date = db.Column(db.Date)  # Date of final assessment
    
    # Attendance tracking
    attendance_percentage = db.Column(db.Float)  # Calculated attendance for this level
    meets_attendance_requirement = db.Column(db.Boolean, default=False)
    
    # Additional information
    notes = db.Column(db.Text)
    instructor_feedback = db.Column(db.Text)  # Feedback from instructor
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completion_date = db.Column(db.DateTime)  # When level was completed
    
    # Relationships
    student = db.relationship('Student', backref='matriculation_assignments')
    
    def __repr__(self):
        return f'<StudentMatriculationAssignment {self.student.student_name if self.student else "Unknown"} - {self.matriculation_level.name if self.matriculation_level else "Unknown"}>'
    
    @property
    def status_color(self):
        """Return color class for status"""
        status_colors = {
            'in_progress': 'info',
            'completed': 'success',
            'dropped': 'warning',
            'failed': 'danger'
        }
        return status_colors.get(self.status, 'secondary')
    
    @property
    def grade_color(self):
        """Return color class for grade"""
        grade_colors = {
            'A': 'success',
            'B': 'info',
            'C': 'warning',
            'D': 'orange',
            'F': 'danger'
        }
        return grade_colors.get(self.current_grade or self.final_grade, 'secondary')
    
    @property
    def duration_weeks(self):
        """Calculate assignment duration in weeks"""
        end_date = self.end_date or datetime.now().date()
        days = (end_date - self.start_date).days
        return round(days / 7, 1)
    
    def check_completion_requirements(self):
        """Check if student meets requirements for completion"""
        requirements_met = {
            'attendance': False,
            'assignments': False,
            'final_assessment': False
        }
        
        # Check attendance requirement
        if self.attendance_percentage and self.matriculation_level:
            requirements_met['attendance'] = self.attendance_percentage >= (self.matriculation_level.attendance_requirement * 100)
        
        # Check assignments (if required)
        if self.matriculation_level and self.matriculation_level.assignment_requirements:
            required_assignments = self.matriculation_level.assignment_requirements
            completed_assignments = self.assignments_completed or []
            requirements_met['assignments'] = len(completed_assignments) >= len(required_assignments)
        else:
            requirements_met['assignments'] = True  # No assignments required
        
        # Check final assessment
        if self.matriculation_level and self.matriculation_level.final_assessment_required:
            requirements_met['final_assessment'] = self.final_assessment_score is not None and self.final_assessment_score >= 70
        else:
            requirements_met['final_assessment'] = True  # No final assessment required
        
        # Update meets_attendance_requirement
        self.meets_attendance_requirement = requirements_met['attendance']
        
        # Determine if all requirements are met
        all_met = all(requirements_met.values())
        
        return {
            'requirements_met': requirements_met,
            'all_requirements_met': all_met,
            'can_complete': all_met
        }
    
    def mark_completed(self, completion_date=None, final_grade=None):
        """Mark this assignment as completed"""
        self.status = 'completed'
        self.is_active = False
        self.completion_date = completion_date or datetime.utcnow()
        self.end_date = self.completion_date.date()
        self.completion_percentage = 100.0
        
        if final_grade:
            self.final_grade = final_grade
        
        # Award credit hours
        if self.matriculation_level:
            self.credit_hours_earned = self.matriculation_level.credit_hours
        
        return self
    
    @classmethod
    def get_current_assignment_for_student(cls, student_id):
        """Get current matriculation assignment for a student"""
        return cls.query.filter_by(student_id=student_id, is_active=True).first()
    
    @classmethod
    def get_completed_assignments_for_student(cls, student_id):
        """Get all completed matriculation assignments for a student"""
        return cls.query.filter_by(student_id=student_id, status='completed').all()

# Add indexes for better performance
db.Index('idx_report_templates_type', ReportTemplate.report_type)
db.Index('idx_report_templates_created_by', ReportTemplate.created_by)
db.Index('idx_report_executions_executed_by', ReportExecution.executed_by)
db.Index('idx_report_executions_executed_at', ReportExecution.executed_at)

class FinancialRecord(db.Model):
    """Track financial records for each student per academic year"""
    __tablename__ = 'financial_records'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Tuition information
    tuition_amount = db.Column(db.Numeric(10, 2), nullable=False)
    tuition_type = db.Column(db.String(20))  # Full, Reduced, Scholarship
    discount_percentage = db.Column(db.Integer, default=0)
    discount_reason = db.Column(db.Text)
    final_tuition_amount = db.Column(db.Numeric(10, 2))
    
    # Financial aid
    financial_aid_requested = db.Column(db.Boolean, default=False)
    financial_aid_form_sent = db.Column(db.Boolean, default=False)
    financial_aid_form_sent_date = db.Column(db.DateTime)
    financial_aid_form_received = db.Column(db.Boolean, default=False) 
    financial_aid_form_received_date = db.Column(db.DateTime)
    financial_aid_approved_amount = db.Column(db.Numeric(10, 2))
    
    # Enrollment contract
    enrollment_contract_generated = db.Column(db.Boolean, default=False)
    enrollment_contract_sent = db.Column(db.Boolean, default=False)
    enrollment_contract_sent_date = db.Column(db.DateTime)
    enrollment_contract_received = db.Column(db.Boolean, default=False)
    enrollment_contract_received_date = db.Column(db.DateTime)
    
    # External systems
    admire_charges_setup = db.Column(db.Boolean, default=False)
    admire_charges_setup_date = db.Column(db.DateTime)
    admire_account_number = db.Column(db.String(50))
    
    # FAFSA
    fafsa_required = db.Column(db.Boolean, default=False)
    fafsa_status = db.Column(db.String(50))  # Not Started, In Progress, Submitted, Approved, Denied
    fafsa_submission_date = db.Column(db.DateTime)
    pell_grant_eligible = db.Column(db.Boolean, default=False)
    pell_grant_amount = db.Column(db.Numeric(10, 2))
    pell_grant_received_date = db.Column(db.DateTime)
    
    # Payment tracking
    payment_plan = db.Column(db.String(50))  # Full, Monthly, Quarterly, etc.
    total_paid = db.Column(db.Numeric(10, 2), default=0)
    balance_due = db.Column(db.Numeric(10, 2))
    
    # Status
    financial_status = db.Column(db.String(50))  # Pending, Active, Hold, Cleared
    notes = db.Column(db.Text)
    
    # Enhanced contract status tracking - NEW FIELDS
    enhanced_contract_generated = db.Column(db.Boolean, default=False)
    enhanced_contract_generated_date = db.Column(db.DateTime)
    enhanced_contract_pdf_path = db.Column(db.String(500))
    enhanced_contract_sent = db.Column(db.Boolean, default=False)
    enhanced_contract_sent_date = db.Column(db.DateTime)
    enhanced_contract_signed = db.Column(db.Boolean, default=False)
    enhanced_contract_signed_date = db.Column(db.DateTime)
    
    # Contract version control
    contract_generation_hash = db.Column(db.String(64))  # SHA-256 hash of tuition data when contract was generated
    contract_needs_regeneration = db.Column(db.Boolean, default=False)  # Set when tuition changes after generation
    contract_regeneration_reason = db.Column(db.String(500))  # Why regeneration is needed
    
    # Dropbox Sign integration for enhanced contracts
    enhanced_contract_dropbox_sign_id = db.Column(db.String(100))
    enhanced_contract_dropbox_sign_status = db.Column(db.String(20))  # 'pending', 'completed', 'declined', 'expired'
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    
    # Relationships
    student = db.relationship('Student', back_populates='financial_records')
    academic_year = db.relationship('AcademicYear', backref='financial_records')
    documents = db.relationship('FinancialDocument', back_populates='financial_record', cascade='all, delete-orphan')

    def calculate_balance(self):
        """Calculate current balance due"""
        self.balance_due = (self.final_tuition_amount or 0) - (self.total_paid or 0)
        return self.balance_due
    
    def get_contract_status(self):
        """Get the current contract status for UI display - checks both enhanced and legacy fields"""
        # Check enhanced fields first (new system)
        contract_signed = self.enhanced_contract_signed or self.enrollment_contract_received
        contract_sent = self.enhanced_contract_sent or self.enrollment_contract_sent  
        contract_generated = self.enhanced_contract_generated
        
        if contract_signed:
            if self.contract_needs_regeneration:
                return 'signed_outdated'  # Contract signed but tuition changed
            return 'Signed'  # Fixed: Return title case for UI consistency
        elif contract_sent:
            if self.contract_needs_regeneration:
                return 'sent_outdated'  # Contract sent but tuition changed
            return 'Sent'  # Fixed: Return title case for UI consistency
        elif contract_generated:
            if self.contract_needs_regeneration:
                return 'generated_outdated'  # Contract generated but tuition changed
            return 'Generated'  # Fixed: Return title case for UI consistency
        else:
            return 'not_generated'
    
    def generate_tuition_hash(self):
        """Generate hash of current tuition data for version control"""
        import hashlib
        import json
        
        # Create a consistent hash of tuition-related data
        tuition_data = {
            'tuition_amount': float(self.tuition_amount or 0),
            'final_tuition_amount': float(self.final_tuition_amount or 0),
            'discount_percentage': self.discount_percentage or 0,
            'financial_aid_approved_amount': float(self.financial_aid_approved_amount or 0),
            'academic_year_id': self.academic_year_id
        }
        
        # Add student tuition components if available
        from models import StudentTuitionComponent
        components = StudentTuitionComponent.query.filter_by(
            student_id=self.student_id,
            academic_year_id=self.academic_year_id
        ).all()
        
        component_data = []
        for comp in components:
            component_data.append({
                'component_id': comp.component_id,
                'amount': float(comp.amount or 0),
                'discount_amount': float(comp.discount_amount or 0),
                'is_active': comp.is_active
            })
        
        tuition_data['components'] = sorted(component_data, key=lambda x: x['component_id'])
        
        # Create hash
        data_string = json.dumps(tuition_data, sort_keys=True)
        return hashlib.sha256(data_string.encode()).hexdigest()
    
    def check_needs_regeneration(self):
        """Check if contract needs regeneration due to tuition changes"""
        if not self.enhanced_contract_generated:
            return False
        
        current_hash = self.generate_tuition_hash()
        return current_hash != self.contract_generation_hash
    
    def mark_contract_outdated(self, reason="Tuition amounts changed"):
        """Mark contract as needing regeneration"""
        self.contract_needs_regeneration = True
        self.contract_regeneration_reason = reason

    @property
    def all_documents(self):
        """Get all documents for this student/year from both manual uploads and secure uploads"""
        documents = []
        
        # Add manual uploads (FinancialDocument)
        for doc in self.documents:
            documents.append({
                'id': doc.id,
                'type': 'manual',
                'filename': doc.filename,
                'document_type': doc.document_type,
                'uploaded_at': doc.uploaded_at,
                'uploaded_by': doc.uploaded_by,
                'description': doc.description,
                'file_size': doc.file_size,
                'source': 'Manual Upload'
            })
        
        # Add secure uploads (FormUploadLog) for this student
        from models import FormUploadLog
        secure_uploads = FormUploadLog.query.filter_by(
            student_id=self.student_id,
            processing_status='processed'
        ).all()
        
        for upload in secure_uploads:
            # Try to match by academic year context if possible
            documents.append({
                'id': upload.id,
                'type': 'secure',
                'filename': upload.original_filename,
                'document_type': upload.document_category or 'other',
                'uploaded_at': upload.uploaded_at,
                'uploaded_by': 'Student/Family',
                'description': upload.document_description or 'Secure upload',
                'file_size': upload.file_size,
                'source': 'Secure Upload'
            })
        
        # Sort by upload date (newest first)
        documents.sort(key=lambda x: x['uploaded_at'], reverse=True)
        return documents

    @property
    def document_count(self):
        """Get total count of all documents (manual + secure)"""
        manual_count = len(self.documents)
        
        from models import FormUploadLog
        secure_count = FormUploadLog.query.filter_by(
            student_id=self.student_id,
            processing_status='processed'
        ).count()
        
        return manual_count + secure_count

    @property  
    def latest_contract_document(self):
        """Get the most recent contract document from either system"""
        latest_doc = None
        latest_date = None
        
        # Check manual uploads for enrollment contracts
        for doc in self.documents:
            if doc.document_type == 'enrollment_contract':
                if not latest_date or doc.uploaded_at > latest_date:
                    latest_date = doc.uploaded_at
                    latest_doc = {
                        'id': doc.id,
                        'type': 'manual',
                        'filename': doc.filename,
                        'file_path': doc.file_path,
                        'uploaded_at': doc.uploaded_at,
                        'source': 'Manual Upload'
                    }
        
        # Check secure uploads for tuition contracts
        from models import FormUploadLog, SecureFormLink
        contract_uploads = db.session.query(FormUploadLog).join(
            SecureFormLink, FormUploadLog.secure_link_id == SecureFormLink.id
        ).filter(
            FormUploadLog.student_id == self.student_id,
            SecureFormLink.form_type == 'tuition_contract',
            FormUploadLog.processing_status == 'processed'
        ).all()
        
        for upload in contract_uploads:
            if not latest_date or upload.uploaded_at > latest_date:
                latest_date = upload.uploaded_at
                latest_doc = {
                    'id': upload.id,
                    'type': 'secure',
                    'filename': upload.original_filename,
                    'file_path': upload.file_path,
                    'uploaded_at': upload.uploaded_at,
                    'source': 'Secure Upload'
                }
        
        return latest_doc

# Add relationship to Student model
Student.financial_records = db.relationship('FinancialRecord', back_populates='student', order_by='desc(FinancialRecord.academic_year_id)')

class FinancialDocument(db.Model):
    """Store financial documents securely"""
    __tablename__ = 'financial_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    financial_record_id = db.Column(db.Integer, db.ForeignKey('financial_records.id'), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # financial_aid_form, enrollment_contract, other
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)  # Encrypted path
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    
    # Security
    encrypted = db.Column(db.Boolean, default=True)
    checksum = db.Column(db.String(64))  # SHA-256 hash
    
    # Metadata
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    # Relationships
    financial_record = db.relationship('FinancialRecord', back_populates='documents')

# ... existing code ...

class FinancialAidApplication(db.Model):
    """Division-specific financial aid applications"""
    __tablename__ = 'financial_aid_applications'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    
    # Application details
    application_status = db.Column(db.String(20), default='Draft')  # 'Draft', 'Submitted', 'Under Review', 'Approved', 'Denied'
    application_type = db.Column(db.String(50))  # 'New', 'Renewal', 'Appeal'
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    submission_date = db.Column(db.DateTime)
    review_date = db.Column(db.DateTime)
    decision_date = db.Column(db.DateTime)
    
    # Financial information
    household_income = db.Column(db.Numeric(10, 2))
    household_size = db.Column(db.Integer)
    other_children_in_school = db.Column(db.Integer)
    other_tuition_payments = db.Column(db.Numeric(10, 2))
    
    # Parent employment information
    father_employer = db.Column(db.String(200))
    father_income = db.Column(db.Numeric(10, 2))
    mother_employer = db.Column(db.String(200))
    mother_income = db.Column(db.Numeric(10, 2))
    
    # Assets
    home_ownership = db.Column(db.Boolean, default=False)
    home_value = db.Column(db.Numeric(10, 2))
    mortgage_balance = db.Column(db.Numeric(10, 2))
    savings_amount = db.Column(db.Numeric(10, 2))
    investments_amount = db.Column(db.Numeric(10, 2))
    
    # Expenses
    monthly_rent = db.Column(db.Numeric(10, 2))
    monthly_mortgage = db.Column(db.Numeric(10, 2))
    monthly_utilities = db.Column(db.Numeric(10, 2))
    monthly_food = db.Column(db.Numeric(10, 2))
    monthly_medical = db.Column(db.Numeric(10, 2))
    monthly_other = db.Column(db.Numeric(10, 2))
    
    # Aid requested
    requested_aid_amount = db.Column(db.Numeric(10, 2))
    requested_aid_percentage = db.Column(db.Integer)  # Percentage of tuition
    hardship_explanation = db.Column(db.Text)
    
    # Decision
    approved_aid_amount = db.Column(db.Numeric(10, 2))
    approved_aid_percentage = db.Column(db.Integer)
    decision_notes = db.Column(db.Text)
    reviewed_by = db.Column(db.String(100))
    approved_by = db.Column(db.String(100))
    
    # Division-specific fields (stored as JSON)
    division_specific_data = db.Column(db.JSON)  # For custom fields per division
    
    # E-signature tracking
    esign_sent = db.Column(db.Boolean, default=False)
    esign_sent_date = db.Column(db.DateTime)
    esign_completed = db.Column(db.Boolean, default=False)
    esign_completed_date = db.Column(db.DateTime)
    esign_document_id = db.Column(db.String(100))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='financial_aid_applications')
    academic_year = db.relationship('AcademicYear', backref='financial_aid_applications')
    documents = db.relationship('FinancialAidDocument', backref='application', lazy='dynamic', cascade='all, delete-orphan')
    
    # Unique constraint to prevent duplicate applications for same student/year/division
    __table_args__ = (db.UniqueConstraint('student_id', 'academic_year_id', 'division', name='unique_student_year_division'),)
    
    def __repr__(self):
        return f'<FinancialAidApplication {self.student_id} - {self.division} - {self.academic_year_id}>'
    
    @property
    def status_color(self):
        """Return Bootstrap color class for status"""
        colors = {
            'Draft': 'secondary',
            'Submitted': 'info',
            'Under Review': 'warning',
            'Approved': 'success',
            'Denied': 'danger'
        }
        return colors.get(self.application_status, 'secondary')
    
    @property
    def total_monthly_expenses(self):
        """Calculate total monthly expenses"""
        expenses = [
            self.monthly_rent or 0,
            self.monthly_mortgage or 0,
            self.monthly_utilities or 0,
            self.monthly_food or 0,
            self.monthly_medical or 0,
            self.monthly_other or 0
        ]
        return sum(float(e) for e in expenses)


class FinancialAidDocument(db.Model):
    """Documents attached to financial aid applications"""
    __tablename__ = 'financial_aid_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('financial_aid_applications.id'), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # 'tax_return', 'pay_stub', 'bank_statement', etc.
    document_year = db.Column(db.Integer)  # For tax returns
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    
    # Security
    encrypted = db.Column(db.Boolean, default=True)
    
    # Metadata
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.String(100))
    description = db.Column(db.Text)
    
    def __repr__(self):
        return f'<FinancialAidDocument {self.document_type} - {self.filename}>'


class TuitionContract(db.Model):
    """Division-specific tuition contracts"""
    __tablename__ = 'tuition_contracts'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    
    # Contract details
    contract_type = db.Column(db.String(50))  # 'Standard', 'Financial Aid', 'Scholarship'
    contract_status = db.Column(db.String(20), default='Draft')  # 'Draft', 'Generated', 'Sent', 'Signed', 'Cancelled'
    contract_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Financial terms
    tuition_amount = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    financial_aid_amount = db.Column(db.Numeric(10, 2), default=0)
    final_tuition_amount = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Payment terms
    payment_plan = db.Column(db.String(50), default='Annual')  # 'Annual', 'Semester', 'Monthly', 'Custom'
    payment_schedule = db.Column(db.JSON)  # List of payment due dates and amounts
    first_payment_due = db.Column(db.Date)
    final_payment_due = db.Column(db.Date)
    
    # Registration fee handling
    registration_fee = db.Column(db.Numeric(10, 2), default=0)
    registration_fee_option = db.Column(db.String(20), default='upfront')  # 'upfront' or 'rolled_in'
    
    # Payment method fields
    payment_timing = db.Column(db.String(20))  # 'upfront' or 'monthly'
    payment_method = db.Column(db.String(20))  # 'credit_card', 'ach', 'third_party'
    
    # Credit card fields
    cc_number = db.Column(db.String(20))  # Encrypted/masked
    cc_exp_date = db.Column(db.String(7))  # MM/YYYY format
    cc_holder_name = db.Column(db.String(100))
    cc_cvv = db.Column(db.String(4))  # Encrypted
    cc_zip = db.Column(db.String(10))  # Billing zip code
    cc_charge_date = db.Column(db.Integer)  # Day of month to charge (1-31)
    
    # ACH/Bank fields
    ach_account_holder_name = db.Column(db.String(100))
    ach_routing_number = db.Column(db.String(9))
    ach_account_number = db.Column(db.String(20))  # Encrypted/masked
    ach_debit_date = db.Column(db.Integer)  # Day of month to debit (1-31)
    
    # Third party payer fields
    third_party_payer_name = db.Column(db.String(100))
    third_party_payer_relationship = db.Column(db.String(50))  # 'parent', 'grandparent', 'sponsor', 'other'
    third_party_payer_contact = db.Column(db.String(120))  # Email or phone
    
    # Late payment terms
    late_fee_amount = db.Column(db.Numeric(10, 2))
    late_fee_percentage = db.Column(db.Numeric(5, 2))
    grace_period_days = db.Column(db.Integer, default=10)
    
    # Contract content
    contract_template_id = db.Column(db.String(100))  # Template used for this contract
    contract_terms = db.Column(db.Text)  # Full contract terms
    special_conditions = db.Column(db.Text)  # Any special conditions or notes
    
    # Division-specific fields
    division_specific_data = db.Column(db.JSON)  # Custom fields per division
    
    # Document paths
    contract_pdf_path = db.Column(db.String(500))  # Generated contract PDF
    signed_contract_path = db.Column(db.String(500))  # Signed contract PDF
    
    # E-signature tracking (OpenSign)
    opensign_document_id = db.Column(db.String(100))
    opensign_template_id = db.Column(db.String(100))
    opensign_status = db.Column(db.String(20))  # 'pending', 'completed', 'declined', 'expired'
    opensign_sent_date = db.Column(db.DateTime)
    opensign_signed_date = db.Column(db.DateTime)
    opensign_signed_url = db.Column(db.String(500))
    opensign_certificate_url = db.Column(db.String(500))
    
    # Hybrid signing options - BOTH digital and print/upload available
    signing_method = db.Column(db.String(20), default='both_available')  # 'digital_only', 'print_only', 'both_available'
    secure_upload_token = db.Column(db.String(64))  # Link to SecureFormLink for print option
    print_upload_completed = db.Column(db.Boolean, default=False)  # Whether print version was uploaded
    print_upload_date = db.Column(db.DateTime)  # When print version was uploaded
    
    # Contract receipt tracking - which method was actually used to receive the signed contract
    receipt_method = db.Column(db.String(20))  # 'opensign', 'secure_upload', 'manual_upload', 'email', 'in_person'
    received_by_user = db.Column(db.String(100))  # Username of who processed the receipt (for manual uploads)
    receipt_notes = db.Column(db.Text)  # Notes about how the contract was received
    
    # Signatories
    parent1_name = db.Column(db.String(100))
    parent1_email = db.Column(db.String(120))
    parent1_signed = db.Column(db.Boolean, default=False)
    parent1_signed_date = db.Column(db.DateTime)
    
    parent2_name = db.Column(db.String(100))
    parent2_email = db.Column(db.String(120))
    parent2_signed = db.Column(db.Boolean, default=False)
    parent2_signed_date = db.Column(db.DateTime)
    
    # Administrative
    generated_by = db.Column(db.String(100))
    generated_date = db.Column(db.DateTime)
    sent_by = db.Column(db.String(100))
    sent_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='tuition_contracts')
    academic_year = db.relationship('AcademicYear', backref='tuition_contracts')
    
    # Unique constraint
    __table_args__ = (db.UniqueConstraint('student_id', 'academic_year_id', 'division', name='unique_student_year_division_contract'),)
    
    def __repr__(self):
        return f'<TuitionContract {self.student_id} - {self.division} - {self.academic_year_id}>'
    
    @property
    def status_color(self):
        """Return Bootstrap color class for status"""
        colors = {
            'Draft': 'secondary',
            'Generated': 'info',
            'Sent': 'warning',
            'Signed': 'success',
            'Cancelled': 'danger'
        }
        return colors.get(self.contract_status, 'secondary')
    
    @property
    def is_fully_signed(self):
        """Check if contract is completed via either digital signature OR print upload"""
        # Check digital signatures
        digital_complete = self.opensign_status == 'completed'
        
        # Check print upload completion
        print_complete = self.print_upload_completed
        
        # Contract is complete if either method is finished
        return digital_complete or print_complete
    
    @property
    def completion_method(self):
        """Return how the contract was completed"""
        if self.opensign_status == 'completed':
            return 'Digital Signature'
        elif self.print_upload_completed:
            return 'Print & Upload'
        else:
            return 'Pending'
    
    @property
    def signing_options_available(self):
        """Return available signing options"""
        if self.signing_method == 'digital_only':
            return ['Digital Signature']
        elif self.signing_method == 'print_only':
            return ['Print & Upload']
        else:  # both_available
            return ['Digital Signature', 'Print & Upload']
    
    @property
    def receipt_method_display(self):
        """Get human-readable receipt method"""
        if not self.receipt_method:
            return 'Not Yet Received'
        
        method_map = {
            'opensign': 'Digital Signature (OpenSign)',
            'secure_upload': 'Secure Upload Link',
            'manual_upload': 'Manual Admin Upload',
            'email': 'Email Attachment',
            'in_person': 'In-Person Delivery',
            'mail': 'Physical Mail'
        }
        return method_map.get(self.receipt_method, self.receipt_method.title())
    
    @property
    def receipt_status_badge(self):
        """Get bootstrap badge class for receipt status"""
        if not self.receipt_method:
            return 'bg-secondary'
        elif self.receipt_method == 'opensign':
            return 'bg-success'
        elif self.receipt_method == 'secure_upload':
            return 'bg-primary'
        elif self.receipt_method == 'manual_upload':
            return 'bg-info'
        else:
            return 'bg-warning'
    
    @property
    def days_until_first_payment(self):
        """Calculate days until first payment is due"""
        if self.first_payment_due:
            from datetime import date
            delta = self.first_payment_due - date.today()
            return delta.days
        return None
    
    def generate_payment_schedule(self):
        """Generate payment schedule based on payment plan"""
        from datetime import date, timedelta
        from dateutil.relativedelta import relativedelta
        
        schedule = []
        
        if self.payment_plan == 'Annual':
            schedule.append({
                'due_date': self.first_payment_due.isoformat() if self.first_payment_due else None,
                'amount': float(self.final_tuition_amount),
                'description': 'Annual tuition payment'
            })
        elif self.payment_plan == 'Semester':
            semester_amount = float(self.final_tuition_amount) / 2
            schedule.append({
                'due_date': self.first_payment_due.isoformat() if self.first_payment_due else None,
                'amount': semester_amount,
                'description': 'Fall semester payment'
            })
            if self.first_payment_due:
                spring_due = self.first_payment_due + relativedelta(months=5)
                schedule.append({
                    'due_date': spring_due.isoformat(),
                    'amount': semester_amount,
                    'description': 'Spring semester payment'
                })
        elif self.payment_plan == 'Monthly':
            monthly_amount = float(self.final_tuition_amount) / 10  # 10 months
            current_due = self.first_payment_due
            for month in range(10):
                if current_due:
                    schedule.append({
                        'due_date': current_due.isoformat(),
                        'amount': monthly_amount,
                        'description': f'Monthly payment {month + 1} of 10'
                    })
                    current_due = current_due + relativedelta(months=1)
        
        self.payment_schedule = schedule
        return schedule


class DivisionFinancialConfig(db.Model):
    """Configuration for division-specific financial aid and contracts"""
    __tablename__ = 'division_financial_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(10), unique=True, nullable=False)  # YZA, YOH, KOLLEL
    
    # Financial aid application configuration
    aid_application_enabled = db.Column(db.Boolean, default=True)
    aid_application_deadline = db.Column(db.Date)  # Annual deadline for applications
    aid_application_requirements = db.Column(db.JSON)  # List of required documents
    aid_application_custom_fields = db.Column(db.JSON)  # Division-specific fields
    aid_review_committee = db.Column(db.JSON)  # List of reviewer emails
    
    # Tuition contract configuration
    base_tuition_amount = db.Column(db.Numeric(10, 2))  # Standard tuition for division
    contract_template_path = db.Column(db.String(500))  # Path to contract template
    contract_terms_path = db.Column(db.String(500))  # Path to terms document
    payment_plans_available = db.Column(db.JSON)  # List of available payment plans
    late_fee_policy = db.Column(db.JSON)  # Late fee configuration
    
    # OpenSign configuration
    opensign_template_id = db.Column(db.String(100))  # Default template for contracts
    opensign_folder_id = db.Column(db.String(100))  # Folder for signed documents
    
    # Email templates
    aid_application_email_template = db.Column(db.Text)
    contract_email_template = db.Column(db.Text)
    reminder_email_template = db.Column(db.Text)
    
    # Branding
    letterhead_path = db.Column(db.String(500))
    logo_path = db.Column(db.String(500))
    primary_color = db.Column(db.String(7))  # Hex color for division
    
    # Administrative
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<DivisionFinancialConfig {self.division}>'

class SecureFormLink(db.Model):
    """Secure links for form distribution and upload"""
    __tablename__ = 'secure_form_links'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    form_type = db.Column(db.String(50), nullable=False)  # 'financial_aid_app', 'tuition_contract'
    form_id = db.Column(db.String(50))  # Reference to specific form (application_id, contract_id)
    division = db.Column(db.String(10), nullable=False)
    
    # Security settings
    expires_at = db.Column(db.DateTime, nullable=False)
    max_uses = db.Column(db.Integer, default=5)  # Allow multiple uploads for attachments
    times_used = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    allow_multiple_files = db.Column(db.Boolean, default=False)  # Enable for financial aid apps
    
    # Form details
    form_title = db.Column(db.String(200))
    form_description = db.Column(db.Text)
    pre_filled_pdf_path = db.Column(db.String(500))  # Path to generated pre-filled form
    
    # Tracking
    sent_date = db.Column(db.DateTime)
    first_accessed = db.Column(db.DateTime)
    last_accessed = db.Column(db.DateTime)
    uploaded_file_path = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime)
    uploaded_by_ip = db.Column(db.String(45))
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # 'pending', 'accessed', 'uploaded', 'processed', 'expired'
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='secure_form_links')
    
    def __repr__(self):
        return f'<SecureFormLink {self.token} - {self.form_type}>'
    
    @property
    def is_expired(self):
        """Check if link has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_usable(self):
        """Check if link can still be used"""
        return (self.is_active and 
                not self.is_expired and 
                self.times_used < self.max_uses)
    
    @property
    def upload_url(self):
        """Get the secure upload URL"""
        return f"/secure-upload/{self.token}"
    
    def increment_usage(self):
        """Increment usage counter"""
        self.times_used += 1
        self.last_accessed = datetime.utcnow()
        if not self.first_accessed:
            self.first_accessed = datetime.utcnow()
        
        if self.times_used >= self.max_uses:
            self.is_active = False
        
        db.session.commit()
    
    def mark_uploaded(self, file_path, ip_address=None):
        """Mark as uploaded with file details"""
        self.uploaded_file_path = file_path
        self.uploaded_at = datetime.utcnow()
        self.uploaded_by_ip = ip_address
        self.status = 'uploaded'
        self.is_active = False  # Deactivate after upload
        db.session.commit()
    
    @classmethod
    def generate_token(cls):
        """Generate a secure token"""
        import secrets
        return secrets.token_urlsafe(32)
    
    @classmethod
    def create_form_link(cls, student_id, form_type, form_id=None, division=None, 
                        title=None, description=None, expires_hours=72):
        """Create a new secure form link"""
        from datetime import timedelta
        
        # Get student info if division not provided
        if not division:
            student = Student.query.get(student_id)
            division = student.division if student else 'YZA'
        
        link = cls(
            token=cls.generate_token(),
            student_id=student_id,
            form_type=form_type,
            form_id=form_id,
            division=division,
            form_title=title or f"{form_type.replace('_', ' ').title()}",
            form_description=description,
            expires_at=datetime.utcnow() + timedelta(hours=expires_hours)
        )
        
        db.session.add(link)
        db.session.commit()
        return link


class FormUploadLog(db.Model):
    """Log of all form uploads for audit trail"""
    __tablename__ = 'form_upload_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    secure_link_id = db.Column(db.Integer, db.ForeignKey('secure_form_links.id'), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    
    # Upload details
    original_filename = db.Column(db.String(255))
    stored_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    file_hash = db.Column(db.String(64))  # SHA-256 hash for integrity
    
    # Processing status
    processing_status = db.Column(db.String(20), default='pending')  # 'pending', 'processed', 'failed'
    processing_notes = db.Column(db.Text)
    auto_processed = db.Column(db.Boolean, default=False)
    
    # Document categorization for financial aid attachments
    document_category = db.Column(db.String(50))  # 'main_form', 'w2', 'tax_return', 'bank_statement', 'other'
    document_description = db.Column(db.String(200))  # User-provided description
    
    # Security info
    upload_ip = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    # Admin review
    reviewed_by = db.Column(db.String(100))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    
    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    # Relationships
    secure_link = db.relationship('SecureFormLink', backref='upload_logs')
    student = db.relationship('Student', backref='form_uploads')
    
    def __repr__(self):
        return f'<FormUploadLog {self.original_filename}>'
    
    @property
    def file_size_formatted(self):
        """Get formatted file size"""
        if not self.file_size:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.1f} TB"

class TuitionComponent(db.Model):
    """Define tuition components that can be configured per division"""
    __tablename__ = 'tuition_components'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # "Registration", "Tuition", "Room", "Board", etc.
    description = db.Column(db.Text)  # Description of what this component covers
    component_type = db.Column(db.String(50), nullable=False)  # 'fee', 'tuition', 'room', 'board', 'other'
    
    # Default behavior
    is_required = db.Column(db.Boolean, default=True)  # Whether this component is required by default
    is_proration_eligible = db.Column(db.Boolean, default=False)  # Whether this can be prorated for partial years
    calculation_method = db.Column(db.String(50), default='fixed')  # 'fixed', 'per_credit', 'percentage', 'custom'
    
    # Display settings
    display_order = db.Column(db.Integer, default=0)  # Order to display components
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<TuitionComponent {self.name}>'
    
    @classmethod
    def create_default_components(cls):
        """Create default tuition components"""
        default_components = [
            {
                'name': 'Registration',
                'description': 'One-time registration fee',
                'component_type': 'fee',
                'is_required': True,
                'is_proration_eligible': False,
                'display_order': 1
            },
            {
                'name': 'Tuition',
                'description': 'Academic tuition fees',
                'component_type': 'tuition',
                'is_required': True,
                'is_proration_eligible': True,
                'display_order': 2
            },
            {
                'name': 'Room',
                'description': 'Dormitory room charges',
                'component_type': 'room',
                'is_required': False,
                'is_proration_eligible': True,
                'display_order': 3
            },
            {
                'name': 'Board',
                'description': 'Meal plan charges',
                'component_type': 'board',
                'is_required': False,
                'is_proration_eligible': True,
                'display_order': 4
            }
        ]
        
        for comp_data in default_components:
            existing = cls.query.filter_by(name=comp_data['name']).first()
            if not existing:
                component = cls(**comp_data)
                db.session.add(component)
        
        db.session.commit()

class DivisionTuitionComponent(db.Model):
    """Configure tuition components for each division with default amounts"""
    __tablename__ = 'division_tuition_components'
    
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    component_id = db.Column(db.Integer, db.ForeignKey('tuition_components.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Default amounts for this division/component/year
    default_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    minimum_amount = db.Column(db.Numeric(10, 2), default=0)  # Minimum allowed amount
    maximum_amount = db.Column(db.Numeric(10, 2))  # Maximum allowed amount (null = no limit)
    
    # Component behavior for this division
    is_enabled = db.Column(db.Boolean, default=True)  # Whether this component is used for this division
    is_required = db.Column(db.Boolean, default=True)  # Whether this component is required for this division
    is_student_editable = db.Column(db.Boolean, default=False)  # Whether students can modify this component
    
    # Administrative
    notes = db.Column(db.Text)  # Notes about this component for this division
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    component = db.relationship('TuitionComponent', backref='division_configs')
    academic_year = db.relationship('AcademicYear', backref='tuition_components')
    
    # Unique constraint
    __table_args__ = (db.UniqueConstraint('division', 'component_id', 'academic_year_id', 
                                         name='unique_division_component_year'),)
    
    def __repr__(self):
        return f'<DivisionTuitionComponent {self.division}-{self.component.name if self.component else "Unknown"}>'
    
    @classmethod
    def create_default_for_division(cls, division, academic_year_id):
        """Create default tuition components for a division"""
        # Default amounts for YZA
        yza_defaults = {
            'Registration': 550.00,
            'Tuition': 4260.00,
            'Room': 2400.00,
            'Board': 1800.00
        }
        
        # Default amounts for other divisions (can be customized)
        yoh_defaults = {
            'Registration': 500.00,
            'Tuition': 3800.00,
            'Room': 2200.00,
            'Board': 1600.00
        }
        
        kollel_defaults = {
            'Registration': 300.00,
            'Tuition': 2400.00,
            'Room': 2000.00,
            'Board': 1500.00
        }
        
        defaults_map = {
            'YZA': yza_defaults,
            'YOH': yoh_defaults,
            'KOLLEL': kollel_defaults
        }
        
        defaults = defaults_map.get(division, yza_defaults)
        
        # Get all tuition components
        components = TuitionComponent.query.filter_by(is_active=True).all()
        
        for component in components:
            # Check if already exists
            existing = cls.query.filter_by(
                division=division,
                component_id=component.id,
                academic_year_id=academic_year_id
            ).first()
            
            if not existing:
                default_amount = defaults.get(component.name, 0.00)
                
                # Special logic for different divisions
                is_required = component.is_required
                is_enabled = True
                
                # Room and Board might not be required for all divisions
                if component.name in ['Room', 'Board'] and division == 'KOLLEL':
                    is_required = False
                
                division_component = cls(
                    division=division,
                    component_id=component.id,
                    academic_year_id=academic_year_id,
                    default_amount=default_amount,
                    is_enabled=is_enabled,
                    is_required=is_required,
                    is_student_editable=False
                )
                
                db.session.add(division_component)
        
        db.session.commit()
    
    @classmethod
    def create_defaults_for_academic_year(cls, academic_year_id):
        """Create default tuition components for all divisions for a specific academic year"""
        divisions = ['YZA', 'YOH', 'KOLLEL']
        total_created = 0
        
        for division in divisions:
            # Only create if they don't already exist
            existing_count = cls.query.filter_by(
                division=division,
                academic_year_id=academic_year_id
            ).count()
            
            if existing_count == 0:
                cls.create_default_for_division(division, academic_year_id)
                # Count how many were created for this division
                new_count = cls.query.filter_by(
                    division=division,
                    academic_year_id=academic_year_id
                ).count()
                total_created += new_count
        
        return total_created

class PDFTemplate(db.Model):
    """PDF Templates that can be used across the system"""
    __tablename__ = 'pdf_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Template name
    description = db.Column(db.Text)  # Description of template usage
    category = db.Column(db.String(50), nullable=False)  # 'financial_aid', 'tuition_contract', 'acceptance_letter', etc.
    template_type = db.Column(db.String(50), nullable=False)  # 'html', 'uploaded_pdf', 'generated'
    
    # Template content or file
    content = db.Column(db.Text)  # HTML content for generated templates
    file_path = db.Column(db.String(500))  # Path for uploaded PDF templates
    
    # Template configuration
    is_active = db.Column(db.Boolean, default=True)
    is_global = db.Column(db.Boolean, default=False)  # Available to all divisions
    allowed_divisions = db.Column(db.JSON)  # List of divisions that can use this template
    
    # Version control
    version = db.Column(db.Integer, default=1)
    parent_template_id = db.Column(db.Integer, db.ForeignKey('pdf_templates.id'))  # For version history
    
    # Metadata
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.String(100))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    variables = db.relationship('PDFTemplateVariable', backref='template', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('DivisionTemplateAssignment', backref='template', lazy='dynamic')
    history = db.relationship('PDFTemplate', backref=db.backref('parent', remote_side=[id]))
    
    def __repr__(self):
        return f'<PDFTemplate {self.name} ({self.category})>'
    
    @property
    def variable_list(self):
        """Get list of all variables in this template"""
        return [{'name': var.variable_name, 'description': var.description, 'required': var.is_required} 
                for var in self.variables]
    
    def create_new_version(self, updated_by):
        """Create a new version of this template"""
        new_version = PDFTemplate(
            name=self.name,
            description=self.description,
            category=self.category,
            template_type=self.template_type,
            content=self.content,
            file_path=self.file_path,
            is_active=True,
            is_global=self.is_global,
            allowed_divisions=self.allowed_divisions,
            version=self.version + 1,
            parent_template_id=self.id,
            created_by=updated_by,
            updated_by=updated_by
        )
        # Deactivate current version
        self.is_active = False
        return new_version

class PDFTemplateVariable(db.Model):
    """Variables/placeholders available in PDF templates"""
    __tablename__ = 'pdf_template_variables'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('pdf_templates.id'), nullable=False)
    variable_name = db.Column(db.String(100), nullable=False)  # e.g., 'student_name', 'tuition_amount'
    description = db.Column(db.String(500))  # Description of what this variable represents
    default_value = db.Column(db.String(200))  # Default value if not provided
    is_required = db.Column(db.Boolean, default=True)
    variable_type = db.Column(db.String(50), default='string')  # 'string', 'number', 'date', 'boolean'
    
    # Unique constraint
    __table_args__ = (db.UniqueConstraint('template_id', 'variable_name', name='unique_template_variable'),)
    
    def __repr__(self):
        return f'<PDFTemplateVariable {self.variable_name}>'

class DivisionTemplateAssignment(db.Model):
    """Assigns templates to divisions for specific document types"""
    __tablename__ = 'division_template_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    division = db.Column(db.String(10), nullable=False)  # YZA, YOH, KOLLEL
    document_type = db.Column(db.String(50), nullable=False)  # 'financial_aid_form', 'tuition_contract', etc.
    template_id = db.Column(db.Integer, db.ForeignKey('pdf_templates.id'), nullable=False)
    
    # Override settings
    is_default = db.Column(db.Boolean, default=True)  # Is this the default template for this division/type
    custom_settings = db.Column(db.JSON)  # Any division-specific overrides
    
    # Timestamps
    assigned_by = db.Column(db.String(100))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint - only one default template per division/document type
    __table_args__ = (db.UniqueConstraint('division', 'document_type', 'is_default', name='unique_division_doc_default'),)
    
    def __repr__(self):
        return f'<DivisionTemplateAssignment {self.division} - {self.document_type}>'

class StudentTuitionComponent(db.Model):
    """Individual student's tuition component amounts (can override division defaults)"""
    __tablename__ = 'student_tuition_components'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey('tuition_components.id'), nullable=False)
    
    # Student-specific amounts
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # Actual amount for this student
    original_amount = db.Column(db.Numeric(10, 2))  # Original amount before any adjustments
    discount_amount = db.Column(db.Numeric(10, 2), default=0)  # Discount applied
    discount_percentage = db.Column(db.Numeric(5, 2), default=0)  # Discount percentage
    discount_reason = db.Column(db.String(200))  # Reason for discount
    
    # Proration settings
    is_prorated = db.Column(db.Boolean, default=False)  # Whether this component is prorated
    proration_percentage = db.Column(db.Numeric(5, 2), default=100.00)  # Proration percentage
    proration_reason = db.Column(db.String(200))  # Reason for proration (late start, early leave, etc.)
    proration_start_date = db.Column(db.Date)  # When proration period starts
    proration_end_date = db.Column(db.Date)  # When proration period ends
    
    # Component status
    is_active = db.Column(db.Boolean, default=True)  # Whether this component applies to this student
    is_override = db.Column(db.Boolean, default=False)  # Whether this overrides division default
    override_reason = db.Column(db.String(200))  # Reason for override
    
    # Payment tracking
    amount_paid = db.Column(db.Numeric(10, 2), default=0)  # Amount paid for this component
    balance_due = db.Column(db.Numeric(10, 2), default=0)  # Remaining balance for this component
    
    # Administrative
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    approved_by = db.Column(db.String(100))  # Who approved any overrides
    approved_date = db.Column(db.DateTime)  # When overrides were approved
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='tuition_components')
    academic_year = db.relationship('AcademicYear', backref='student_tuition_components')
    component = db.relationship('TuitionComponent', backref='student_assignments')
    
    # Unique constraint
    __table_args__ = (db.UniqueConstraint('student_id', 'academic_year_id', 'component_id', 
                                         name='unique_student_component_year'),)
    
    def __repr__(self):
        return f'<StudentTuitionComponent {self.student.student_name if self.student else "Unknown"}-{self.component.name if self.component else "Unknown"}>'
    
    @property
    def calculated_amount(self):
        """Calculate the final amount after discounts and proration"""
        base_amount = self.original_amount or self.amount
        
        # Apply discount
        if self.discount_percentage > 0:
            discount = base_amount * (self.discount_percentage / 100)
            base_amount -= discount
        elif self.discount_amount > 0:
            base_amount -= self.discount_amount
        
        # Apply proration
        if self.is_prorated and self.proration_percentage < 100:
            base_amount = base_amount * (self.proration_percentage / 100)
        
        return max(base_amount, 0)  # Never negative
    
    def calculate_balance(self):
        """Calculate remaining balance"""
        self.balance_due = self.calculated_amount - (self.amount_paid or 0)
        return self.balance_due
    
    @classmethod
    def create_for_student(cls, student_id, academic_year_id, division=None):
        """Create tuition components for a student based on division defaults"""
        from models import Student
        
        if not division:
            student = Student.query.get(student_id)
            division = student.division if student else 'YZA'
        
        # Get division defaults for this academic year
        division_components = DivisionTuitionComponent.query.filter_by(
            division=division,
            academic_year_id=academic_year_id,
            is_enabled=True
        ).all()
        
        for div_comp in division_components:
            # Check if already exists
            existing = cls.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id,
                component_id=div_comp.component_id
            ).first()
            
            if not existing:
                student_component = cls(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    component_id=div_comp.component_id,
                    amount=div_comp.default_amount,
                    original_amount=div_comp.default_amount,
                    proration_percentage=div_comp.proration_percentage,
                    is_active=div_comp.is_enabled
                )
                
                db.session.add(student_component)
        
        db.session.commit()

class EmailTemplate(db.Model):
    """Email templates for various communications"""
    __tablename__ = 'email_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # acceptance, enrollment_contract, financial_aid, general, reminder
    division = db.Column(db.String(20))  # YZA, YOH, KOLLEL, or null for global
    is_active = db.Column(db.Boolean, default=True)
    
    # Email content
    subject_template = db.Column(db.String(500), nullable=False)
    body_template = db.Column(db.Text, nullable=False)
    body_format = db.Column(db.String(20), default='html')  # html or plain
    
    # Configuration
    include_pdf_attachment = db.Column(db.Boolean, default=False)
    pdf_template_id = db.Column(db.Integer, db.ForeignKey('pdf_templates.id'))
    cc_addresses = db.Column(db.String(500))  # Comma-separated email addresses
    bcc_addresses = db.Column(db.String(500))
    reply_to_address = db.Column(db.String(200))
    
    # Metadata
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    version = db.Column(db.Integer, default=1)
    
    # Relations
    pdf_template = db.relationship('PDFTemplate', backref='email_templates')
    variables = db.relationship('EmailTemplateVariable', back_populates='template', cascade='all, delete-orphan')
    history = db.relationship('EmailTemplateHistory', back_populates='template', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<EmailTemplate {self.name}>'
    
    def get_variables(self):
        """Get all variables used in this template"""
        import re
        pattern = r'\{\{(\w+)\}\}'
        subject_vars = re.findall(pattern, self.subject_template or '')
        body_vars = re.findall(pattern, self.body_template or '')
        return list(set(subject_vars + body_vars))
    
    def render(self, context):
        """Render the template with given context"""
        try:
            subject = self.subject_template
            body = self.body_template
            
            for key, value in context.items():
                subject = subject.replace(f'{{{{{key}}}}}', str(value))
                body = body.replace(f'{{{{{key}}}}}', str(value))
            
            return {
                'subject': subject,
                'body': body,
                'format': self.body_format
            }
        except Exception as e:
            raise ValueError(f"Error rendering template: {str(e)}")

class EmailTemplateVariable(db.Model):
    """Variables available in email templates"""
    __tablename__ = 'email_template_variables'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('email_templates.id'), nullable=False)
    variable_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    sample_value = db.Column(db.String(200))
    
    # Relations
    template = db.relationship('EmailTemplate', back_populates='variables')
    
    def __repr__(self):
        return f'<EmailTemplateVariable {self.variable_name}>'

class EmailTemplateHistory(db.Model):
    """Version history for email templates"""
    __tablename__ = 'email_template_history'
    
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('email_templates.id'), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    
    # Template content at this version
    subject_template = db.Column(db.String(500), nullable=False)
    body_template = db.Column(db.Text, nullable=False)
    
    # Change metadata
    changed_by = db.Column(db.String(100), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    change_description = db.Column(db.String(500))
    
    # Relations
    template = db.relationship('EmailTemplate', back_populates='history')
    
    def __repr__(self):
        return f'<EmailTemplateHistory Template:{self.template_id} Version:{self.version}>'

class StudentYearlyTracking(db.Model):
    """Track student's yearly dorm and meal program status"""
    __tablename__ = 'student_yearly_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    
    # Program participation status
    dorm_program_status = db.Column(db.Boolean, default=False)  # Whether student was in dorm program
    meal_program_status = db.Column(db.Boolean, default=False)  # Whether student was in meal program
    
    # Tuition information for this year
    total_tuition_charged = db.Column(db.Numeric(10, 2))  # Total tuition for this year
    tuition_components_summary = db.Column(db.JSON)  # Summary of components for this year
    
    # Status information
    enrollment_status = db.Column(db.String(20), default='Enrolled')  # 'Enrolled', 'Withdrawn', 'Graduated'
    withdrawal_date = db.Column(db.Date)  # If student withdrew during the year
    withdrawal_reason = db.Column(db.String(200))  # Reason for withdrawal
    
    # Financial aid information for this year
    financial_aid_received = db.Column(db.Numeric(10, 2), default=0)
    scholarship_amount = db.Column(db.Numeric(10, 2), default=0)
    fafsa_amount = db.Column(db.Numeric(10, 2), default=0)
    
    # Additional tracking data
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref='yearly_tracking')
    academic_year = db.relationship('AcademicYear', backref='student_tracking')
    
    # Unique constraint - one record per student per year
    __table_args__ = (db.UniqueConstraint('student_id', 'academic_year_id', 
                                         name='unique_student_year_tracking'),)
    
    def __repr__(self):
        return f'<StudentYearlyTracking {self.student.student_name if self.student else "Unknown"}-{self.academic_year.year_label if self.academic_year else "Unknown"}>'
    
    @classmethod
    def create_or_update_for_student(cls, student_id, academic_year_id, **kwargs):
        """Create or update tracking record for a student"""
        tracking = cls.query.filter_by(
            student_id=student_id,
            academic_year_id=academic_year_id
        ).first()
        
        if not tracking:
            tracking = cls(
                student_id=student_id,
                academic_year_id=academic_year_id
            )
            db.session.add(tracking)
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(tracking, key):
                setattr(tracking, key, value)
        
        tracking.updated_at = datetime.utcnow()
        return tracking
    
    @property
    def program_summary(self):
        """Get a summary of programs student participated in"""
        programs = []
        if self.dorm_program_status:
            programs.append('Dormitory')
        if self.meal_program_status:
            programs.append('Meals')
        return ', '.join(programs) if programs else 'None'
    
    def get_component_summary(self):
        """Get human-readable summary of tuition components"""
        if not self.tuition_components_summary:
            return 'No components data'
        
        summary = []
        for comp in self.tuition_components_summary:
            if comp.get('is_active', False):
                amount = comp.get('final_amount', 0)
                summary.append(f"{comp.get('name', 'Unknown')}: ${amount:.2f}")
        
        return '; '.join(summary) if summary else 'No active components'

# Enhanced contract status tracking - NEW FIELDS
    enhanced_contract_generated = db.Column(db.Boolean, default=False)
    enhanced_contract_generated_date = db.Column(db.DateTime)
    enhanced_contract_pdf_path = db.Column(db.String(500))
    enhanced_contract_sent = db.Column(db.Boolean, default=False)
    enhanced_contract_sent_date = db.Column(db.DateTime)
    enhanced_contract_signed = db.Column(db.Boolean, default=False)
    enhanced_contract_signed_date = db.Column(db.DateTime)
    
    # Contract version control
    contract_generation_hash = db.Column(db.String(64))  # SHA-256 hash of tuition data when contract was generated
    contract_needs_regeneration = db.Column(db.Boolean, default=False)  # Set when tuition changes after generation
    contract_regeneration_reason = db.Column(db.String(500))  # Why regeneration is needed
    
    # OpenSign integration for enhanced contracts
    enhanced_contract_opensign_id = db.Column(db.String(100))
    enhanced_contract_opensign_status = db.Column(db.String(20))  # 'pending', 'completed', 'declined', 'expired'