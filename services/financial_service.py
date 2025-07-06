"""
Financial Service Classes
Handles business logic for financial operations
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from flask import current_app
from models import (
    Student, FinancialRecord, TuitionRecord, FinancialAidApplication,
    TuitionContract, AcademicYear, db, StudentTuitionComponent, 
    TuitionComponent, DivisionFinancialConfig
)
import logging

logger = logging.getLogger(__name__)

class FinancialService:
    """Service class for financial operations"""
    
    def __init__(self):
        self.logger = logger
    
    def get_or_create_financial_record(self, student_id: int, academic_year_id: int) -> FinancialRecord:
        """Get or create a financial record for a student and academic year"""
        try:
            # Try to find existing record
            financial_record = FinancialRecord.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
            if not financial_record:
                # Create new record
                financial_record = FinancialRecord(
                    student_id=student_id,
                    academic_year_id=academic_year_id,
                    financial_aid_required=False,
                    tuition_type='Not Set'
                )
                db.session.add(financial_record)
                db.session.commit()
                
                self.logger.info(f"Created new financial record for student {student_id}, year {academic_year_id}")
            
            return financial_record
            
        except Exception as e:
            self.logger.error(f"Error creating financial record: {str(e)}")
            raise
    
    def calculate_tuition_amount(self, student_id: int, academic_year_id: int) -> Decimal:
        """Calculate total tuition amount for a student"""
        try:
            # Get student tuition components
            components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).all()
            
            if not components:
                return Decimal('0.00')
            
            total_amount = Decimal('0.00')
            for component in components:
                if component.amount:
                    total_amount += component.amount
            
            return total_amount
            
        except Exception as e:
            self.logger.error(f"Error calculating tuition: {str(e)}")
            raise
    
    def determine_tuition_type(self, student_id: int, academic_year_id: int) -> str:
        """Determine tuition type based on components"""
        try:
            components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).all()
            
            if not components:
                return 'Not Set'
            
            total_amount = sum(component.amount for component in components if component.amount)
            
            # Logic for determining tuition type
            if total_amount == 0:
                return 'Full Scholarship'
            elif total_amount < 15000:
                return 'Partial Scholarship'
            elif any(comp.tuition_component.component_name == 'Room' for comp in components):
                return 'Tuition + Room'
            elif any(comp.tuition_component.component_name == 'Board' for comp in components):
                return 'Tuition + Board'
            else:
                return 'Tuition Only'
                
        except Exception as e:
            self.logger.error(f"Error determining tuition type: {str(e)}")
            return 'Not Set'
    
    def update_financial_record(self, record_id: int, data: Dict) -> bool:
        """Update a financial record"""
        try:
            record = FinancialRecord.query.get(record_id)
            if not record:
                return False
            
            # Update fields
            for field, value in data.items():
                if hasattr(record, field):
                    setattr(record, field, value)
            
            record.updated_at = datetime.utcnow()
            db.session.commit()
            
            self.logger.info(f"Updated financial record {record_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating financial record: {str(e)}")
            db.session.rollback()
            return False
    
    def get_student_financial_summary(self, student_id: int, academic_year_id: int) -> Dict:
        """Get comprehensive financial summary for a student"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return {}
            
            # Get financial record
            financial_record = self.get_or_create_financial_record(student_id, academic_year_id)
            
            # Get tuition components
            components = StudentTuitionComponent.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).all()
            
            # Calculate totals
            total_tuition = self.calculate_tuition_amount(student_id, academic_year_id)
            tuition_type = self.determine_tuition_type(student_id, academic_year_id)
            
            # Get financial aid
            financial_aid = FinancialAidApplication.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
            # Get contracts
            contracts = TuitionContract.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).all()
            
            return {
                'student': {
                    'id': student.id,
                    'name': student.student_name,
                    'division': student.division,
                    'status': student.status
                },
                'financial_record': {
                    'id': financial_record.id,
                    'tuition_type': tuition_type,
                    'financial_aid_required': financial_record.financial_aid_required,
                    'financial_aid_form_received': financial_record.financial_aid_form_received,
                    'enhanced_contract_signed': financial_record.enhanced_contract_signed,
                    'enrollment_contract_received': financial_record.enrollment_contract_received,
                    'admire_setup_complete': financial_record.admire_setup_complete
                },
                'tuition': {
                    'total_amount': float(total_tuition),
                    'components': [
                        {
                            'name': comp.tuition_component.component_name,
                            'amount': float(comp.amount) if comp.amount else 0,
                            'description': comp.tuition_component.description
                        } for comp in components
                    ]
                },
                'financial_aid': {
                    'application_id': financial_aid.id if financial_aid else None,
                    'status': financial_aid.application_status if financial_aid else 'Not Applied',
                    'requested_amount': float(financial_aid.requested_aid_amount) if financial_aid and financial_aid.requested_aid_amount else 0,
                    'awarded_amount': float(financial_aid.award_amount) if financial_aid and financial_aid.award_amount else 0
                },
                'contracts': [
                    {
                        'id': contract.id,
                        'status': contract.contract_status,
                        'signing_status': contract.opensign_status,
                        'generated_date': contract.generated_date.isoformat() if contract.generated_date else None,
                        'sent_date': contract.sent_date.isoformat() if contract.sent_date else None
                    } for contract in contracts
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting financial summary: {str(e)}")
            return {}
    
    def get_division_financial_stats(self, division: str, academic_year_id: int) -> Dict:
        """Get financial statistics for a division"""
        try:
            # Get all students in division
            students = Student.query.filter_by(division=division).all()
            student_ids = [s.id for s in students]
            
            # Get financial records
            financial_records = FinancialRecord.query.filter(
                FinancialRecord.student_id.in_(student_ids),
                FinancialRecord.academic_year_id == academic_year_id
            ).all()
            
            # Get contracts
            contracts = TuitionContract.query.filter(
                TuitionContract.student_id.in_(student_ids),
                TuitionContract.academic_year_id == academic_year_id
            ).all()
            
            # Get financial aid applications
            aid_applications = FinancialAidApplication.query.filter(
                FinancialAidApplication.student_id.in_(student_ids),
                FinancialAidApplication.academic_year_id == academic_year_id
            ).all()
            
            # Calculate statistics
            stats = {
                'total_students': len(students),
                'financial_records': len(financial_records),
                'contracts': {
                    'total': len(contracts),
                    'signed': len([c for c in contracts if c.opensign_status == 'completed']),
                    'pending': len([c for c in contracts if c.opensign_status == 'pending']),
                    'generated': len([c for c in contracts if c.generated_date])
                },
                'financial_aid': {
                    'applications': len(aid_applications),
                    'approved': len([a for a in aid_applications if a.application_status == 'Approved']),
                    'pending': len([a for a in aid_applications if a.application_status == 'Submitted']),
                    'total_awarded': sum(float(a.award_amount or 0) for a in aid_applications if a.application_status == 'Approved')
                },
                'completion_rates': {
                    'contracts': (len([c for c in contracts if c.opensign_status == 'completed']) / len(contracts) * 100) if contracts else 0,
                    'financial_aid': (len([a for a in aid_applications if a.application_status == 'Approved']) / len(aid_applications) * 100) if aid_applications else 0
                }
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting division stats: {str(e)}")
            return {}

class ContractService:
    """Service class for contract operations"""
    
    def __init__(self):
        self.logger = logger
    
    def create_contract(self, student_id: int, academic_year_id: int, contract_data: Dict) -> Optional[TuitionContract]:
        """Create a new tuition contract"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return None
            
            # Create contract
            contract = TuitionContract(
                student_id=student_id,
                academic_year_id=academic_year_id,
                division=student.division,
                tuition_amount=contract_data.get('tuition_amount', 0),
                final_tuition_amount=contract_data.get('final_tuition_amount', 0),
                contract_status='Generated',
                opensign_status='not_sent',
                generated_date=datetime.utcnow()
            )
            
            # Set additional fields
            for field, value in contract_data.items():
                if hasattr(contract, field):
                    setattr(contract, field, value)
            
            db.session.add(contract)
            db.session.commit()
            
            self.logger.info(f"Created contract for student {student_id}")
            return contract
            
        except Exception as e:
            self.logger.error(f"Error creating contract: {str(e)}")
            db.session.rollback()
            return None
    
    def update_contract_status(self, contract_id: int, status: str, opensign_status: str = None) -> bool:
        """Update contract status"""
        try:
            contract = TuitionContract.query.get(contract_id)
            if not contract:
                return False
            
            contract.contract_status = status
            if opensign_status:
                contract.opensign_status = opensign_status
            
            # Update relevant dates
            if status == 'Sent':
                contract.sent_date = datetime.utcnow()
            elif status == 'Signed':
                contract.signed_date = datetime.utcnow()
            
            db.session.commit()
            
            self.logger.info(f"Updated contract {contract_id} status to {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating contract status: {str(e)}")
            db.session.rollback()
            return False
    
    def get_contract_by_student(self, student_id: int, academic_year_id: int) -> Optional[TuitionContract]:
        """Get contract for a student and academic year"""
        try:
            return TuitionContract.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
        except Exception as e:
            self.logger.error(f"Error getting contract: {str(e)}")
            return None

class FinancialAidService:
    """Service class for financial aid operations"""
    
    def __init__(self):
        self.logger = logger
    
    def create_application(self, student_id: int, academic_year_id: int, application_data: Dict) -> Optional[FinancialAidApplication]:
        """Create a new financial aid application"""
        try:
            student = Student.query.get(student_id)
            if not student:
                return None
            
            # Create application
            application = FinancialAidApplication(
                student_id=student_id,
                academic_year_id=academic_year_id,
                division=student.division,
                application_status='Draft',
                application_date=datetime.utcnow()
            )
            
            # Set application data
            for field, value in application_data.items():
                if hasattr(application, field):
                    setattr(application, field, value)
            
            db.session.add(application)
            db.session.commit()
            
            self.logger.info(f"Created financial aid application for student {student_id}")
            return application
            
        except Exception as e:
            self.logger.error(f"Error creating financial aid application: {str(e)}")
            db.session.rollback()
            return None
    
    def update_application_status(self, application_id: int, status: str, award_amount: Decimal = None) -> bool:
        """Update financial aid application status"""
        try:
            application = FinancialAidApplication.query.get(application_id)
            if not application:
                return False
            
            application.application_status = status
            if award_amount is not None:
                application.award_amount = award_amount
            
            # Update relevant dates
            if status == 'Approved':
                application.reviewed_date = datetime.utcnow()
            elif status == 'Denied':
                application.reviewed_date = datetime.utcnow()
            
            db.session.commit()
            
            self.logger.info(f"Updated financial aid application {application_id} status to {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating financial aid status: {str(e)}")
            db.session.rollback()
            return False
    
    def get_application_by_student(self, student_id: int, academic_year_id: int) -> Optional[FinancialAidApplication]:
        """Get financial aid application for a student and academic year"""
        try:
            return FinancialAidApplication.query.filter_by(
                student_id=student_id,
                academic_year_id=academic_year_id
            ).first()
            
        except Exception as e:
            self.logger.error(f"Error getting financial aid application: {str(e)}")
            return None
