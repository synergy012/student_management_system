"""
Common helper functions used across the application
"""
from datetime import datetime
import hmac
import hashlib
from flask import current_app


def parse_date(date_str):
    """Parse date string in various formats"""
    if not date_str or date_str.strip() == '':
        return None
    try:
        # Try different date formats
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None
    except Exception:
        return None


def parse_decimal(value):
    """Parse a numeric field value, returning float if possible."""
    if value and str(value).strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def verify_webhook_signature(request_data, signature, secret):
    """Verify webhook signature using HMAC"""
    computed_signature = hmac.new(
        secret.encode(),
        request_data,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_signature, signature) 