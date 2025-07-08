# Route Mapping Documentation

## Blueprint Naming Conventions

### Current Blueprint Names
- **Core System**: `core`
- **Students**: `students` 
- **Applications**: `applications`
- **Academic**: `academic`
- **Financial**: `financial` (main blueprint)
  - `financial_core` (sub-blueprint)
  - `financial_tuition` (sub-blueprint)
  - `financial_contracts` (sub-blueprint)
  - `financial_aid` (sub-blueprint)
  - `financial_documents` (sub-blueprint)
  - `financial_divisions` (sub-blueprint)
- **Kollel**: `kollel`
- **Reports**: `reports`
- **Settings**: `settings`
- **Files**: `files`
- **Dormitories**: `dormitories`
- **Enrollment**: `enrollment`
- **Enrollment Email**: `enrollment_email`
- **Email Templates**: `email_templates`
- **PDF Templates**: `pdf_templates`
- **Secure Forms**: `secure_forms`
- **Tuition Components**: `tuition_components`
- **Academic Year Transition**: `academic_year_transition`
- **Webhooks**: `webhooks`
- **Monitoring**: `monitoring` (URL prefix: `/monitoring`)
- **Backup**: `backup` (URL prefix: `/backup`)

### Naming Convention Analysis
- **Consistent (Singular)**: core, students, applications, academic, kollel, reports, settings, files, dormitories, enrollment, webhooks
- **Compound Names**: enrollment_email, email_templates, pdf_templates, secure_forms, tuition_components, academic_year_transition
- **Financial Sub-blueprints**: All use `financial_` prefix consistently

## Route Patterns

### Core Routes
- `core.index` → `/`

### Student Management Routes
- `students.view_students` → `/students`
- `students.student_details` → `/students/<student_id>`
- `students.edit_student` → `/students/<student_id>/edit`
- `students.create_student` → `/students/new`
- `students.view_uploaded_contract` → `/students/<student_id>/view-uploaded-contract`

### Financial Routes (Complex Sub-blueprint Structure)
- `financial.financial_core.financial_dashboard` → `/financial`
- `financial.financial_core.student_financial` → `/financial/student/<student_id>`
- `financial.financial_aid.division_financial_aid` → `/divisions/<division>/financial-aid`
- `financial.financial_divisions.division_tuition_contracts` → `/divisions/<division>/tuition-contracts`
- `financial.financial_divisions.division_financial_config` → `/divisions/<division>/config`
- `financial.financial_contracts.generate_tuition_contract` → `/api/students/<student_id>/generate-tuition-contract`

### Academic Routes
- `academic.academic_dashboard` → `/academic`
- `academic.shiurim_list` → `/shiurim`
- `academic.attendance_dashboard` → `/attendance`
- `academic.matriculation_dashboard` → `/matriculation`

### Settings Routes
- `settings.settings_page` → `/settings`
- `settings.upload_division_form` → `/upload-division-form/<division>`
- `settings.download_division_form` → `/download-division-form/<division>/<form_type>`
- `settings.get_dropbox_sign_quota` → `/dropbox-sign-quota`

### Dormitories Routes
- `dormitories.dormitory_dashboard` → `/dormitories`
- `dormitories.dormitory_map` → `/dormitories/map`

### Reports Routes
- `reports.reports_dashboard` → `/reports`
- `reports.report_builder` → `/reports/builder`
- `reports.download_report` → `/api/reports/download/<int:execution_id>`

### Template Management Routes
- `pdf_templates.template_manager` → `/pdf-templates`
- `email_templates.template_manager` → `/email-templates`

### Secure Forms Routes
- `secure_forms.upload_form` → `/secure-upload/<token>`
- `secure_forms.download_form` → `/download-form/<token>`
- `secure_forms.admin_secure_forms` → `/admin/secure-forms`
- `secure_forms.admin_form_uploads` → `/admin/form-uploads`

### Kollel Routes
- `kollel.kollel_dashboard` → `/kollel`
- `kollel.kollel_students` → `/kollel/students`
- `kollel.kollel_settings` → `/kollel/settings`
- `kollel.edit_kollel_student` → `/kollel/student/<kollel_student_id>/edit`

### File Management Routes
- `files.view_attachment` → `/attachments/<path:filename>/view`
- `files.serve_attachment` → `/attachments/<path:filename>`
- `files.download_file` → `/download/<path:filename>`

### Monitoring Routes (URL Prefix: `/monitoring`)
- `monitoring.monitoring_dashboard` → `/monitoring/`
- `monitoring.monitoring_logs` → `/monitoring/logs`

### Backup Routes (URL Prefix: `/backup`)
- `backup.backup_dashboard` → `/backup/`

## Route Consistency Issues Fixed

### Previously Fixed Issues:
1. **auth.users** → **auth.users_list** ✅
2. **settings.settings** → **settings.settings_page** ✅
3. **reports.reports_builder** → **reports.report_builder** ✅
4. **Financial sub-blueprint routes** → Properly namespaced ✅
5. **Hardcoded URLs** → Converted to `url_for` calls ✅

### Current Status:
- All routes are properly defined and accessible
- No missing routes detected
- Blueprint naming follows consistent patterns within each module
- Financial sub-blueprints use proper namespacing

## Recommendations for Standardization

### Option 1: Keep Current Naming (Recommended)
- Most blueprints already follow reasonable conventions
- Financial sub-blueprints are properly namespaced
- Changes would require extensive template updates

### Option 2: Full Standardization
- Convert all to singular names where possible
- Standardize compound names with underscores
- Would require significant refactoring

## Best Practices Implemented

1. **URL Generation**: All templates use `url_for()` instead of hardcoded URLs
2. **Blueprint Namespacing**: Financial module uses proper sub-blueprint structure
3. **Route Parameters**: Consistent parameter naming across blueprints
4. **API Consistency**: API routes use `/api/` prefix consistently
5. **Admin Routes**: Admin functionality uses `/admin/` prefix

---

*Last Updated: $(date)*
*Status: All routes functional and properly mapped* 