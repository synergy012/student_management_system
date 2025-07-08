/* ====================================
   MODERN UI JAVASCRIPT
   Student Management System
   ==================================== */

// Toast Notification System
class ToastManager {
    constructor() {
        this.container = this.createContainer();
    }
    
    createContainer() {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }
    
    show(message, type = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = this.getIcon(type);
        toast.innerHTML = `
            <div class="toast-icon">
                <i class="fas fa-${icon}"></i>
            </div>
            <div class="toast-message">${message}</div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        this.container.appendChild(toast);
        
        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        // Auto remove
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
        
        return toast;
    }
    
    getIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'times-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }
    
    success(message, duration) {
        return this.show(message, 'success', duration);
    }
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    }
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Initialize toast manager
const toast = new ToastManager();

// Theme Toggle System
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.init();
    }
    
    init() {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        this.createToggleButton();
        this.updateToggleButton();
    }
    
    createToggleButton() {
        // Check if toggle already exists
        if (document.querySelector('.theme-toggle')) return;
        
        const toggle = document.createElement('button');
        toggle.className = 'btn btn-sm btn-outline-secondary theme-toggle';
        toggle.innerHTML = '<i class="fas fa-moon"></i>';
        toggle.title = 'Toggle Dark Mode';
        toggle.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1060;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        
        toggle.addEventListener('click', () => this.toggle());
        document.body.appendChild(toggle);
    }
    
    toggle() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        localStorage.setItem('theme', this.currentTheme);
        this.updateToggleButton();
        
        // Animate the transition
        document.documentElement.style.transition = 'background-color 0.3s, color 0.3s';
        setTimeout(() => {
            document.documentElement.style.transition = '';
        }, 300);
    }
    
    updateToggleButton() {
        const toggle = document.querySelector('.theme-toggle');
        if (toggle) {
            const icon = toggle.querySelector('i');
            icon.className = this.currentTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }
    }
}

// Search Enhancement
class SearchManager {
    constructor(inputSelector, resultCallback) {
        this.input = document.querySelector(inputSelector);
        this.callback = resultCallback;
        this.timeout = null;
        this.init();
    }
    
    init() {
        if (!this.input) return;
        
        this.input.addEventListener('input', (e) => {
            clearTimeout(this.timeout);
            this.timeout = setTimeout(() => {
                this.performSearch(e.target.value);
            }, 300);
        });
        
        // Add search icon and clear button
        this.enhanceInput();
    }
    
    enhanceInput() {
        const wrapper = document.createElement('div');
        wrapper.className = 'search-wrapper position-relative';
        wrapper.style.cssText = 'display: inline-block; position: relative; width: 100%;';
        
        this.input.parentNode.insertBefore(wrapper, this.input);
        wrapper.appendChild(this.input);
        
        // Add search icon
        const searchIcon = document.createElement('i');
        searchIcon.className = 'fas fa-search';
        searchIcon.style.cssText = `
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: #9ca3af;
            z-index: 10;
        `;
        wrapper.appendChild(searchIcon);
        
        // Add padding to input for icon
        this.input.style.paddingLeft = '2.5rem';
        
        // Add clear button when there's text
        this.input.addEventListener('input', (e) => {
            this.updateClearButton(wrapper, e.target.value);
        });
    }
    
    updateClearButton(wrapper, value) {
        let clearBtn = wrapper.querySelector('.search-clear');
        
        if (value && !clearBtn) {
            clearBtn = document.createElement('button');
            clearBtn.className = 'search-clear';
            clearBtn.innerHTML = '<i class="fas fa-times"></i>';
            clearBtn.style.cssText = `
                position: absolute;
                right: 12px;
                top: 50%;
                transform: translateY(-50%);
                background: none;
                border: none;
                color: #9ca3af;
                cursor: pointer;
                z-index: 10;
            `;
            clearBtn.addEventListener('click', () => {
                this.input.value = '';
                this.performSearch('');
                clearBtn.remove();
            });
            wrapper.appendChild(clearBtn);
        } else if (!value && clearBtn) {
            clearBtn.remove();
        }
    }
    
    performSearch(query) {
        if (this.callback) {
            this.callback(query);
        }
    }
}

// Loading Button Enhancement
function createLoadingButton(button, text = 'Loading...') {
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status"></span>
        ${text}
    `;
    
    return function stopLoading() {
        button.disabled = false;
        button.innerHTML = originalText;
    };
}

// Enhanced Form Validation
class FormValidator {
    constructor(formSelector) {
        this.form = document.querySelector(formSelector);
        this.init();
    }
    
