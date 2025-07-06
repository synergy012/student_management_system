"""
Database Backup Management Blueprint
Provides web interface for backup operations, monitoring, and recovery
"""

from flask import Blueprint, render_template, jsonify, request, current_app, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from datetime import datetime
import os
from utils.decorators import permission_required
from security_enhancements import admin_ip_required, rate_limit, log_security_event
from database_backup_system import (
    backup_manager, create_immediate_backup, restore_from_backup, 
    get_backup_list, emergency_backup
)

backup = Blueprint('backup', __name__, url_prefix='/backup')

@backup.route('/')
@login_required
@permission_required('manage_users')
@admin_ip_required
def dashboard():
    """Backup management dashboard"""
    try:
        status = backup_manager.get_backup_status()
        recent_backups = sorted(
            get_backup_list()[-10:], 
            key=lambda x: x['timestamp'], 
            reverse=True
        )
        
        return render_template('backup/dashboard.html', 
                             status=status, 
                             recent_backups=recent_backups)
    except Exception as e:
        current_app.logger.error(f"Error loading backup dashboard: {str(e)}")
        flash('Error loading backup dashboard', 'error')
        return redirect(url_for('core.index'))

@backup.route('/api/status')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=30)
def api_status():
    """Get backup system status"""
    try:
        status = backup_manager.get_backup_status()
        return jsonify({
            'success': True,
            'data': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/create', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=5)
def api_create_backup():
    """Create a new backup"""
    try:
        backup_type = request.json.get('type', 'manual')
        
        log_security_event(
            'backup_created',
            f"Admin initiated {backup_type} backup",
            {'backup_type': backup_type}
        )
        
        result = create_immediate_backup(backup_type)
        
        if result['success']:
            current_app.logger.info(f"Backup created by {current_user.username}: {result['backup_info']['name']}")
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Backup creation failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/emergency', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=2)
def api_emergency_backup():
    """Create emergency backup"""
    try:
        log_security_event(
            'emergency_backup',
            "Admin initiated emergency backup",
            {'reason': request.json.get('reason', 'Manual emergency backup')}
        )
        
        result = emergency_backup()
        
        if result['success']:
            current_app.logger.warning(f"Emergency backup created by {current_user.username}: {result['backup_info']['name']}")
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Emergency backup failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/list')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=20)
def api_list_backups():
    """List all available backups"""
    try:
        backups = get_backup_list()
        
        # Sort by timestamp (newest first)
        backups = sorted(backups, key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'data': backups,
            'total': len(backups)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/restore', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=2)
def api_restore_backup():
    """Restore from backup"""
    try:
        backup_name = request.json.get('backup_name')
        target_path = request.json.get('target_path')
        
        if not backup_name:
            return jsonify({
                'success': False,
                'error': 'Backup name is required'
            }), 400
        
        log_security_event(
            'backup_restore_initiated',
            f"Admin initiated restore from backup: {backup_name}",
            {'backup_name': backup_name, 'target_path': target_path}
        )
        
        result = restore_from_backup(backup_name, target_path)
        
        if result['success']:
            current_app.logger.warning(f"Database restored by {current_user.username} from backup: {backup_name}")
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Backup restore failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/verify/<backup_name>')
@login_required
@permission_required('manage_users')
@rate_limit(requests_per_minute=10)
def api_verify_backup(backup_name):
    """Verify backup integrity"""
    try:
        # Find backup info
        backup_info = None
        for backup in get_backup_list():
            if backup['name'] == backup_name:
                backup_info = backup
                break
        
        if not backup_info:
            return jsonify({
                'success': False,
                'error': 'Backup not found'
            }), 404
        
        # Verify file exists
        backup_path = backup_info['file_path']
        if not os.path.exists(backup_path):
            return jsonify({
                'success': False,
                'error': 'Backup file not found',
                'verification': {
                    'file_exists': False,
                    'hash_valid': False,
                    'integrity_valid': False
                }
            })
        
        # Verify hash
        current_hash = backup_manager._calculate_file_hash(backup_path)
        hash_valid = current_hash == backup_info['hash']
        
        # For more detailed verification, we'd need to decompress and check integrity
        # This is a simplified version
        verification_result = {
            'file_exists': True,
            'hash_valid': hash_valid,
            'file_size_matches': os.path.getsize(backup_path) == backup_info['file_size'],
            'backup_info': backup_info
        }
        
        return jsonify({
            'success': True,
            'verification': verification_result
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/cleanup', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=2)
def api_cleanup_backups():
    """Clean up old backups"""
    try:
        log_security_event(
            'backup_cleanup',
            "Admin initiated backup cleanup",
            {}
        )
        
        backup_manager.cleanup_old_backups()
        
        return jsonify({
            'success': True,
            'message': 'Backup cleanup completed'
        })
        
    except Exception as e:
        current_app.logger.error(f"Backup cleanup failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/schedule', methods=['GET', 'POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=10)
def api_backup_schedule():
    """Get or update backup schedule"""
    if request.method == 'GET':
        try:
            return jsonify({
                'success': True,
                'schedule': backup_manager.metadata['backup_schedule'],
                'scheduler_running': backup_manager.scheduler_running
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    else:  # POST
        try:
            new_schedule = request.json.get('schedule', {})
            
            # Validate schedule format
            if 'daily' in new_schedule:
                # Validate time format (HH:MM)
                try:
                    datetime.strptime(new_schedule['daily'], '%H:%M')
                except ValueError:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid daily time format (use HH:MM)'
                    }), 400
            
            # Update schedule
            backup_manager.metadata['backup_schedule'].update(new_schedule)
            backup_manager._save_metadata()
            
            log_security_event(
                'backup_schedule_updated',
                "Admin updated backup schedule",
                {'new_schedule': new_schedule}
            )
            
            # Restart scheduler if running
            if backup_manager.scheduler_running:
                backup_manager.stop_automated_backups()
                backup_manager.start_automated_backups()
            
            return jsonify({
                'success': True,
                'message': 'Backup schedule updated',
                'schedule': backup_manager.metadata['backup_schedule']
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

@backup.route('/api/scheduler/start', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=5)
def api_start_scheduler():
    """Start backup scheduler"""
    try:
        if backup_manager.scheduler_running:
            return jsonify({
                'success': False,
                'error': 'Scheduler is already running'
            })
        
        backup_manager.start_automated_backups()
        
        log_security_event(
            'backup_scheduler_started',
            "Admin started backup scheduler",
            {}
        )
        
        return jsonify({
            'success': True,
            'message': 'Backup scheduler started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/api/scheduler/stop', methods=['POST'])
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=5)
def api_stop_scheduler():
    """Stop backup scheduler"""
    try:
        if not backup_manager.scheduler_running:
            return jsonify({
                'success': False,
                'error': 'Scheduler is not running'
            })
        
        backup_manager.stop_automated_backups()
        
        log_security_event(
            'backup_scheduler_stopped',
            "Admin stopped backup scheduler",
            {}
        )
        
        return jsonify({
            'success': True,
            'message': 'Backup scheduler stopped'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@backup.route('/download/<backup_name>')
@login_required
@permission_required('manage_users')
@admin_ip_required
@rate_limit(requests_per_minute=3)
def download_backup(backup_name):
    """Download a backup file"""
    try:
        # Find backup info
        backup_info = None
        for backup in get_backup_list():
            if backup['name'] == backup_name:
                backup_info = backup
                break
        
        if not backup_info:
            flash('Backup not found', 'error')
            return redirect(url_for('backup.dashboard'))
        
        backup_path = backup_info['file_path']
        if not os.path.exists(backup_path):
            flash('Backup file not found on disk', 'error')
            return redirect(url_for('backup.dashboard'))
        
        log_security_event(
            'backup_download',
            f"Admin downloaded backup: {backup_name}",
            {'backup_name': backup_name, 'file_path': backup_path}
        )
        
        return send_file(backup_path, as_attachment=True)
        
    except Exception as e:
        current_app.logger.error(f"Backup download failed: {str(e)}")
        flash('Error downloading backup file', 'error')
        return redirect(url_for('backup.dashboard'))

# Error handlers for backup blueprint
@backup.errorhandler(403)
def backup_forbidden(error):
    """Handle 403 errors in backup management"""
    log_security_event(
        'backup_access_denied',
        f"Access denied to backup endpoint",
        {'endpoint': request.endpoint, 'ip': request.remote_addr}
    )
    return jsonify({'error': 'Access denied to backup management'}), 403

@backup.errorhandler(429)
def backup_rate_limited(error):
    """Handle rate limiting in backup management"""
    log_security_event(
        'backup_rate_limited',
        f"Rate limit exceeded for backup endpoint",
        {'endpoint': request.endpoint, 'ip': request.remote_addr}
    )
    return jsonify({'error': 'Rate limit exceeded for backup operations'}), 429 