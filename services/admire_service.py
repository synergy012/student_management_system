"""
Admire Billing System Integration Service

This service handles integration with the Admire billing system for student payment processing.
Based on common billing API patterns and your existing codebase structure.
"""

import requests
import json
from datetime import datetime
from typing import Dict, Optional, Any
from flask import current_app
from models import Student, FinancialRecord, db


class AdmireService:
    """Service class for Admire billing system integration"""
    
    def __init__(self):
        self.base_url = current_app.config.get('ADMIRE_API_URL', 'https://api.admire.example.com')
        self.api_key = current_app.config.get('ADMIRE_API_KEY')
        self.api_secret = current_app.config.get('ADMIRE_API_SECRET')
        self.environment = current_app.config.get('ADMIRE_ENVIRONMENT', 'sandbox')
        
        # Common headers for API requests
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'X-Admire-Environment': self.environment
        }
    
    def validate_config(self) -> bool:
        """Validate that required configuration is present"""
        required_config = ['ADMIRE_API_URL', 'ADMIRE_API_KEY', 'ADMIRE_API_SECRET']
        for config_key in required_config:
            if not current_app.config.get(config_key):
                current_app.logger.error(f"Missing required Admire configuration: {config_key}")
                return False
        return True
    
    def create_student_account(self, student: Student, academic_year_id: int) -> Dict[str, Any]:
        """
        Create a student account in Admire billing system
        
        Args:
            student: Student model instance
            academic_year_id: Academic year ID for the billing period
            
        Returns:
            Dict containing success status and account details
        """
        try:
            if not self.validate_config():
                return {
                    'success': False,
                    'error': 'Admire API configuration is incomplete'
                }
            
            # Prepare student data for Admire API
            student_data = {
                'student_id': student.id,
                'first_name': student.student_first_name,
                'last_name': student.student_last_name,
                'full_name': student.student_name,
                'email': student.email,
                'phone': student.phone_number,
                'division': student.division,
                'academic_year_id': academic_year_id,
                'enrollment_status': student.enrollment_status_current_year,
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Make API request to create student account
            response = requests.post(
                f"{self.base_url}/students",
                json=student_data,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 201:
                admire_data = response.json()
                current_app.logger.info(f"Successfully created Admire account for student {student.id}")
                
                return {
                    'success': True,
                    'account_number': admire_data.get('account_number'),
                    'account_id': admire_data.get('account_id'),
                    'billing_url': admire_data.get('billing_url'),
                    'payment_methods': admire_data.get('payment_methods', [])
                }
            else:
                error_message = f"Failed to create Admire account: {response.status_code} - {response.text}"
                current_app.logger.error(error_message)
                return {
                    'success': False,
                    'error': error_message
                }
                
        except requests.exceptions.RequestException as e:
            error_message = f"Network error creating Admire account: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }
        except Exception as e:
            error_message = f"Unexpected error creating Admire account: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }
    
    def setup_student_billing(self, student_id: str, financial_record_id: int) -> Dict[str, Any]:
        """
        Set up billing for a student in Admire system
        
        Args:
            student_id: Student ID
            financial_record_id: Financial record ID
            
        Returns:
            Dict containing setup status and details
        """
        try:
            student = Student.query.get(student_id)
            financial_record = FinancialRecord.query.get(financial_record_id)
            
            if not student or not financial_record:
                return {
                    'success': False,
                    'error': 'Student or financial record not found'
                }
            
            # Create or update student account in Admire
            account_result = self.create_student_account(student, financial_record.academic_year_id)
            
            if account_result['success']:
                # Update financial record with Admire details
                financial_record.admire_charges_setup = True
                financial_record.admire_charges_setup_date = datetime.utcnow()
                financial_record.admire_account_number = account_result.get('account_number')
                
                db.session.commit()
                
                current_app.logger.info(f"Successfully set up Admire billing for student {student_id}")
                
                return {
                    'success': True,
                    'account_number': account_result.get('account_number'),
                    'billing_url': account_result.get('billing_url'),
                    'message': 'Admire billing setup completed successfully'
                }
            else:
                return account_result
                
        except Exception as e:
            db.session.rollback()
            error_message = f"Error setting up Admire billing: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }
    
    def get_student_billing_status(self, account_number: str) -> Dict[str, Any]:
        """
        Get billing status for a student from Admire
        
        Args:
            account_number: Student's Admire account number
            
        Returns:
            Dict containing billing status and details
        """
        try:
            if not self.validate_config():
                return {
                    'success': False,
                    'error': 'Admire API configuration is incomplete'
                }
            
            response = requests.get(
                f"{self.base_url}/students/{account_number}/billing-status",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                billing_data = response.json()
                return {
                    'success': True,
                    'account_number': account_number,
                    'balance': billing_data.get('balance', 0),
                    'payment_status': billing_data.get('payment_status'),
                    'last_payment_date': billing_data.get('last_payment_date'),
                    'payment_methods': billing_data.get('payment_methods', [])
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to get billing status: {response.status_code}"
                }
                
        except Exception as e:
            error_message = f"Error getting billing status: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }
    
    def sync_payment_data(self, account_number: str) -> Dict[str, Any]:
        """
        Sync payment data from Admire system
        
        Args:
            account_number: Student's Admire account number
            
        Returns:
            Dict containing sync status and payment data
        """
        try:
            if not self.validate_config():
                return {
                    'success': False,
                    'error': 'Admire API configuration is incomplete'
                }
            
            response = requests.get(
                f"{self.base_url}/students/{account_number}/payments",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_data = response.json()
                return {
                    'success': True,
                    'payments': payment_data.get('payments', []),
                    'total_paid': payment_data.get('total_paid', 0),
                    'pending_payments': payment_data.get('pending_payments', [])
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to sync payment data: {response.status_code}"
                }
                
        except Exception as e:
            error_message = f"Error syncing payment data: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }
    
    def generate_payment_link(self, account_number: str, amount: float = None) -> Dict[str, Any]:
        """
        Generate a payment link for a student
        
        Args:
            account_number: Student's Admire account number
            amount: Optional specific amount (if None, uses account balance)
            
        Returns:
            Dict containing payment link and details
        """
        try:
            if not self.validate_config():
                return {
                    'success': False,
                    'error': 'Admire API configuration is incomplete'
                }
            
            payment_data = {
                'account_number': account_number,
                'amount': amount,
                'return_url': f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/financial/payment-success",
                'cancel_url': f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/financial/payment-cancelled"
            }
            
            response = requests.post(
                f"{self.base_url}/payments/create-link",
                json=payment_data,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                link_data = response.json()
                return {
                    'success': True,
                    'payment_link': link_data.get('payment_link'),
                    'expires_at': link_data.get('expires_at'),
                    'amount': link_data.get('amount')
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to generate payment link: {response.status_code}"
                }
                
        except Exception as e:
            error_message = f"Error generating payment link: {str(e)}"
            current_app.logger.error(error_message)
            return {
                'success': False,
                'error': error_message
            }