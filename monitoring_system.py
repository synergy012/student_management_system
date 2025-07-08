"""
Comprehensive Monitoring and Alerting System
Provides real-time monitoring, health checks, performance metrics, and automated alerting
"""

import os
import time
import psutil
import logging
import json
import threading
import smtplib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from flask import current_app
from extensions import db
from models import User, Application, Student

# Monitoring Logger
monitoring_logger = logging.getLogger('monitoring')
monitoring_handler = logging.FileHandler('logs/monitoring.log')
monitoring_handler.setFormatter(logging.Formatter(
    '%(asctime)s [MONITORING] %(levelname)s: %(message)s'
))
monitoring_logger.addHandler(monitoring_handler)
monitoring_logger.setLevel(logging.INFO)

@dataclass
class HealthCheck:
    """Health check result"""
    name: str
    status: str  # healthy, warning, critical
    message: str
    timestamp: datetime
    response_time: float
    details: Dict[str, Any] = None

@dataclass
class MetricValue:
    """Metric measurement"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    tags: Dict[str, str] = None

class SystemMonitor:
    """System resource monitoring"""
    
    def __init__(self):
        self.thresholds = {
            'cpu_warning': 70.0,
            'cpu_critical': 85.0,
            'memory_warning': 75.0,
            'memory_critical': 90.0,
            'disk_warning': 80.0,
            'disk_critical': 95.0,
            'response_time_warning': 2.0,
            'response_time_critical': 5.0
        }
    
    def get_system_metrics(self) -> List[MetricValue]:
        """Get current system metrics"""
        metrics = []
        timestamp = datetime.utcnow()
        
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=1)
        metrics.append(MetricValue(
            name='cpu_usage',
            value=cpu_percent,
            unit='percent',
            timestamp=timestamp
        ))
        
        # Memory Usage
        memory = psutil.virtual_memory()
        metrics.append(MetricValue(
            name='memory_usage',
            value=memory.percent,
            unit='percent',
            timestamp=timestamp
        ))
        
        # Disk Usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        metrics.append(MetricValue(
            name='disk_usage',
            value=disk_percent,
            unit='percent',
            timestamp=timestamp
        ))
        
        # Process count
        process_count = len(psutil.pids())
        metrics.append(MetricValue(
            name='process_count',
            value=process_count,
            unit='count',
            timestamp=timestamp
        ))
        
        return metrics
    
    def check_system_health(self) -> List[HealthCheck]:
        """Perform system health checks"""
        checks = []
        timestamp = datetime.utcnow()
        
        # CPU Health Check
        start_time = time.time()
        cpu_percent = psutil.cpu_percent(interval=1)
        response_time = time.time() - start_time
        
        if cpu_percent >= self.thresholds['cpu_critical']:
            status = 'critical'
            message = f'CPU usage critically high: {cpu_percent:.1f}%'
        elif cpu_percent >= self.thresholds['cpu_warning']:
            status = 'warning'
            message = f'CPU usage high: {cpu_percent:.1f}%'
        else:
            status = 'healthy'
            message = f'CPU usage normal: {cpu_percent:.1f}%'
        
        checks.append(HealthCheck(
            name='cpu_usage',
            status=status,
            message=message,
            timestamp=timestamp,
            response_time=response_time,
            details={'cpu_percent': cpu_percent}
        ))
        
        # Memory Health Check
        memory = psutil.virtual_memory()
        if memory.percent >= self.thresholds['memory_critical']:
            status = 'critical'
            message = f'Memory usage critically high: {memory.percent:.1f}%'
        elif memory.percent >= self.thresholds['memory_warning']:
            status = 'warning'
            message = f'Memory usage high: {memory.percent:.1f}%'
        else:
            status = 'healthy'
            message = f'Memory usage normal: {memory.percent:.1f}%'
        
        checks.append(HealthCheck(
            name='memory_usage',
            status=status,
            message=message,
            timestamp=timestamp,
            response_time=0.01,
            details={'memory_percent': memory.percent, 'available_mb': memory.available // 1024 // 1024}
        ))
        
        # Disk Health Check
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        if disk_percent >= self.thresholds['disk_critical']:
            status = 'critical'
            message = f'Disk usage critically high: {disk_percent:.1f}%'
        elif disk_percent >= self.thresholds['disk_warning']:
            status = 'warning'
            message = f'Disk usage high: {disk_percent:.1f}%'
        else:
            status = 'healthy'
            message = f'Disk usage normal: {disk_percent:.1f}%'
        
        checks.append(HealthCheck(
            name='disk_usage',
            status=status,
            message=message,
            timestamp=timestamp,
            response_time=0.01,
            details={'disk_percent': disk_percent, 'free_gb': disk.free // 1024 // 1024 // 1024}
        ))
        
        return checks

class DatabaseMonitor:
    """Database health and performance monitoring"""
    
    def check_database_health(self) -> List[HealthCheck]:
        """Check database connectivity and performance"""
        checks = []
        timestamp = datetime.utcnow()
        
        # Database Connectivity Check
        start_time = time.time()
        try:
            # Simple query to test connectivity
            result = db.session.execute("SELECT 1").scalar()
            response_time = time.time() - start_time
            
            if response_time > 5.0:
                status = 'critical'
                message = f'Database response very slow: {response_time:.2f}s'
            elif response_time > 2.0:
                status = 'warning'
                message = f'Database response slow: {response_time:.2f}s'
            else:
                status = 'healthy'
                message = f'Database responsive: {response_time:.3f}s'
            
            checks.append(HealthCheck(
                name='database_connectivity',
                status=status,
                message=message,
                timestamp=timestamp,
                response_time=response_time,
                details={'query_result': result}
            ))
            
        except Exception as e:
            response_time = time.time() - start_time
            checks.append(HealthCheck(
                name='database_connectivity',
                status='critical',
                message=f'Database connection failed: {str(e)}',
                timestamp=timestamp,
                response_time=response_time,
                details={'error': str(e)}
            ))
        
        # Table Record Counts
        try:
            user_count = User.query.count()
            application_count = Application.query.count()
            student_count = Student.query.count()
            
            checks.append(HealthCheck(
                name='database_records',
                status='healthy',
                message=f'Records: {user_count} users, {application_count} applications, {student_count} students',
                timestamp=timestamp,
                response_time=0.1,
                details={
                    'user_count': user_count,
                    'application_count': application_count,
                    'student_count': student_count
                }
            ))
            
        except Exception as e:
            checks.append(HealthCheck(
                name='database_records',
                status='warning',
                message=f'Could not get record counts: {str(e)}',
                timestamp=timestamp,
                response_time=0.1,
                details={'error': str(e)}
            ))
        
        return checks

class ApplicationMonitor:
    """Application-specific monitoring"""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.request_count = 0
        self.error_count = 0
        self.last_error = None
    
    def increment_request_count(self):
        """Increment request counter"""
        self.request_count += 1
    
    def increment_error_count(self, error: str):
        """Increment error counter"""
        self.error_count += 1
        self.last_error = error
    
    def get_application_metrics(self) -> List[MetricValue]:
        """Get application-specific metrics"""
        metrics = []
        timestamp = datetime.utcnow()
        uptime = (timestamp - self.start_time).total_seconds()
        
        metrics.append(MetricValue(
            name='app_uptime',
            value=uptime,
            unit='seconds',
            timestamp=timestamp
        ))
        
        metrics.append(MetricValue(
            name='app_requests',
            value=self.request_count,
            unit='count',
            timestamp=timestamp
        ))
        
        metrics.append(MetricValue(
            name='app_errors',
            value=self.error_count,
            unit='count',
            timestamp=timestamp
        ))
        
        # Request rate (requests per minute)
        request_rate = (self.request_count / uptime) * 60 if uptime > 0 else 0
        metrics.append(MetricValue(
            name='app_request_rate',
            value=request_rate,
            unit='requests_per_minute',
            timestamp=timestamp
        ))
        
        return metrics
    
    def check_application_health(self) -> List[HealthCheck]:
        """Check application health"""
        checks = []
        timestamp = datetime.utcnow()
        uptime = (timestamp - self.start_time).total_seconds()
        
        # Uptime Check
        if uptime < 60:  # Less than 1 minute
            status = 'warning'
            message = f'Application recently started: {uptime:.0f}s ago'
        else:
            status = 'healthy'
            uptime_hours = uptime / 3600
            message = f'Application uptime: {uptime_hours:.1f} hours'
        
        checks.append(HealthCheck(
            name='application_uptime',
            status=status,
            message=message,
            timestamp=timestamp,
            response_time=0.001,
            details={'uptime_seconds': uptime}
        ))
        
        # Error Rate Check
        error_rate = (self.error_count / self.request_count) * 100 if self.request_count > 0 else 0
        
        if error_rate > 10:
            status = 'critical'
            message = f'High error rate: {error_rate:.1f}%'
        elif error_rate > 5:
            status = 'warning'
            message = f'Elevated error rate: {error_rate:.1f}%'
        else:
            status = 'healthy'
            message = f'Low error rate: {error_rate:.1f}%'
        
        checks.append(HealthCheck(
            name='application_errors',
            status=status,
            message=message,
            timestamp=timestamp,
            response_time=0.001,
            details={
                'error_rate': error_rate,
                'error_count': self.error_count,
                'request_count': self.request_count,
                'last_error': self.last_error
            }
        ))
        
        return checks

class AlertManager:
    """Alert management and notification system"""
    
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_recipients = self._load_alert_recipients()
        self.alert_cooldown = {}  # Prevent spam
        self.cooldown_period = 300  # 5 minutes
    
    def _load_alert_recipients(self) -> List[str]:
        """Load alert recipients from environment"""
        recipients_str = os.getenv('ALERT_RECIPIENTS', '')
        return [email.strip() for email in recipients_str.split(',') if email.strip()]
    
    def should_send_alert(self, alert_key: str) -> bool:
        """Check if alert should be sent (cooldown logic)"""
        current_time = time.time()
        
        if alert_key in self.alert_cooldown:
            last_sent = self.alert_cooldown[alert_key]
            if current_time - last_sent < self.cooldown_period:
                return False
        
        self.alert_cooldown[alert_key] = current_time
        return True
    
    def send_alert(self, subject: str, message: str, alert_type: str = 'warning'):
        """Send alert email"""
        if not self.alert_recipients or not self.smtp_user:
            monitoring_logger.warning("Alert recipients or SMTP not configured")
            return False
        
        alert_key = f"{alert_type}_{subject}"
        
        if not self.should_send_alert(alert_key):
            monitoring_logger.info(f"Alert cooldown active for: {alert_key}")
            return False
        
        try:
            msg = MimeMultipart()
            msg['From'] = self.smtp_user
            msg['To'] = ', '.join(self.alert_recipients)
            msg['Subject'] = f"[{alert_type.upper()}] Student Management System - {subject}"
            
            body = f"""
