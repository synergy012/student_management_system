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
    
    # Dormitory and Meals Option - NEW FIELD
    dormitory_meals_option = db.Column(db.String(200))
    
    # Additional Information
    additional_info = db.Column(db.Text)
    
    # Documents (stored as JSON for file references) - Added: Missing from Student table
    documents = db.Column(db.JSON)
    
    # Custom fields for storing additional structured data (JSON)
    custom_fields = db.Column(db.Text)  # JSON encoded

    # Relationship to original application
    application = db.relationship('Application', backref=db.backref('student', uselist=False))
    
    # Relationship to file attachments
    attachments = db.relationship('FileAttachment', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
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
    
    @property
    def financial_aid(self):
        """Get financial aid information"""
        return {
            'payment_status': self.tuition_payment_status or '',
            'amount_can_pay': float(self.amount_can_pay) if self.amount_can_pay else 0.0,
            'scholarship_requested': float(self.scholarship_amount_requested) if self.scholarship_amount_requested else 0.0,
            'explanation': self.financial_aid_explanation or ''
        }
    
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

def init_db():
    """Initialize the database with default permissions"""
    for perm_name in Permission.get_all_permissions():
        if not Permission.query.filter_by(name=perm_name).first():
            perm = Permission(name=perm_name)
            db.session.add(perm)
    db.session.commit() 