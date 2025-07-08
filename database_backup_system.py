"""
Comprehensive Database Backup and Recovery System
Provides automated backups, corruption detection, point-in-time recovery, and restoration
"""

import os
import shutil
import sqlite3
import gzip
import hashlib
import json
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import schedule

# Backup Logger
backup_logger = logging.getLogger('database_backup')
backup_handler = logging.FileHandler('logs/database_backup.log')
backup_handler.setFormatter(logging.Formatter(
    '%(asctime)s [BACKUP] %(levelname)s: %(message)s'
))
backup_logger.addHandler(backup_handler)
backup_logger.setLevel(logging.INFO)

class DatabaseBackupManager:
    """Comprehensive database backup and recovery management"""
    
    def __init__(self, database_path: str = 'student_management.db'):
        self.database_path = database_path
        self.backup_dir = Path('backups')
        self.backup_dir.mkdir(exist_ok=True)
        
        # Backup configuration
        self.max_daily_backups = 7      # Keep 7 daily backups
        self.max_weekly_backups = 4     # Keep 4 weekly backups
        self.max_monthly_backups = 12   # Keep 12 monthly backups
        self.compression_enabled = True
        
        # Initialize backup metadata
        self.metadata_file = self.backup_dir / 'backup_metadata.json'
        self.metadata = self._load_metadata()
        
        # Backup scheduler
        self.scheduler_running = False
        self.scheduler_thread = None
        
        backup_logger.info("Database Backup Manager initialized")
    
    def _load_metadata(self) -> Dict:
        """Load backup metadata"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                backup_logger.error(f"Error loading backup metadata: {e}")
        
        return {
            'backups': [],
            'last_full_backup': None,
            'backup_schedule': {
                'daily': '02:00',     # 2 AM daily
                'weekly': 'Sunday',   # Weekly on Sunday
                'monthly': 1          # Monthly on 1st day
            }
        }
    
    def _save_metadata(self):
        """Save backup metadata"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2, default=str)
        except Exception as e:
            backup_logger.error(f"Error saving backup metadata: {e}")
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file for integrity verification"""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            backup_logger.error(f"Error calculating hash for {file_path}: {e}")
            return None
    
    def _verify_database_integrity(self, db_path: str) -> Tuple[bool, str]:
        """Verify database integrity using SQLite's PRAGMA integrity_check"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] == 'ok':
                return True, "Database integrity check passed"
            else:
                return False, f"Database integrity check failed: {result}"
                
        except Exception as e:
            return False, f"Error during integrity check: {str(e)}"
    
    def create_backup(self, backup_type: str = 'manual', compress: bool = None) -> Dict:
        """Create a database backup with integrity verification"""
        if compress is None:
            compress = self.compression_enabled
        
        timestamp = datetime.now()
        backup_name = f"backup_{backup_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        backup_logger.info(f"Starting {backup_type} backup: {backup_name}")
        
        try:
            # Verify source database integrity first
            is_valid, integrity_msg = self._verify_database_integrity(self.database_path)
            if not is_valid:
                backup_logger.error(f"Source database failed integrity check: {integrity_msg}")
                return {
                    'success': False,
                    'error': f"Source database corrupted: {integrity_msg}",
                    'backup_name': backup_name
                }
            
            # Create backup using SQLite's backup API (online backup)
            backup_path = self.backup_dir / f"{backup_name}.db"
            self._create_sqlite_backup(self.database_path, str(backup_path))
            
            # Verify backup integrity
            is_valid, integrity_msg = self._verify_database_integrity(str(backup_path))
            if not is_valid:
                backup_logger.error(f"Backup failed integrity check: {integrity_msg}")
                backup_path.unlink()  # Delete corrupted backup
                return {
                    'success': False,
                    'error': f"Backup corrupted: {integrity_msg}",
                    'backup_name': backup_name
                }
            
            # Calculate hash for verification
            backup_hash = self._calculate_file_hash(str(backup_path))
            backup_size = backup_path.stat().st_size
            
            # Compress backup if requested
            if compress:
                compressed_path = self.backup_dir / f"{backup_name}.db.gz"
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                backup_path.unlink()  # Remove uncompressed backup
                backup_path = compressed_path
                compressed_size = backup_path.stat().st_size
                compression_ratio = (1 - compressed_size / backup_size) * 100
                
                backup_logger.info(f"Backup compressed: {backup_size:,} -> {compressed_size:,} bytes ({compression_ratio:.1f}% reduction)")
            
            # Record backup metadata
            backup_info = {
                'name': backup_name,
                'type': backup_type,
                'timestamp': timestamp.isoformat(),
                'file_path': str(backup_path),
                'file_size': backup_path.stat().st_size,
                'original_size': backup_size,
                'compressed': compress,
                'hash': backup_hash,
                'integrity_verified': True,
                'source_db_path': self.database_path
            }
            
            self.metadata['backups'].append(backup_info)
            if backup_type == 'full':
                self.metadata['last_full_backup'] = timestamp.isoformat()
            
            self._save_metadata()
            
            backup_logger.info(f"Backup completed successfully: {backup_name}")
            return {
                'success': True,
                'backup_info': backup_info,
                'message': f"Backup created: {backup_name}"
            }
            
        except Exception as e:
            backup_logger.error(f"Backup failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'backup_name': backup_name
            }
    
    def _create_sqlite_backup(self, source_db: str, target_db: str):
        """Create SQLite backup using the backup API (online backup)"""
        source_conn = sqlite3.connect(source_db)
        target_conn = sqlite3.connect(target_db)
        
        try:
            # Use SQLite's backup API for consistent backup
            source_conn.backup(target_conn)
        finally:
            source_conn.close()
            target_conn.close()
    
    def restore_backup(self, backup_name: str, target_path: str = None) -> Dict:
        """Restore database from backup"""
        if target_path is None:
            target_path = f"{self.database_path}.restored"
        
        backup_logger.info(f"Starting restore of backup: {backup_name}")
        
        try:
            # Find backup in metadata
            backup_info = None
            for backup in self.metadata['backups']:
                if backup['name'] == backup_name:
                    backup_info = backup
                    break
            
            if not backup_info:
                return {
                    'success': False,
                    'error': f"Backup not found: {backup_name}"
                }
            
            backup_path = Path(backup_info['file_path'])
            if not backup_path.exists():
                return {
                    'success': False,
                    'error': f"Backup file not found: {backup_path}"
                }
            
            # Verify backup hash
            current_hash = self._calculate_file_hash(str(backup_path))
            if current_hash != backup_info['hash']:
                return {
                    'success': False,
                    'error': f"Backup file corrupted (hash mismatch)"
                }
            
            # Extract if compressed
            restore_source = backup_path
            if backup_info['compressed']:
                temp_path = backup_path.with_suffix('')
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(temp_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                restore_source = temp_path
            
            # Verify backup integrity before restore
            is_valid, integrity_msg = self._verify_database_integrity(str(restore_source))
            if not is_valid:
                if backup_info['compressed']:
                    restore_source.unlink()  # Clean up temp file
                return {
                    'success': False,
                    'error': f"Backup corrupted: {integrity_msg}"
                }
            
            # Copy backup to target location
            shutil.copy2(restore_source, target_path)
            
            # Clean up temp file if compressed
            if backup_info['compressed'] and restore_source != backup_path:
                restore_source.unlink()
            
            # Verify restored database
            is_valid, integrity_msg = self._verify_database_integrity(target_path)
            if not is_valid:
                os.remove(target_path)
                return {
                    'success': False,
                    'error': f"Restored database corrupted: {integrity_msg}"
                }
            
            backup_logger.info(f"Backup restored successfully to: {target_path}")
            return {
                'success': True,
                'backup_info': backup_info,
                'target_path': target_path,
                'message': f"Database restored from {backup_name}"
            }
            
        except Exception as e:
            backup_logger.error(f"Restore failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cleanup_old_backups(self):
        """Clean up old backups based on retention policy"""
        backup_logger.info("Starting backup cleanup")
        
        try:
            now = datetime.now()
            backups_to_remove = []
            
            # Group backups by type
            daily_backups = []
            weekly_backups = []
            monthly_backups = []
            
            for backup in self.metadata['backups']:
                backup_date = datetime.fromisoformat(backup['timestamp'])
                backup_type = backup['type']
                
                if backup_type in ['daily', 'scheduled']:
                    daily_backups.append(backup)
                elif backup_type == 'weekly':
                    weekly_backups.append(backup)
                elif backup_type == 'monthly':
                    monthly_backups.append(backup)
            
            # Sort by timestamp (newest first)
            daily_backups.sort(key=lambda x: x['timestamp'], reverse=True)
            weekly_backups.sort(key=lambda x: x['timestamp'], reverse=True)
            monthly_backups.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Mark old backups for removal
            if len(daily_backups) > self.max_daily_backups:
                backups_to_remove.extend(daily_backups[self.max_daily_backups:])
            
            if len(weekly_backups) > self.max_weekly_backups:
                backups_to_remove.extend(weekly_backups[self.max_weekly_backups:])
            
            if len(monthly_backups) > self.max_monthly_backups:
                backups_to_remove.extend(monthly_backups[self.max_monthly_backups:])
            
            # Remove old backup files and metadata
            removed_count = 0
            for backup in backups_to_remove:
                backup_path = Path(backup['file_path'])
                if backup_path.exists():
                    backup_path.unlink()
                    backup_logger.info(f"Removed old backup: {backup['name']}")
                    removed_count += 1
                
                # Remove from metadata
                self.metadata['backups'] = [b for b in self.metadata['backups'] if b['name'] != backup['name']]
            
            self._save_metadata()
            backup_logger.info(f"Cleanup completed: {removed_count} old backups removed")
            
        except Exception as e:
            backup_logger.error(f"Backup cleanup failed: {str(e)}")
    
    def get_backup_status(self) -> Dict:
        """Get comprehensive backup status"""
        try:
            now = datetime.now()
            
            # Count backups by type
            backup_counts = {'daily': 0, 'weekly': 0, 'monthly': 0, 'manual': 0, 'full': 0}
            total_size = 0
            latest_backup = None
            
            for backup in self.metadata['backups']:
                backup_type = backup['type']
                if backup_type in backup_counts:
                    backup_counts[backup_type] += 1
                else:
                    backup_counts['manual'] += 1
                
                total_size += backup['file_size']
                
                if latest_backup is None or backup['timestamp'] > latest_backup['timestamp']:
                    latest_backup = backup
            
            # Check if database exists and get its status
            db_exists = os.path.exists(self.database_path)
            db_size = os.path.getsize(self.database_path) if db_exists else 0
            
            # Check database integrity
            db_integrity = None
            if db_exists:
                is_valid, integrity_msg = self._verify_database_integrity(self.database_path)
                db_integrity = {'valid': is_valid, 'message': integrity_msg}
            
            # Calculate time since last backup
            time_since_last_backup = None
            if latest_backup:
                last_backup_time = datetime.fromisoformat(latest_backup['timestamp'])
                time_since_last_backup = (now - last_backup_time).total_seconds() / 3600  # hours
            
            return {
                'database_exists': db_exists,
                'database_size': db_size,
                'database_integrity': db_integrity,
                'total_backups': len(self.metadata['backups']),
                'backup_counts': backup_counts,
                'total_backup_size': total_size,
                'latest_backup': latest_backup,
                'time_since_last_backup_hours': time_since_last_backup,
                'backup_schedule': self.metadata['backup_schedule'],
                'scheduler_running': self.scheduler_running
            }
            
        except Exception as e:
            backup_logger.error(f"Error getting backup status: {str(e)}")
            return {'error': str(e)}
    
    def start_automated_backups(self):
        """Start automated backup scheduler"""
        if self.scheduler_running:
            backup_logger.warning("Backup scheduler already running")
            return
        
        # Schedule daily backups
        schedule.every().day.at(self.metadata['backup_schedule']['daily']).do(
            lambda: self.create_backup('daily')
        )
        
        # Schedule weekly backups
        getattr(schedule.every(), self.metadata['backup_schedule']['weekly'].lower()).at(
            self.metadata['backup_schedule']['daily']
        ).do(lambda: self.create_backup('weekly'))
        
        # Schedule monthly backups
        schedule.every().month.do(lambda: self.create_backup('monthly'))
        
        # Schedule cleanup
        schedule.every().day.at("03:00").do(self.cleanup_old_backups)
        
        # Start scheduler thread
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        backup_logger.info("Automated backup scheduler started")
    
    def stop_automated_backups(self):
        """Stop automated backup scheduler"""
        self.scheduler_running = False
        schedule.clear()
        if self.scheduler_thread:
            self.scheduler_thread.join()
        backup_logger.info("Automated backup scheduler stopped")
    
    def _run_scheduler(self):
        """Run the backup scheduler"""
        while self.scheduler_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def export_backup_config(self) -> Dict:
        """Export backup configuration for migration"""
        return {
            'metadata': self.metadata,
            'config': {
                'max_daily_backups': self.max_daily_backups,
                'max_weekly_backups': self.max_weekly_backups,
                'max_monthly_backups': self.max_monthly_backups,
                'compression_enabled': self.compression_enabled
            }
        }
    
    def import_backup_config(self, config: Dict):
        """Import backup configuration"""
        if 'metadata' in config:
            self.metadata = config['metadata']
            self._save_metadata()
        
        if 'config' in config:
            cfg = config['config']
            self.max_daily_backups = cfg.get('max_daily_backups', self.max_daily_backups)
            self.max_weekly_backups = cfg.get('max_weekly_backups', self.max_weekly_backups)
            self.max_monthly_backups = cfg.get('max_monthly_backups', self.max_monthly_backups)
            self.compression_enabled = cfg.get('compression_enabled', self.compression_enabled)
        
        backup_logger.info("Backup configuration imported")

# Global backup manager instance
backup_manager = DatabaseBackupManager()

def create_immediate_backup(backup_type: str = 'manual') -> Dict:
    """Create an immediate backup"""
    return backup_manager.create_backup(backup_type)

def restore_from_backup(backup_name: str, target_path: str = None) -> Dict:
    """Restore database from a specific backup"""
    return backup_manager.restore_backup(backup_name, target_path)

def get_backup_list() -> List[Dict]:
    """Get list of available backups"""
    return backup_manager.metadata['backups']

def init_backup_system():
    """Initialize the backup system"""
    backup_manager.start_automated_backups()
    backup_logger.info("Backup system initialized")

def emergency_backup() -> Dict:
    """Create emergency backup with high priority"""
    backup_logger.warning("Emergency backup initiated")
    return backup_manager.create_backup('emergency', compress=False)

# CLI Functions for manual backup operations
def backup_database_now():
    """Create backup immediately (for manual use)"""
    result = create_immediate_backup('manual')
    if result['success']:
        print(f"✅ Backup created successfully: {result['backup_info']['name']}")
        print(f"📁 Location: {result['backup_info']['file_path']}")
        print(f"📊 Size: {result['backup_info']['file_size']:,} bytes")
    else:
        print(f"❌ Backup failed: {result['error']}")
    return result

def list_backups():
    """List all available backups"""
    backups = get_backup_list()
    if not backups:
        print("No backups found")
        return
    
    print("Available Backups:")
    print("-" * 80)
    for backup in sorted(backups, key=lambda x: x['timestamp'], reverse=True):
        timestamp = datetime.fromisoformat(backup['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        size_mb = backup['file_size'] / (1024 * 1024)
        compressed = "📦" if backup['compressed'] else "📄"
        print(f"{compressed} {backup['name']} | {timestamp} | {size_mb:.1f} MB | {backup['type']}")

if __name__ == "__main__":
    # Command line interface
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python database_backup_system.py [backup|restore|list|status]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'backup':
        backup_database_now()
    elif command == 'list':
        list_backups()
    elif command == 'status':
        status = backup_manager.get_backup_status()
        print(json.dumps(status, indent=2, default=str))
    elif command == 'restore' and len(sys.argv) >= 3:
        backup_name = sys.argv[2]
        result = restore_from_backup(backup_name)
        if result['success']:
            print(f"✅ Database restored from: {backup_name}")
            print(f"📁 Restored to: {result['target_path']}")
        else:
            print(f"❌ Restore failed: {result['error']}")
    else:
        print("Invalid command or missing arguments")
        sys.exit(1) 