Alert Type: {alert_type.upper()}
Timestamp: {datetime.utcnow().isoformat()}
System: Student Management System

{message}

---
This is an automated alert from the Student Management System monitoring.
"""
            
            msg.attach(MimeText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            monitoring_logger.info(f"Alert sent: {subject}")
            return True
            
        except Exception as e:
            monitoring_logger.error(f"Failed to send alert: {str(e)}")
            return False
    
    def process_health_checks(self, health_checks: List[HealthCheck]):
        """Process health checks and send alerts if needed"""
        critical_checks = [check for check in health_checks if check.status == 'critical']
        warning_checks = [check for check in health_checks if check.status == 'warning']
        
        # Send critical alerts
        for check in critical_checks:
            self.send_alert(
                subject=f"CRITICAL: {check.name}",
                message=f"{check.message}\n\nDetails: {json.dumps(check.details, indent=2)}",
                alert_type='critical'
            )
        
        # Send warning alerts (less frequently)
        if warning_checks:
            warning_summary = "\n".join([f"- {check.name}: {check.message}" for check in warning_checks])
            self.send_alert(
                subject=f"System Warnings ({len(warning_checks)} issues)",
                message=f"The following warnings were detected:\n\n{warning_summary}",
                alert_type='warning'
            )

class MonitoringDashboard:
    """Centralized monitoring dashboard"""
    
    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.database_monitor = DatabaseMonitor()
        self.application_monitor = ApplicationMonitor()
        self.alert_manager = AlertManager()
        self.monitoring_active = True
        self.monitoring_thread = None
    
    def start_monitoring(self):
        """Start background monitoring"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        monitoring_logger.info("Monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join()
        monitoring_logger.info("Monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Perform all health checks
                all_health_checks = []
                all_health_checks.extend(self.system_monitor.check_system_health())
                all_health_checks.extend(self.database_monitor.check_database_health())
                all_health_checks.extend(self.application_monitor.check_application_health())
                
                # Process alerts
                self.alert_manager.process_health_checks(all_health_checks)
                
                # Log health status
                critical_count = len([c for c in all_health_checks if c.status == 'critical'])
                warning_count = len([c for c in all_health_checks if c.status == 'warning'])
                
                monitoring_logger.info(
                    f"Health check completed: {critical_count} critical, {warning_count} warnings"
                )
                
                # Wait before next check
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                monitoring_logger.error(f"Error in monitoring loop: {str(e)}")
                time.sleep(60)
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current system status"""
        # Get all health checks
        system_checks = self.system_monitor.check_system_health()
        database_checks = self.database_monitor.check_database_health()
        app_checks = self.application_monitor.check_application_health()
        
        all_checks = system_checks + database_checks + app_checks
        
        # Get all metrics
        system_metrics = self.system_monitor.get_system_metrics()
        app_metrics = self.application_monitor.get_application_metrics()
        
        all_metrics = system_metrics + app_metrics
        
        # Calculate overall status
        critical_count = len([c for c in all_checks if c.status == 'critical'])
        warning_count = len([c for c in all_checks if c.status == 'warning'])
        
        if critical_count > 0:
            overall_status = 'critical'
        elif warning_count > 0:
            overall_status = 'warning'
        else:
            overall_status = 'healthy'
        
        return {
            'overall_status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'health_checks': [asdict(check) for check in all_checks],
            'metrics': [asdict(metric) for metric in all_metrics],
            'summary': {
                'total_checks': len(all_checks),
                'critical_count': critical_count,
                'warning_count': warning_count,
                'healthy_count': len(all_checks) - critical_count - warning_count
            }
        }

# Global monitoring instance
monitoring_dashboard = MonitoringDashboard()

def init_monitoring():
    """Initialize monitoring system"""
    monitoring_dashboard.start_monitoring()
    monitoring_logger.info("Monitoring system initialized")

def get_monitoring_status():
    """Get current monitoring status"""
    return monitoring_dashboard.get_current_status()

def log_request():
    """Log incoming request (call from middleware)"""
    monitoring_dashboard.application_monitor.increment_request_count()

def log_error(error: str):
    """Log application error"""
    monitoring_dashboard.application_monitor.increment_error_count(error) 