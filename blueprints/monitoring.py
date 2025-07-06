"""
Monitoring Blueprint for Real-time System Monitoring Dashboard
Provides web interface for system health, performance metrics, and alerts
"""

from flask import Blueprint, render_template, jsonify, request, current_app, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import json
import os
from utils.decorators import permission_required
from security_enhancements import admin_ip_required, rate_limit, log_security_event
from monitoring_system import get_monitoring_status, monitoring_dashboard
from logging_system import get_log_files, search_logs, debug_collector

monitoring = Blueprint('monitoring', __name__, url_prefix='/monitoring')

@monitoring.route('/')
@login_required
@permission_required('manage_users')
def dashboard():
    """Main monitoring dashboard"""
    try:
        # Basic monitoring dashboard
        return render_template('monitoring/dashboard.html')
    except Exception as e:
        current_app.logger.error(f"Error loading monitoring dashboard: {str(e)}")
        flash('Error loading monitoring dashboard', 'error')
        return redirect(url_for('core.index'))

@monitoring.route('/api/status')
@login_required
@permission_required('manage_users')
def api_status():
    """API endpoint for real-time status updates"""
    try:
        # Return basic status for now
        status = {
            'overall_status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'health_checks': [],
            'metrics': [],
            'summary': {
                'total_checks': 0,
                'critical_count': 0,
                'warning_count': 0,
                'healthy_count': 0
            }
        }
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/health-checks')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=60)
def api_health_checks():
    """Get detailed health check results"""
    try:
        status = get_monitoring_status()
        health_checks = status.get('health_checks', [])
        
        # Group by status
        grouped = {
            'critical': [h for h in health_checks if h['status'] == 'critical'],
            'warning': [h for h in health_checks if h['status'] == 'warning'],
            'healthy': [h for h in health_checks if h['status'] == 'healthy']
        }
        
        return jsonify({
            'success': True,
            'data': grouped,
            'summary': status.get('summary', {})
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/metrics')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=60)
def api_metrics():
    """Get system metrics"""
    try:
        status = get_monitoring_status()
        metrics = status.get('metrics', [])
        
        # Group metrics by type
        grouped_metrics = {}
        for metric in metrics:
            metric_type = metric['name'].split('_')[0]  # cpu, memory, disk, app
            if metric_type not in grouped_metrics:
                grouped_metrics[metric_type] = []
            grouped_metrics[metric_type].append(metric)
        
        return jsonify({
            'success': True,
            'data': grouped_metrics,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/logs')
@login_required
@permission_required('manage_users')
@admin_ip_required
def logs_viewer():
    """Log file viewer interface"""
    try:
        log_files = get_log_files()
        return render_template('monitoring/logs.html', log_files=log_files)
    except Exception as e:
        current_app.logger.error(f"Error loading log viewer: {str(e)}")
        flash('Error loading log viewer', 'error')
        return redirect(url_for('monitoring.dashboard'))

@monitoring.route('/api/logs/search')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=20)
def api_search_logs():
    """Search through log files"""
    try:
        query = request.args.get('q', '')
        log_file = request.args.get('file')
        limit = min(int(request.args.get('limit', 100)), 500)  # Max 500 results
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query is required'
            }), 400
        
        # Log the search for audit
        log_security_event(
            'log_search',
            f"Admin searched logs for: {query}",
            {'query': query, 'file': log_file, 'limit': limit}
        )
        
        results = search_logs(query, log_file, limit)
        
        return jsonify({
            'success': True,
            'data': results,
            'query': query,
            'total_results': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/logs/files')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=30)
def api_log_files():
    """Get list of available log files"""
    try:
        log_files = get_log_files()
        return jsonify({
            'success': True,
            'data': log_files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/logs/download/<filename>')
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=5)
def download_log_file(filename):
    """Download a log file"""
    try:
        # Security check - prevent path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        log_path = os.path.join('logs', filename)
        if not os.path.exists(log_path):
            return jsonify({'error': 'Log file not found'}), 404
        
        # Log the download for audit
        log_security_event(
            'log_download',
            f"Admin downloaded log file: {filename}",
            {'filename': filename}
        )
        
        from flask import send_file
        return send_file(log_path, as_attachment=True)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/debug')
@login_required
@permission_required('manage_users')
@admin_ip_required
def debug_tools():
    """Debug tools interface"""
    try:
        return render_template('monitoring/debug.html')
    except Exception as e:
        current_app.logger.error(f"Error loading debug tools: {str(e)}")
        flash('Error loading debug tools', 'error')
        return redirect(url_for('monitoring.dashboard'))

@monitoring.route('/api/debug/start-session')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=10)
def api_start_debug_session():
    """Start a new debug session"""
    try:
        session_id = debug_collector.start_debug_session()
        
        log_security_event(
            'debug_session_started',
            f"Admin started debug session: {session_id}",
            {'session_id': session_id}
        )
        
        return jsonify({
            'success': True,
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/debug/sessions')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=20)
def api_debug_sessions():
    """Get list of debug sessions"""
    try:
        sessions = []
        for session_id, session_data in debug_collector.debug_sessions.items():
            sessions.append({
                'id': session_id,
                'start_time': session_data['start_time'].isoformat(),
                'active': session_data['active'],
                'event_count': len(session_data['events'])
            })
        
        return jsonify({
            'success': True,
            'data': sessions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/debug/session/<session_id>')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=20)
def api_debug_session_details(session_id):
    """Get debug session details"""
    try:
        if session_id not in debug_collector.debug_sessions:
            return jsonify({
                'success': False,
                'error': 'Debug session not found'
            }), 404
        
        session_data = debug_collector.debug_sessions[session_id]
        
        return jsonify({
            'success': True,
            'data': {
                'id': session_id,
                'start_time': session_data['start_time'].isoformat(),
                'active': session_data['active'],
                'events': session_data['events'][-50:],  # Last 50 events
                'context': session_data['context']
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/alerts/test')
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=2)
def api_test_alerts():
    """Test alert system"""
    try:
        from monitoring_system import monitoring_dashboard
        
        # Send test alert
        result = monitoring_dashboard.alert_manager.send_alert(
            subject="Test Alert",
            message="This is a test alert from the monitoring system.",
            alert_type="warning"
        )
        
        log_security_event(
            'alert_test',
            "Admin tested alert system",
            {'result': result}
        )
        
        return jsonify({
            'success': True,
            'message': 'Test alert sent' if result else 'Failed to send test alert'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/system/restart')
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=1)
def api_restart_monitoring():
    """Restart monitoring system"""
    try:
        # Stop and restart monitoring
        monitoring_dashboard.stop_monitoring()
        monitoring_dashboard.start_monitoring()
        
        log_security_event(
            'monitoring_restart',
            "Admin restarted monitoring system",
            {}
        )
        
        return jsonify({
            'success': True,
            'message': 'Monitoring system restarted'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@monitoring.route('/api/performance/slow-queries')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=20)
def api_slow_queries():
    """Get slow database queries"""
    try:
        from logging_system import performance_logger
        
        slow_queries = performance_logger.slow_queries[-50:]  # Last 50 slow queries
        
        return jsonify({
            'success': True,
            'data': slow_queries,
            'total': len(slow_queries)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Error handlers for monitoring blueprint
@monitoring.errorhandler(403)
def monitoring_forbidden(error):
    """Handle 403 errors in monitoring"""
    log_security_event(
        'monitoring_access_denied',
        f"Access denied to monitoring endpoint",
        {'endpoint': request.endpoint, 'ip': request.remote_addr}
    )
    return jsonify({'error': 'Access denied to monitoring features'}), 403

@monitoring.errorhandler(429)
def monitoring_rate_limited(error):
    """Handle rate limiting in monitoring"""
    log_security_event(
        'monitoring_rate_limited',
        f"Rate limit exceeded for monitoring endpoint",
        {'endpoint': request.endpoint, 'ip': request.remote_addr}
    )
    return jsonify({'error': 'Rate limit exceeded'}), 429 