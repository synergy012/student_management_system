"""
Comprehensive Logging System for Student Management System
Provides structured logging, centralized log management, and advanced debugging capabilities
"""

import os
import json
import logging
import traceback
import functools
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from logging.handlers import RotatingFileHandler, SMTPHandler
from flask import request, current_app, session, g
from flask_login import current_user
from contextlib import contextmanager
import gzip
import shutil

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output"""
    
    def format(self, record):
        # Create base log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add request context if available
        if request:
            log_entry['request'] = {
                'method': request.method,
                'url': request.url,
                'remote_addr': request.remote_addr,
                'user_agent': request.user_agent.string[:200] if request.user_agent else None,
                'endpoint': request.endpoint,
                'view_args': dict(request.view_args) if request.view_args else None
            }
        
        # Add user context if available
        if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            log_entry['user'] = {
                'id': current_user.id,
                'username': current_user.username,
                'is_admin': getattr(current_user, 'is_admin', False)
            }
        
        # Add session info
        if session:
            log_entry['session_id'] = session.get('_id', 'no_session')
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add any extra fields from the log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 
                          'msecs', 'relativeCreated', 'thread', 'threadName', 
                          'processName', 'process', 'exc_info', 'exc_text', 'stack_info']:
                extra_fields[key] = value
        
        if extra_fields:
            log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, separators=(',', ':'))

class LogManager:
    """Centralized log management"""
    
    def __init__(self, app=None):
        self.app = app
        self.loggers = {}
        self.log_levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize logging for Flask app"""
        self.app = app
        
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        # Configure main application logger
        self.setup_application_logger()
        
        # Configure specialized loggers
        self.setup_security_logger()
        self.setup_audit_logger()
        self.setup_performance_logger()
        self.setup_database_logger()
        self.setup_webhook_logger()
        
        # Setup log rotation
        self.setup_log_rotation()
        
        # Configure error email alerts for production
        if not app.debug:
            self.setup_email_alerts()
    
    def setup_application_logger(self):
        """Setup main application logger"""
        logger = logging.getLogger('app')
        logger.setLevel(logging.INFO)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            'logs/application.log',
            maxBytes=50*1024*1024,  # 50MB
            backupCount=10
        )
        file_handler.setFormatter(StructuredFormatter())
        
        # Console handler for development
        if self.app.debug:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            ))
            logger.addHandler(console_handler)
        
        logger.addHandler(file_handler)
        self.loggers['app'] = logger
    
    def setup_security_logger(self):
        """Setup security events logger"""
        logger = logging.getLogger('security')
        logger.setLevel(logging.INFO)
        
        file_handler = RotatingFileHandler(
            'logs/security.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=20
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        self.loggers['security'] = logger
    
    def setup_audit_logger(self):
        """Setup audit trail logger"""
        logger = logging.getLogger('audit')
        logger.setLevel(logging.INFO)
        
        file_handler = RotatingFileHandler(
            'logs/audit.log',
            maxBytes=20*1024*1024,  # 20MB
            backupCount=15
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        self.loggers['audit'] = logger
    
    def setup_performance_logger(self):
        """Setup performance monitoring logger"""
        logger = logging.getLogger('performance')
        logger.setLevel(logging.INFO)
        
        file_handler = RotatingFileHandler(
            'logs/performance.log',
            maxBytes=30*1024*1024,  # 30MB
            backupCount=10
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        self.loggers['performance'] = logger
    
    def setup_database_logger(self):
        """Setup database operations logger"""
        logger = logging.getLogger('database')
        logger.setLevel(logging.WARNING)  # Only log warnings and errors
        
        file_handler = RotatingFileHandler(
            'logs/database.log',
            maxBytes=15*1024*1024,  # 15MB
            backupCount=10
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        self.loggers['database'] = logger
    
    def setup_webhook_logger(self):
        """Setup webhook events logger"""
        logger = logging.getLogger('webhook')
        logger.setLevel(logging.INFO)
        
        file_handler = RotatingFileHandler(
            'logs/webhook.log',
            maxBytes=25*1024*1024,  # 25MB
            backupCount=8
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        self.loggers['webhook'] = logger
    
    def setup_email_alerts(self):
        """Setup email alerts for critical errors"""
        mail_handler = SMTPHandler(
            mailhost=(
                self.app.config.get('MAIL_SERVER', 'localhost'),
                self.app.config.get('MAIL_PORT', 587)
            ),
            fromaddr=self.app.config.get('MAIL_USERNAME', 'alerts@system.com'),
            toaddrs=self.app.config.get('ADMIN_EMAIL', 'admin@system.com').split(','),
            subject='Student Management System - Critical Error',
            credentials=(
                self.app.config.get('MAIL_USERNAME'),
                self.app.config.get('MAIL_PASSWORD')
            ),
            secure=() if self.app.config.get('MAIL_USE_TLS') else None
        )
        mail_handler.setLevel(logging.CRITICAL)
        mail_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        # Add to main application logger
        if 'app' in self.loggers:
            self.loggers['app'].addHandler(mail_handler)
    
    def setup_log_rotation(self):
        """Setup automated log rotation and compression"""
        def rotate_logs():
            """Compress old log files"""
            log_dir = 'logs'
            for filename in os.listdir(log_dir):
                if filename.endswith('.log') and not filename.endswith('.gz'):
                    filepath = os.path.join(log_dir, filename)
                    # Check if file is older than 1 day and larger than 10MB
                    if (os.path.getmtime(filepath) < time.time() - 86400 and 
                        os.path.getsize(filepath) > 10*1024*1024):
                        
                        with open(filepath, 'rb') as f_in:
                            with gzip.open(filepath + '.gz', 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(filepath)
        
        # Schedule log rotation (simplified - in production use proper job scheduler)
        timer = threading.Timer(3600.0, rotate_logs)  # Every hour
        timer.daemon = True
        timer.start()
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger by name"""
        return self.loggers.get(name, logging.getLogger(name))

class PerformanceLogger:
    """Performance monitoring and logging"""
    
    def __init__(self):
        self.logger = logging.getLogger('performance')
        self.request_times = {}
        self.slow_queries = []
    
    @contextmanager
    def time_operation(self, operation_name: str, **kwargs):
        """Context manager to time operations"""
        start_time = datetime.utcnow()
        start_timestamp = time.time()
        
        try:
            yield
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = datetime.utcnow()
            duration = time.time() - start_timestamp
            
            self.logger.info(
                f"Operation '{operation_name}' completed",
                extra={
                    'operation': operation_name,
                    'duration_ms': round(duration * 1000, 2),
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'success': success,
                    'error': error,
                    **kwargs
                }
            )
            
            # Log slow operations
            if duration > 2.0:  # Longer than 2 seconds
                self.logger.warning(
                    f"Slow operation detected: '{operation_name}'",
                    extra={
                        'operation': operation_name,
                        'duration_ms': round(duration * 1000, 2),
                        'threshold_exceeded': True,
                        **kwargs
                    }
                )
    
    def log_request_performance(self, endpoint: str, method: str, duration: float, status_code: int):
        """Log request performance metrics"""
        self.logger.info(
            f"Request {method} {endpoint} completed",
            extra={
                'request_type': 'http',
                'endpoint': endpoint,
                'method': method,
                'duration_ms': round(duration * 1000, 2),
                'status_code': status_code,
                'slow': duration > 1.0
            }
        )
    
    def log_database_query(self, query: str, duration: float, row_count: int = None):
        """Log database query performance"""
        self.logger.info(
            "Database query executed",
            extra={
                'query_type': 'database',
                'query_hash': hash(query) % 10000,  # Simple hash for grouping
                'duration_ms': round(duration * 1000, 2),
                'row_count': row_count,
                'slow': duration > 0.5
            }
        )
        
        if duration > 1.0:  # Slow query threshold
            self.slow_queries.append({
                'query': query[:200] + '...' if len(query) > 200 else query,
                'duration': duration,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            # Keep only last 100 slow queries
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]

class AuditLogger:
    """Audit trail logging for compliance"""
    
    def __init__(self):
        self.logger = logging.getLogger('audit')
    
    def log_user_action(self, action: str, target: str = None, details: Dict = None):
        """Log user actions for audit trail"""
        self.logger.info(
            f"User action: {action}",
            extra={
                'audit_type': 'user_action',
                'action': action,
                'target': target,
                'details': details or {},
                'user_id': current_user.id if current_user.is_authenticated else None,
                'username': current_user.username if current_user.is_authenticated else None,
                'ip_address': request.remote_addr if request else None,
                'user_agent': request.user_agent.string if request else None
            }
        )
    
    def log_data_access(self, table: str, operation: str, record_id: Any = None, sensitive: bool = False):
        """Log data access for compliance"""
        self.logger.info(
            f"Data access: {operation} on {table}",
            extra={
                'audit_type': 'data_access',
                'table': table,
                'operation': operation,
                'record_id': str(record_id) if record_id else None,
                'sensitive_data': sensitive,
                'user_id': current_user.id if current_user.is_authenticated else None,
                'username': current_user.username if current_user.is_authenticated else None
            }
        )
    
    def log_system_event(self, event: str, details: Dict = None):
        """Log system events"""
        self.logger.info(
            f"System event: {event}",
            extra={
                'audit_type': 'system_event',
                'event': event,
                'details': details or {}
            }
        )

class DebugCollector:
    """Collect debug information for troubleshooting"""
    
    def __init__(self):
        self.debug_sessions = {}
        self.max_sessions = 100
    
    def start_debug_session(self, session_id: str = None) -> str:
        """Start a debug session"""
        if not session_id:
            session_id = f"debug_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(self) % 1000}"
        
        self.debug_sessions[session_id] = {
            'start_time': datetime.utcnow(),
            'events': [],
            'context': self._capture_context(),
            'active': True
        }
        
        # Cleanup old sessions
        if len(self.debug_sessions) > self.max_sessions:
            oldest = min(self.debug_sessions.keys(), 
                        key=lambda k: self.debug_sessions[k]['start_time'])
            del self.debug_sessions[oldest]
        
        return session_id
    
    def add_debug_event(self, session_id: str, event_type: str, data: Any):
        """Add event to debug session"""
        if session_id in self.debug_sessions:
            self.debug_sessions[session_id]['events'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'type': event_type,
                'data': data
            })
    
    def end_debug_session(self, session_id: str) -> Dict:
        """End debug session and return collected data"""
        if session_id in self.debug_sessions:
            session = self.debug_sessions[session_id]
            session['active'] = False
            session['end_time'] = datetime.utcnow()
            session['duration'] = (session['end_time'] - session['start_time']).total_seconds()
            return session
        return None
    
    def _capture_context(self) -> Dict:
        """Capture current application context"""
        context = {
            'timestamp': datetime.utcnow().isoformat(),
            'python_version': os.sys.version,
            'platform': os.name
        }
        
        if request:
            context['request'] = {
                'method': request.method,
                'url': request.url,
                'headers': dict(request.headers),
                'remote_addr': request.remote_addr
            }
        
        if current_user and current_user.is_authenticated:
            context['user'] = {
                'id': current_user.id,
                'username': current_user.username
            }
        
        return context

# Decorators for automatic logging
def log_function_call(logger_name: str = 'app', log_args: bool = False, log_result: bool = False):
    """Decorator to automatically log function calls"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(logger_name)
            
            extra_data = {
                'function': func.__name__,
                'module': func.__module__
            }
            
            if log_args:
                extra_data['args'] = str(args)[:200]  # Limit length
                extra_data['kwargs'] = {k: str(v)[:100] for k, v in kwargs.items()}
            
            logger.info(f"Function call: {func.__name__}", extra=extra_data)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                extra_data['duration_ms'] = round(duration * 1000, 2)
                extra_data['success'] = True
                
                if log_result and result is not None:
                    extra_data['result_type'] = type(result).__name__
                    if hasattr(result, '__len__'):
                        extra_data['result_length'] = len(result)
                
                logger.info(f"Function completed: {func.__name__}", extra=extra_data)
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                extra_data['duration_ms'] = round(duration * 1000, 2)
                extra_data['success'] = False
                extra_data['error'] = str(e)
                
                logger.error(f"Function failed: {func.__name__}", extra=extra_data, exc_info=True)
                raise
                
        return wrapper
    return decorator

def audit_action(action: str, target: str = None):
    """Decorator to automatically log audit actions"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            audit_logger = AuditLogger()
            
            try:
                result = func(*args, **kwargs)
                audit_logger.log_user_action(
                    action=action,
                    target=target,
                    details={'success': True, 'function': func.__name__}
                )
                return result
            except Exception as e:
                audit_logger.log_user_action(
                    action=action,
                    target=target,
                    details={'success': False, 'error': str(e), 'function': func.__name__}
                )
                raise
        return wrapper
    return decorator

# Global instances
log_manager = LogManager()
performance_logger = PerformanceLogger()
audit_logger = AuditLogger()
debug_collector = DebugCollector()

# Middleware function to log all requests
def log_requests():
    """Middleware to log all incoming requests"""
    start_time = time.time()
    
    def after_request(response):
        duration = time.time() - start_time
        performance_logger.log_request_performance(
            endpoint=request.endpoint or 'unknown',
            method=request.method,
            duration=duration,
            status_code=response.status_code
        )
        return response
    
    return after_request

# Utility functions
def get_log_files() -> List[Dict[str, Any]]:
    """Get list of available log files"""
    log_files = []
    log_dir = 'logs'
    
    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            if filename.endswith('.log') or filename.endswith('.log.gz'):
                filepath = os.path.join(log_dir, filename)
                stat = os.stat(filepath)
                log_files.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'compressed': filename.endswith('.gz')
                })
    
    return sorted(log_files, key=lambda x: x['modified'], reverse=True)

def search_logs(query: str, log_file: str = None, limit: int = 100) -> List[Dict]:
    """Search through log files"""
    results = []
    log_dir = 'logs'
    
    files_to_search = [log_file] if log_file else [f for f in os.listdir(log_dir) if f.endswith('.log')]
    
    for filename in files_to_search:
        filepath = os.path.join(log_dir, filename)
        if not os.path.exists(filepath):
            continue
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if query.lower() in line.lower():
                        try:
                            # Try to parse as JSON
                            log_entry = json.loads(line)
                            log_entry['file'] = filename
                            log_entry['line_number'] = line_num
                            results.append(log_entry)
                        except json.JSONDecodeError:
                            # Plain text log line
                            results.append({
                                'file': filename,
                                'line_number': line_num,
                                'raw_line': line.strip(),
                                'timestamp': datetime.utcnow().isoformat()
                            })
                        
                        if len(results) >= limit:
                            break
        except Exception as e:
            continue
    
    return results[-limit:]  # Return most recent matches 