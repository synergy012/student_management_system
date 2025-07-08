/**
 * Email Confirmation Dialog System
 * Provides a unified way to confirm email recipients before sending
 */

class EmailConfirmationDialog {
    constructor() {
        this.modalId = 'emailConfirmationModal';
        this.currentCallback = null;
        this.createModal();
    }

    createModal() {
        // Remove existing modal if present
        const existingModal = document.getElementById(this.modalId);
        if (existingModal) {
            existingModal.remove();
        }

        const modalHtml = `
            <div class="modal fade" id="${this.modalId}" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-envelope me-2"></i>Confirm Email Recipients
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="alert alert-info">
                                <i class="fas fa-info-circle me-2"></i>
                                <span id="emailTypeDescription">Please confirm the email recipients</span>
                            </div>
                            
                            <div class="card">
                                <div class="card-header">
                                    <h6 class="mb-0">
                                        <i class="fas fa-users me-2"></i>Email Recipients
                                    </h6>
                                </div>
                                <div class="card-body">
                                    <div class="row" id="recipientOptions">
                                        <!-- Recipient checkboxes will be populated here -->
                                    </div>
                                    <div class="mt-3">
                                        <small class="text-muted">
                                            <i class="fas fa-info-circle me-1"></i>
                                            Select who should receive this email. At least one recipient must be selected.
                                        </small>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="card mt-3" id="signingOptionsCard" style="display: none;">
                                <div class="card-header">
                                    <h6 class="mb-0">
                                        <i class="fas fa-signature me-2"></i>Contract Signing Options
                                    </h6>
                                </div>
                                <div class="card-body">
                                    <div class="alert alert-info">
                                        <i class="fas fa-info-circle me-2"></i>
                                        Choose how families can sign and return the contract
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="signingMethod" 
                                                       id="digital_only" value="digital"
                                                       onchange="emailConfirmationDialog.updateSigningPreview()">
                                                <label class="form-check-label" for="digital_only">
                                                    <i class="fas fa-signature text-success me-1"></i>
                                                    <strong>Digital Signature Only</strong>
                                                    <div class="small text-muted">Secure electronic signing via OpenSign</div>
                                                </label>
                                            </div>
                                        </div>
                                        
                                        <div class="col-md-6">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="signingMethod" 
                                                       id="print_upload" value="upload" checked
                                                       onchange="emailConfirmationDialog.updateSigningPreview()">
                                                <label class="form-check-label" for="print_upload">
                                                    <i class="fas fa-upload text-primary me-1"></i>
                                                    <strong>Print & Upload</strong>
                                                    <div class="small text-muted">Print, sign, and upload via secure link</div>
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="row mt-3">
                                        <div class="col-md-6">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="signingMethod" 
                                                       id="hybrid_both" value="hybrid"
                                                       onchange="emailConfirmationDialog.updateSigningPreview()">
                                                <label class="form-check-label" for="hybrid_both">
                                                    <i class="fas fa-layer-group text-warning me-1"></i>
                                                    <strong>Both Options Available</strong>
                                                    <div class="small text-muted">Let families choose digital OR print/upload</div>
                                                </label>
                                            </div>
                                        </div>
                                        
                                        <div class="col-md-6">
                                            <div class="form-group">
                                                <label for="expirationHours" class="form-label small">Link Expiration (Hours)</label>
                                                <select class="form-select form-select-sm" id="expirationHours">
                                                    <option value="24">24 Hours</option>
                                                    <option value="48">48 Hours</option>
                                                    <option value="72" selected>72 Hours (3 days)</option>
                                                    <option value="168">1 Week</option>
                                                    <option value="336">2 Weeks</option>
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div id="signingMethodPreview" class="mt-3 p-3 bg-light rounded">
                                        <div class="small text-muted">
                                            <i class="fas fa-eye me-1"></i>
                                            With <strong>Print & Upload</strong> selected, families will receive an email with a secure link to upload their signed contract.
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="card mt-3">
                                <div class="card-header">
                                    <h6 class="mb-0">
                                        <i class="fas fa-eye me-2"></i>Email Preview
                                    </h6>
                                </div>
                                <div class="card-body">
                                    <div id="emailPreview">
                                        <div class="text-center text-muted">
                                            <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                                            Loading email preview...
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times me-2"></i>Cancel
                            </button>
                            <button type="button" class="btn btn-primary" id="confirmSendEmail">
                                <i class="fas fa-paper-plane me-2"></i>Send Email
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Add event listener for send button
        document.getElementById('confirmSendEmail').addEventListener('click', () => {
            this.handleSendConfirmation();
        });
    }

    /**
     * Initialize TinyMCE for the email body editor
     */
    initializeEmailEditor() {
        if (typeof tinymce !== 'undefined') {
            // Remove any existing editor instance
            if (tinymce.get('editableBody')) {
                tinymce.get('editableBody').remove();
            }
            
            setTimeout(() => {
                if (document.getElementById('editableBody')) {
                    tinymce.init({
                        selector: '#editableBody',
                        height: 300,
                        menubar: false,
                        plugins: [
                            'advlist', 'autolink', 'lists', 'link', 'charmap', 'preview',
                            'anchor', 'searchreplace', 'visualblocks', 'code',
                            'insertdatetime', 'media', 'table', 'help', 'wordcount'
                        ],
                        toolbar: 'undo redo | blocks | ' +
                            'bold italic forecolor backcolor | alignleft aligncenter ' +
                            'alignright alignjustify | bullist numlist outdent indent | ' +
                            'removeformat | help',
                        content_style: 'body { font-family: Arial, sans-serif; font-size: 14px; }',
                        setup: function(editor) {
                            window.emailConfirmationEditor = editor;
                            
                            // Add change handler to mark as modified
                            editor.on('input change', function() {
                                if (window.emailConfirmationDialog) {
                                    window.emailConfirmationDialog.markAsModified('body');
                                }
                            });
                        }
                    });
                }
            }, 300);
        }
    }

    /**
     * Show the email confirmation dialog
     * @param {Object} options - Configuration options
     * @param {string} options.studentId - Student ID
     * @param {string} options.emailType - Type of email (acceptance, financial_aid, tuition_contract)
     * @param {string} options.division - Student division
     * @param {Function} options.onConfirm - Callback function when email is confirmed
     * @param {Object} options.customData - Additional data to pass to the callback
     */
    show(options) {
        this.currentCallback = options.onConfirm;
        this.currentOptions = options;

        // Set email type description
        const descriptions = {
            'acceptance': 'You are about to send an acceptance letter',
            'financial_aid': 'You are about to send a financial aid form',
            'tuition_contract': 'You are about to send a tuition contract',
            'enhanced_contract': 'You are about to send an enhanced tuition contract',
            'enrollment_contract': 'You are about to send an enrollment contract',
            'general': 'You are about to send an email'
        };
        
        const description = descriptions[options.emailType] || descriptions.general;
        document.getElementById('emailTypeDescription').textContent = description;

        // Show signing options for contract-related emails
        const contractTypes = ['tuition_contract', 'enhanced_contract', 'enrollment_contract'];
        const signingOptionsCard = document.getElementById('signingOptionsCard');
        
        if (contractTypes.includes(options.emailType)) {
            signingOptionsCard.style.display = 'block';
            // Initialize signing method preview
            this.updateSigningPreview();
        } else {
            signingOptionsCard.style.display = 'none';
        }

        // Load default recipients and render options
        this.loadDefaultRecipients(options.division, options.emailType)
            .then(defaultRecipients => {
                this.renderRecipientOptions(options.studentId, defaultRecipients);
                this.loadEmailPreview(options);
            });

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById(this.modalId));
        modal.show();
    }

    async loadDefaultRecipients(division, emailType) {
        try {
            const response = await fetch(`/api/divisions/${division}/email-recipient-settings`);
            const data = await response.json();
            
            if (data.success) {
                return data.settings[`${emailType}_email_default_recipients`] || ['student'];
            }
        } catch (error) {
            console.error('Error loading default recipients:', error);
        }
        
        return ['student']; // Fallback to student only
    }

    renderRecipientOptions(studentId, defaultRecipients) {
        const container = document.getElementById('recipientOptions');
        
        const recipients = [
            { key: 'student', label: 'Student', icon: 'fa-user', color: 'primary' },
            { key: 'father', label: 'Father', icon: 'fa-male', color: 'info' },
            { key: 'mother', label: 'Mother', icon: 'fa-female', color: 'danger' }
        ];

        let html = '';
        recipients.forEach(recipient => {
            const isChecked = defaultRecipients.includes(recipient.key);
            html += `
                <div class="col-md-4">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" 
                               id="recipient_${recipient.key}" 
                               ${isChecked ? 'checked' : ''}
                               onchange="emailConfirmationDialog.validateRecipients()">
                        <label class="form-check-label" for="recipient_${recipient.key}">
                            <i class="fas ${recipient.icon} text-${recipient.color} me-1"></i>
                            ${recipient.label}
                        </label>
                        <div class="email-address small text-muted" id="email_${recipient.key}">
                            Loading...
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

        // Load email addresses for each recipient
        this.loadRecipientEmails(studentId);
    }