    init() {
        if (!this.form) return;
        
        this.form.addEventListener('submit', (e) => {
            if (!this.validate()) {
                e.preventDefault();
            }
        });
        
        // Real-time validation
        this.form.querySelectorAll('input, textarea, select').forEach(field => {
            field.addEventListener('blur', () => this.validateField(field));
            field.addEventListener('input', () => this.clearFieldError(field));
        });
    }
    
    validate() {
        let isValid = true;
        const fields = this.form.querySelectorAll('input[required], textarea[required], select[required]');
        
        fields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });
        
        return isValid;
    }
    
    validateField(field) {
        const value = field.value.trim();
        let isValid = true;
        let message = '';
        
        // Required validation
        if (field.hasAttribute('required') && !value) {
            isValid = false;
            message = 'This field is required';
        }
        
        // Email validation
        if (field.type === 'email' && value && !this.isValidEmail(value)) {
            isValid = false;
            message = 'Please enter a valid email address';
        }
        
        // Phone validation
        if (field.type === 'tel' && value && !this.isValidPhone(value)) {
            isValid = false;
            message = 'Please enter a valid phone number';
        }
        
        this.showFieldError(field, message, !isValid);
        return isValid;
    }
    
    showFieldError(field, message, hasError) {
        this.clearFieldError(field);
        
        if (hasError) {
            field.classList.add('is-invalid');
            const error = document.createElement('div');
            error.className = 'invalid-feedback';
            error.textContent = message;
            field.parentNode.appendChild(error);
        } else {
            field.classList.add('is-valid');
        }
    }
    
    clearFieldError(field) {
        field.classList.remove('is-invalid', 'is-valid');
        const error = field.parentNode.querySelector('.invalid-feedback');
        if (error) error.remove();
    }
    
    isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    isValidPhone(phone) {
        return /^[\+]?[1-9][\d]{0,15}$/.test(phone.replace(/\s/g, ''));
    }
}

// Keyboard Shortcuts
class KeyboardShortcuts {
    constructor() {
        this.shortcuts = {
            '/': () => this.focusSearch(),
            'n': () => this.createNew(),
            'Escape': () => this.closeModals()
        };
        this.init();
    }
    
    init() {
        document.addEventListener('keydown', (e) => {
            // Don't trigger shortcuts when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                if (e.key === 'Escape') {
                    e.target.blur();
                }
                return;
            }
            
            const handler = this.shortcuts[e.key];
            if (handler) {
                e.preventDefault();
                handler();
            }
        });
    }
    
    focusSearch() {
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="search"], input[placeholder*="Search"]');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    createNew() {
        const createBtn = document.querySelector('a[href*="/new"], a[href*="/create"], .btn-success[href*="/add"]');
        if (createBtn) {
            createBtn.click();
        }
    }
    
    closeModals() {
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const closeBtn = modal.querySelector('.btn-close, [data-bs-dismiss="modal"]');
            if (closeBtn) closeBtn.click();
        });
    }
}

// Auto-save for forms
class AutoSave {
    constructor(formSelector, saveInterval = 30000) {
        this.form = document.querySelector(formSelector);
        this.saveInterval = saveInterval;
        this.saveKey = this.generateSaveKey();
        this.init();
    }
    
    init() {
        if (!this.form) return;
        
        // Load saved data
        this.loadSavedData();
        
        // Save on input
        this.form.addEventListener('input', debounce(() => {
            this.saveData();
        }, 1000));
        
        // Clear saved data on successful submit
        this.form.addEventListener('submit', () => {
            this.clearSavedData();
        });
        
        // Periodic save
        setInterval(() => {
            if (this.hasChanges()) {
                this.saveData();
            }
        }, this.saveInterval);
    }
    
