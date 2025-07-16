# Admire Billing System Integration

## Overview

This document describes the integration between the Student Management System and the Admire billing system. The integration handles student account creation, billing setup, and payment processing.

## Configuration

### Environment Variables

Add the following environment variables to your system:

```bash
# Admire API Configuration
ADMIRE_API_URL=https://api.admire.example.com
ADMIRE_API_KEY=your_api_key_here
ADMIRE_API_SECRET=your_api_secret_here
ADMIRE_ENVIRONMENT=sandbox  # or 'production'
ADMIRE_WEBHOOK_SECRET=your_webhook_secret_here
```

### Development/Testing

For development, the system defaults to sandbox mode. Update `ADMIRE_ENVIRONMENT=production` for live usage.

## Features Implemented

### 1. Student Account Creation
- Automatically creates student accounts in Admire billing system
- Syncs student data (name, email, phone, division, enrollment status)
- Generates unique account numbers for tracking

### 2. Billing Setup Workflow
- Integrated into the financial workflow as a required step
- Appears between "Contract Signed" and "Finalized" steps
- Provides setup and completion tracking

### 3. API Endpoints

#### Setup Admire Billing
```
POST /api/students/<student_id>/setup-admire-billing
```
- Sets up billing for a student in Admire system
- Creates or updates financial record
- Returns account number and billing URL

#### Mark Admire Complete
```
POST /api/students/<student_id>/mark-admire-complete
```
- Manually marks Admire setup as complete
- Updates financial record with completion timestamp

#### Get Admire Status
```
GET /api/students/<student_id>/admire-status?academic_year_id=<year_id>
```
- Returns current Admire setup status
- Includes account number and setup date
- Optional live status from Admire API

### 4. UI Components

#### Financial Dashboard
- Shows Admire setup status for all students
- Green checkmark when setup is complete
- Displays account number if available

#### Student Financial Page
- "Setup Admire" button with loading states
- "Mark Complete" button for manual completion
- Integrated into workflow progress tracking

## Service Class: AdmireService

### Main Methods

#### `create_student_account(student, academic_year_id)`
Creates a new student account in Admire system.

#### `setup_student_billing(student_id, financial_record_id)`
Complete billing setup workflow for a student.

#### `get_student_billing_status(account_number)`
Retrieves current billing status from Admire.

#### `sync_payment_data(account_number)`
Syncs payment data from Admire system.

#### `generate_payment_link(account_number, amount=None)`
Generates payment links for students.

## Database Fields

### FinancialRecord Model
- `admire_charges_setup`: Boolean flag for setup completion
- `admire_charges_setup_date`: Timestamp of setup completion
- `admire_account_number`: Student's Admire account number

## Error Handling

The integration includes comprehensive error handling:
- Configuration validation
- Network timeout handling
- API response validation
- Database transaction rollback on errors
- Detailed logging for debugging

## Testing

### Manual Testing Steps

1. Set environment variables for sandbox mode
2. Navigate to student financial page
3. Click "Setup Admire" button
4. Verify account creation and status update
5. Check financial dashboard for status display

### API Testing

Use the provided API endpoints to test integration:

```bash
# Test account creation
curl -X POST \
  http://localhost:5000/api/students/STUDENT_ID/setup-admire-billing \
  -H "Content-Type: application/json" \
  -d '{"academic_year_id": 1}'

# Test status check
curl -X GET \
  http://localhost:5000/api/students/STUDENT_ID/admire-status?academic_year_id=1
```

## Production Deployment

### Prerequisites
1. Obtain Admire API credentials
2. Configure production environment variables
3. Test in sandbox mode first
4. Update `ADMIRE_ENVIRONMENT=production`

### Monitoring
- Monitor application logs for Admire API errors
- Check financial dashboard for failed setups
- Verify account numbers are being generated correctly

## Common Issues

### Configuration Errors
- Missing environment variables: Check config validation
- Invalid API credentials: Verify with Admire support
- Network timeout: Increase timeout values if needed

### API Errors
- 401 Unauthorized: Check API key and secret
- 429 Rate Limited: Implement retry logic
- 500 Server Error: Contact Admire support

## Future Enhancements

1. **Webhook Integration**: Handle payment notifications from Admire
2. **Bulk Operations**: Setup multiple students at once
3. **Payment Sync**: Automated payment data synchronization
4. **Enhanced UI**: Payment history display and management
5. **Reporting**: Integration with financial reporting system

## Support

For issues with the Admire integration:
1. Check application logs for error details
2. Verify configuration settings
3. Test API endpoints directly
4. Contact Admire support for API issues