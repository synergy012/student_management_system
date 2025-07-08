"""
Security Enhancement Module for Student Management System
Addresses critical security gaps and implements enterprise-grade security features
"""

import hashlib
import hmac
import secrets
import os
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List, Optional, Any
import bleach
from cryptography.fernet import Fernet
from flask import request, jsonify, current_app, session
from flask_login import current_user
from extensions import db
import ipaddress

# Security Logger
security_logger = logging.getLogger('security')
security_handler = logging.FileHandler('logs/security.log')
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s [SECURITY] %(levelname)s: %(message)s [IP: %(ip)s] [User: %(user)s] [Action: %(action)s]'
))
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)

class SecurityManager:
    """Centralized security management"""
    
    def __init__(self):
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for sensitive data"""
        key_file = 'instance/encryption.key'
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            os.makedirs('instance', exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Owner read/write only
            return key
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data like SSN, medical info"""
        if not data:
            return data
        return self.cipher_suite.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        if not encrypted_data:
            return encrypted_data
        try:
            return self.cipher_suite.decrypt(encrypted_data.encode()).decode()
        except:
            return "[DECRYPTION_ERROR]"

class RateLimiter:
    """Simple rate limiting without Redis dependency"""
    
    def __init__(self):
        self.requests = {}
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    def _cleanup_old_requests(self):
        """Remove old request records"""
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            for key in list(self.requests.keys()):
                self.requests[key] = [
                    timestamp for timestamp in self.requests[key]
                    if current_time - timestamp < 3600  # Keep last hour
                ]
                if not self.requests[key]:
                    del self.requests[key]
            self.last_cleanup = current_time
    
    def is_rate_limited(self, key: str, limit: int, window: int) -> bool:
        """Check if request should be rate limited"""
        self._cleanup_old_requests()
        
        current_time = time.time()
        
        if key not in self.requests:
            self.requests[key] = []
        
        # Remove old requests outside window
        self.requests[key] = [
            timestamp for timestamp in self.requests[key]
            if current_time - timestamp < window
        ]
        
        # Check if limit exceeded
        if len(self.requests[key]) >= limit:
            return True
        
        # Add current request
        self.requests[key].append(current_time)
        return False

# Global rate limiter instance
rate_limiter = RateLimiter()

def rate_limit(requests_per_minute: int = 60, per_ip: bool = True, per_user: bool = False):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Generate rate limit key
            key_parts = ['ratelimit', f.__name__]
            
            if per_ip:
                key_parts.append(request.remote_addr)
            
            if per_user and current_user.is_authenticated:
                key_parts.append(str(current_user.id))
            
            key = ':'.join(key_parts)
            
            if rate_limiter.is_rate_limited(key, requests_per_minute, 60):
                log_security_event(
                    'rate_limit_exceeded',
                    f"Rate limit exceeded for {f.__name__}",
                    {'endpoint': f.__name__, 'limit': requests_per_minute}
                )
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