    generateSaveKey() {
        return `autosave_${window.location.pathname}_${this.form.id || 'form'}`;
    }
    
    saveData() {
        const formData = new FormData(this.form);
        const data = {};
        
        for (let [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        localStorage.setItem(this.saveKey, JSON.stringify({
            data,
            timestamp: Date.now()
        }));
        
        this.showSaveIndicator();
    }
    
    loadSavedData() {
        const saved = localStorage.getItem(this.saveKey);
        if (!saved) return;
        
        try {
            const { data, timestamp } = JSON.parse(saved);
            
            // Don't load data older than 24 hours
            if (Date.now() - timestamp > 24 * 60 * 60 * 1000) {
                this.clearSavedData();
                return;
            }
            
            // Fill form with saved data
            Object.entries(data).forEach(([key, value]) => {
                const field = this.form.querySelector(`[name="${key}"]`);
                if (field && !field.value) {
                    field.value = value;
                }
            });
            
            // Show notification
            toast.info('Draft restored from auto-save', 3000);
            
        } catch (e) {
            this.clearSavedData();
        }
    }
    
    clearSavedData() {
        localStorage.removeItem(this.saveKey);
    }
    
    hasChanges() {
        const inputs = this.form.querySelectorAll('input, textarea, select');
        return Array.from(inputs).some(input => input.value.trim() !== '');
    }
    
    showSaveIndicator() {
        let indicator = document.querySelector('.autosave-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'autosave-indicator';
            indicator.style.cssText = `
                position: fixed;
                bottom: 80px;
                right: 20px;
                background: rgba(0,0,0,0.8);
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 12px;
                z-index: 1050;
                opacity: 0;
                transition: opacity 0.3s;
            `;
            document.body.appendChild(indicator);
        }
        
        indicator.textContent = '💾 Draft saved';
        indicator.style.opacity = '1';
        
        setTimeout(() => {
            indicator.style.opacity = '0';
        }, 2000);
    }
}

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function formatDate(date) {
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    }).format(new Date(date));
}

// Enhanced AJAX with loading states
function fetchWithLoading(url, options = {}) {
    const loadingToast = toast.info('Loading...', 0);
    
    return fetch(url, options)
        .then(response => {
            loadingToast.remove();
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .catch(error => {
            loadingToast.remove();
            toast.error(`Error: ${error.message}`);
            throw error;
        });
}

// Page transition effects
function addPageTransitions() {
    document.addEventListener('DOMContentLoaded', () => {
        document.body.classList.add('page-enter');
    });
    
    // Smooth transitions for navigation
    document.addEventListener('click', (e) => {
        const link = e.target.closest('a[href]');
        if (link && !link.target && link.href.startsWith(window.location.origin)) {
            e.preventDefault();
            
            document.body.style.transition = 'opacity 0.2s';
            document.body.style.opacity = '0';
            
            setTimeout(() => {
                window.location.href = link.href;
            }, 200);
        }
    });
}

// Initialize all features when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize theme manager
    new ThemeManager();
    
    // Initialize keyboard shortcuts
    new KeyboardShortcuts();
    
    // Add page transitions
    addPageTransitions();
    
    // Initialize auto-save for forms
    const forms = document.querySelectorAll('form[data-autosave]');
    forms.forEach(form => {
        new AutoSave(`#${form.id}`);
    });
    
    // Initialize form validation
    const validatedForms = document.querySelectorAll('form[data-validate]');
    validatedForms.forEach(form => {
        new FormValidator(`#${form.id}`);
    });
    
    // Enhanced loading buttons
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn[data-loading]');
        if (btn) {
            const stopLoading = createLoadingButton(btn, btn.dataset.loading || 'Loading...');
            
            // Auto-stop loading after 10 seconds
            setTimeout(stopLoading, 10000);
        }
    });
});

// Export for global use
window.toast = toast;
window.SearchManager = SearchManager;
window.createLoadingButton = createLoadingButton;
window.fetchWithLoading = fetchWithLoading; 