    async loadRecipientEmails(studentId) {
        try {
            const response = await fetch(`/api/students/${studentId}/contact-info`);
            const data = await response.json();
            
            if (data.success) {
                const emails = data.emails;
                document.getElementById('email_student').textContent = emails.student || 'No email address';
                document.getElementById('email_father').textContent = emails.father || 'No email address';
                document.getElementById('email_mother').textContent = emails.mother || 'No email address';
                
                // Disable checkboxes for recipients without email addresses
                if (!emails.student) document.getElementById('recipient_student').disabled = true;
                if (!emails.father) document.getElementById('recipient_father').disabled = true;
                if (!emails.mother) document.getElementById('recipient_mother').disabled = true;
            }
        } catch (error) {
            console.error('Error loading recipient emails:', error);
        }
    }

    async loadEmailPreview(options) {
        const previewContainer = document.getElementById('emailPreview');
        
        try {
            const response = await fetch(`/api/students/${options.studentId}/email-preview/${options.emailType}`);
            const data = await response.json();
            
            if (data.success) {
                // Store original content for reference
                this.originalEmailContent = {
                    subject: data.subject,
                    body: data.body
                };

                previewContainer.innerHTML = `
                    <div class="mb-3">
                        <label for="editableSubject" class="form-label fw-bold">
                            <i class="fas fa-edit me-1"></i>Subject: 
                            <small class="text-muted">(editable)</small>
                            <span id="subjectModifiedIndicator" class="badge bg-warning ms-2" style="display: none;">Modified</span>
                        </label>
                        <input type="text" class="form-control" id="editableSubject" value="${this.escapeHtml(data.subject)}" oninput="emailConfirmationDialog.markAsModified('subject')">
                    </div>
                    <div class="mb-3">
                        <label for="editableBody" class="form-label fw-bold">
                            <i class="fas fa-edit me-1"></i>Email Body: 
                            <small class="text-muted">(editable)</small>
                            <span id="bodyModifiedIndicator" class="badge bg-warning ms-2" style="display: none;">Modified</span>
                        </label>
                        <textarea class="form-control" id="editableBody" rows="12" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;" oninput="emailConfirmationDialog.markAsModified('body')">${this.escapeHtml(data.body)}</textarea>
                    </div>
                    <div class="mb-3">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="includeSecureUpload" onchange="emailConfirmationDialog.handleSecureUploadToggle()">
                            <label class="form-check-label" for="includeSecureUpload">
                                <i class="fas fa-shield-alt text-success me-1"></i>
                                <strong>Include Secure Upload Link</strong>
                                <small class="text-muted">(allows families to upload documents securely)</small>
                            </label>
                        </div>
                        <div id="secureUploadInfo" class="small text-info mt-1" style="display: none;">
                            <i class="fas fa-info-circle me-1"></i>
                            When enabled, families will receive a secure upload link to submit documents. The email template will be enhanced with upload instructions and security features.
                        </div>
                    </div>
                    <div class="mb-2">
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="emailConfirmationDialog.resetToTemplate()">
                            <i class="fas fa-undo me-1"></i>Reset to Template
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-info" onclick="emailConfirmationDialog.togglePreview()">
                            <i class="fas fa-eye me-1"></i>Toggle Preview
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-success" onclick="emailConfirmationDialog.refreshWithSecureUpload()" id="refreshSecureUploadBtn" style="display: none;">
                            <i class="fas fa-sync me-1"></i>Apply Secure Upload
                        </button>
                    </div>
                    <div id="emailBodyPreview" class="border rounded p-3 bg-light" style="max-height: 200px; overflow-y: auto; display: none;">
                        ${data.body}
                    </div>
                    ${data.template_used ? `<small class="text-muted"><i class="fas fa-info-circle me-1"></i>Using template: ${data.template_used}</small>` : ''}
                `;
                
                // Initialize TinyMCE for the email body after content is loaded
                this.initializeEmailEditor();
            } else {
                previewContainer.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Could not load email preview: ${data.error}
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading email preview:', error);
            previewContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Error loading email preview
                </div>
            `;
        }
    }

    escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    resetToTemplate() {
        if (this.originalEmailContent) {
            document.getElementById('editableSubject').value = this.originalEmailContent.subject;
            
            // Update TinyMCE editor or textarea
            if (window.emailConfirmationEditor) {
                window.emailConfirmationEditor.setContent(this.originalEmailContent.body);
            } else {
                document.getElementById('editableBody').value = this.originalEmailContent.body;
            }
            
            // Update preview if visible
            const preview = document.getElementById('emailBodyPreview');
            if (preview && preview.style.display !== 'none') {
                preview.innerHTML = this.originalEmailContent.body;
            }
            // Hide modification indicators
            document.getElementById('subjectModifiedIndicator').style.display = 'none';
            document.getElementById('bodyModifiedIndicator').style.display = 'none';
        }
    }

    markAsModified(field) {
        if (!this.originalEmailContent) return;

        let currentValue;
        if (field === 'body' && window.emailConfirmationEditor) {
            currentValue = window.emailConfirmationEditor.getContent();
        } else {
            const element = document.getElementById(`editable${field.charAt(0).toUpperCase() + field.slice(1)}`);
            currentValue = element ? element.value : '';
        }
        
        const originalValue = this.originalEmailContent[field];
        const indicator = document.getElementById(`${field}ModifiedIndicator`);

        if (currentValue !== originalValue) {
            indicator.style.display = 'inline';
        } else {
            indicator.style.display = 'none';
        }
    }

    togglePreview() {
        const preview = document.getElementById('emailBodyPreview');
        const button = event.target.closest('button');
        
        if (preview.style.display === 'none') {
            // Show preview with current content
            let bodyContent;
            if (window.emailConfirmationEditor) {
                bodyContent = window.emailConfirmationEditor.getContent();
            } else {
                bodyContent = document.getElementById('editableBody').value;
            }
            preview.innerHTML = bodyContent;
            preview.style.display = 'block';
            button.innerHTML = '<i class="fas fa-eye-slash me-1"></i>Hide Preview';
        } else {
            // Hide preview
            preview.style.display = 'none';
            button.innerHTML = '<i class="fas fa-eye me-1"></i>Show Preview';
        }
    }

    validateRecipients() {
        const studentChecked = document.getElementById('recipient_student').checked;
        const fatherChecked = document.getElementById('recipient_father').checked;
        const motherChecked = document.getElementById('recipient_mother').checked;
        
        const sendButton = document.getElementById('confirmSendEmail');
        
        if (!studentChecked && !fatherChecked && !motherChecked) {
            sendButton.disabled = true;
            sendButton.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Select Recipients';
        } else {
            sendButton.disabled = false;
            sendButton.innerHTML = '<i class="fas fa-paper-plane me-2"></i>Send Email';
        }
    }

    updateSigningPreview() {
        const signingMethod = document.querySelector('input[name="signingMethod"]:checked')?.value;
        const previewDiv = document.getElementById('signingMethodPreview');
        
        const previews = {
            'digital': {
                text: 'With <strong>Digital Signature Only</strong> selected, families will receive an email with a secure link to sign electronically via OpenSign.',
                class: 'text-success'
            },
            'upload': {
                text: 'With <strong>Print & Upload</strong> selected, families will receive an email with a secure link to upload their signed contract.',
                class: 'text-primary'
            },
            'hybrid': {
                text: 'With <strong>Both Options Available</strong> selected, families will receive an email with both digital signature AND print/upload options so they can choose their preferred method.',
                class: 'text-warning'
            }
        };
        
        const preview = previews[signingMethod] || previews.digital;
        previewDiv.innerHTML = `
            <div class="small ${preview.class}">
                <i class="fas fa-eye me-1"></i>
                ${preview.text}
            </div>
        `;
    }

    handleSecureUploadToggle() {
        const checkbox = document.getElementById('includeSecureUpload');
        const infoDiv = document.getElementById('secureUploadInfo');
        const refreshBtn = document.getElementById('refreshSecureUploadBtn');
        
        if (checkbox.checked) {
            infoDiv.style.display = 'block';
            refreshBtn.style.display = 'inline-block';
        } else {
            infoDiv.style.display = 'none';
            refreshBtn.style.display = 'none';
        }
    }

    async refreshWithSecureUpload() {
        const includeSecureUpload = document.getElementById('includeSecureUpload').checked;
        
        if (!includeSecureUpload) {
            alert('Please enable "Include Secure Upload Link" first.');
            return;
        }

        const refreshBtn = document.getElementById('refreshSecureUploadBtn');
        const originalContent = refreshBtn.innerHTML;
        
        try {
            // Show loading state
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Applying...';
            refreshBtn.disabled = true;

            // Reload email preview with secure upload enabled
            const response = await fetch(`/api/students/${this.currentOptions.studentId}/email-preview/${this.currentOptions.emailType}?include_secure_upload=true`);
            const data = await response.json();
            
            if (data.success) {
                // Update the editable fields with the enhanced content
                document.getElementById('editableSubject').value = data.subject;
                
                // Update TinyMCE editor or textarea
                if (window.emailConfirmationEditor) {
                    window.emailConfirmationEditor.setContent(data.body);
                } else {
                    document.getElementById('editableBody').value = data.body;
                }
                
                // Update preview if visible
                const preview = document.getElementById('emailBodyPreview');
                if (preview && preview.style.display !== 'none') {
                    preview.innerHTML = data.body;
                }
                
                // Show success message
                const infoDiv = document.getElementById('secureUploadInfo');
                infoDiv.innerHTML = `
                    <i class="fas fa-check-circle text-success me-1"></i>
                    <strong>Secure upload link applied!</strong> The email now includes secure upload instructions and a link for families to upload documents safely.
                `;
                infoDiv.className = 'small text-success mt-1';
                
                // Update stored original content so reset works properly
                this.originalEmailContent = {
                    subject: data.subject,
                    body: data.body
                };

            } else {
                throw new Error(data.error || 'Failed to apply secure upload');
            }

        } catch (error) {
            console.error('Error applying secure upload:', error);
            alert('Error applying secure upload functionality. Please try again.');
        } finally {
            // Restore button state
            refreshBtn.innerHTML = originalContent;
            refreshBtn.disabled = false;
        }
    }

    handleSendConfirmation() {
        const selectedRecipients = [];
        
        if (document.getElementById('recipient_student').checked) selectedRecipients.push('student');
        if (document.getElementById('recipient_father').checked) selectedRecipients.push('father');
        if (document.getElementById('recipient_mother').checked) selectedRecipients.push('mother');
        
        if (selectedRecipients.length === 0) {
            alert('Please select at least one recipient.');
            return;
        }

        // Get edited email content
        const editedSubject = document.getElementById('editableSubject')?.value;
        let editedBody;
        if (window.emailConfirmationEditor) {
            editedBody = window.emailConfirmationEditor.getContent();
        } else {
            editedBody = document.getElementById('editableBody')?.value;
        }

        // Get signing method options
        const signingMethod = document.querySelector('input[name="signingMethod"]:checked')?.value || 'digital';
        const expirationHours = document.getElementById('expirationHours')?.value || 72;
        
        // Convert signing method to backend parameters
        let use_opensign = false;
        let use_secure_upload = false;
        
        switch (signingMethod) {
            case 'digital':
                use_opensign = true;
                break;
            case 'upload':
                use_secure_upload = true;
                break;
            case 'hybrid':
                use_opensign = true;
                use_secure_upload = true;
                break;
            default:
                // Default to print & upload
                use_secure_upload = true;
                break;
        }

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById(this.modalId));
        modal.hide();

        // Call the callback with selected recipients, edited content, and signing options
        if (this.currentCallback) {
            this.currentCallback({
                recipients: selectedRecipients,
                customEmailSubject: editedSubject,
                customEmailBody: editedBody,
                use_opensign: use_opensign,
                use_secure_upload: use_secure_upload,
                expires_hours: parseInt(expirationHours),
                signing_method: signingMethod,
                ...this.currentOptions.customData
            });
        }
    }
}

// Create global instance
const emailConfirmationDialog = new EmailConfirmationDialog();

// Make it available globally on window
window.emailConfirmationDialog = emailConfirmationDialog;

// Utility function for easy access
function showEmailConfirmation(options) {
    emailConfirmationDialog.show(options);
} 