class InputSanitizer:
    """Comprehensive input sanitization"""
    
    @staticmethod
    def sanitize_html(input_text: str) -> str:
        """Sanitize HTML input to prevent XSS"""
        if not input_text:
            return input_text
            
        allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br']
        allowed_attributes = {}
        
        return bleach.clean(
            input_text, 
            tags=allowed_tags, 
            attributes=allowed_attributes,
            strip=True
        )
    
    @staticmethod
    def sanitize_sql_input(input_text: str) -> str:
        """Basic SQL injection prevention"""
        if not input_text:
            return input_text
            
        dangerous_chars = ["'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_']
        for char in dangerous_chars:
            input_text = input_text.replace(char, '')
        
        return input_text.strip()
    
    @staticmethod
    def validate_file_upload(file) -> Dict[str, Any]:
        """Validate uploaded files for security"""
        if not file or not file.filename:
            return {'valid': False, 'error': 'No file provided'}
        
        # Check file size (50MB limit)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 50 * 1024 * 1024:
            return {'valid': False, 'error': 'File too large'}
        
        # Check file extension
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.doc', '.docx', '.txt'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            return {'valid': False, 'error': 'File type not allowed'}
        
        # Check for executable files
        executable_extensions = {'.exe', '.bat', '.sh', '.cmd', '.com', '.scr', '.pif'}
        if file_ext in executable_extensions:
            return {'valid': False, 'error': 'Executable files not allowed'}
        
        # Basic malware scan (check for suspicious patterns)
        file_content = file.read(1024)  # Read first 1KB
        file.seek(0)
        
        suspicious_patterns = [b'MZ', b'PK\x03\x04', b'\x7fELF']  # PE, ZIP, ELF headers
        for pattern in suspicious_patterns:
            if pattern in file_content and file_ext not in {'.zip', '.docx'}:
                return {'valid': False, 'error': 'Suspicious file content detected'}
        
        return {'valid': True, 'file_size': file_size}

class SessionSecurity:
    """Enhanced session security"""
    
    @staticmethod
    def validate_session():
        """Validate current session for security"""
        if not current_user.is_authenticated:
            return True
        
        # Check session timeout
        last_activity = session.get('last_activity')
        if last_activity:
            last_activity_time = datetime.fromisoformat(last_activity)
            if datetime.utcnow() - last_activity_time > timedelta(hours=2):
                return False
        
        # Update last activity
        session['last_activity'] = datetime.utcnow().isoformat()
        
        # Check for session hijacking (IP change)
        session_ip = session.get('ip_address')
        current_ip = request.remote_addr
        
        if session_ip and session_ip != current_ip:
            log_security_event(
                'session_hijacking_attempt',
                f"IP change detected for user {current_user.id}",
                {'old_ip': session_ip, 'new_ip': current_ip}
            )
            return False
        
        session['ip_address'] = current_ip
        return True

class DataMasking:
    """Data masking for logging and display"""
    
    @staticmethod
    def mask_ssn(ssn: str) -> str:
        """Mask SSN for display"""
        if not ssn or len(ssn) < 4:
            return "***-**-****"
        return f"***-**-{ssn[-4:]}"
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email for logging"""
        if not email or '@' not in email:
            return "***@***"
        local, domain = email.split('@', 1)
        return f"{local[:2]}***@{domain}"
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone number"""
        if not phone or len(phone) < 4:
            return "***-***-****"
        return f"***-***-{phone[-4:]}"

def log_security_event(event_type: str, description: str, extra_data: Dict = None):
    """Log security events"""
    extra_data = extra_data or {}
    
    security_logger.info(
        description,
        extra={
            'ip': request.remote_addr if request else 'N/A',
            'user': current_user.username if current_user.is_authenticated else 'anonymous',
            'action': event_type,
            'extra': extra_data
        }
    )

def audit_decorator(action: str):
    """Decorator for auditing sensitive actions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            
            # Log action start
            log_security_event(
                f'{action}_started',
                f"Started {action}",
                {'function': f.__name__, 'args_count': len(args)}
            )
            
            try:
                result = f(*args, **kwargs)
                
                # Log successful completion
                log_security_event(
                    f'{action}_completed',
                    f"Completed {action} successfully",
                    {'function': f.__name__, 'duration': time.time() - start_time}
                )
                
                return result
                
            except Exception as e:
                # Log failure
                log_security_event(
                    f'{action}_failed',
                    f"Failed {action}: {str(e)}",
                    {'function': f.__name__, 'error': str(e), 'duration': time.time() - start_time}
                )
                raise
                
        return decorated_function
    return decorator

class IPWhitelist:
    """IP whitelisting for admin functions"""
    
    def __init__(self):
        self.whitelist = self._load_whitelist()
    
    def _load_whitelist(self) -> List[str]:
        """Load IP whitelist from environment or config"""
        whitelist_str = os.getenv('ADMIN_IP_WHITELIST', '127.0.0.1,::1')
        return [ip.strip() for ip in whitelist_str.split(',')]
    
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is in whitelist"""
        if not self.whitelist:
            return True
            
        try:
            client_ip = ipaddress.ip_address(ip)
            for allowed_ip in self.whitelist:
                if '/' in allowed_ip:
                    # CIDR notation
                    if client_ip in ipaddress.ip_network(allowed_ip):
                        return True
                else:
                    # Exact IP
                    if client_ip == ipaddress.ip_address(allowed_ip):
                        return True
            return False
        except:
            return False

def admin_ip_required(f):
    """Decorator to restrict admin functions to whitelisted IPs"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip_whitelist = IPWhitelist()
        
        if not ip_whitelist.is_ip_allowed(request.remote_addr):
            log_security_event(
                'admin_access_denied',
                f"Admin access denied from non-whitelisted IP",
                {'requested_endpoint': f.__name__}
            )
            return jsonify({'error': 'Access denied from this IP'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# Initialize global security manager
security_manager = SecurityManager() 