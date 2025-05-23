# Student Management System

A comprehensive web application for managing student records, courses, enrollments, and applications. Built with Flask and SQLAlchemy.

## Features

- User Authentication (Admin/Staff login)
- Student Management
- Course Management
- Application Processing
- Custom Field Management
- File Upload Support
- Form Submission Handling

## Tech Stack

- Python 3.13
- Flask 3.0.0
- SQLAlchemy 1.4.50
- Flask-SQLAlchemy 3.0.2
- Flask-Login 0.6.3
- Flask-Migrate 4.0.5
- Other dependencies listed in requirements.txt

## Setup Instructions

1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd student_management_system
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Unix or MacOS:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the root directory with:
   ```
   SECRET_KEY=your-secret-key
   DATABASE_URL=sqlite:///student_management.db
   FORMS_WEBHOOK_SECRET=your-webhook-secret
   ```

5. Initialize the database:
   ```bash
   flask db upgrade
   ```

6. Run the application:
   ```bash
   python app.py
   ```

   Or use the provided batch file (Windows):
   ```bash
   fix_and_run.bat
   ```

## First Time Setup

When you first run the application, the first user to register will automatically become an admin user.

## Development

To modify the application structure or database schema:

1. Make your changes to the models
2. Generate migrations:
   ```bash
   flask db migrate -m "Description of changes"
   ```
3. Apply migrations:
   ```bash
   flask db upgrade
   ```

## Security Notes

- Never commit `.env` files or any sensitive information
- Keep your `SECRET_KEY` and `FORMS_WEBHOOK_SECRET` secure
- Regularly update dependencies for security patches

## License

[Your chosen license] 