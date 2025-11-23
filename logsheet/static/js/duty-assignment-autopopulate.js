/**
 * Duty Assignment Auto-population JavaScript
 * Shared functionality for logsheet creation forms
 */

/**
 * Fetch duty assignment data for a given date and populate form fields
 * @param {string} dateVal - Date in YYYY-MM-DD format
 */
function fetchDutyAssignment(dateVal) {
    fetch('/logsheet/api/duty-assignment/?date=' + encodeURIComponent(dateVal), {
        credentials: 'same-origin'
    })
        .then(response => {
            if (!response.ok) {
                console.error('API request failed:', response.status, response.statusText);
                return {};
            }
            return response.json();
        })
        .then(data => {
            // Data received and processing form fields
            var fields = [
                'duty_officer', 'assistant_duty_officer', 'duty_instructor',
                'surge_instructor', 'tow_pilot', 'surge_tow_pilot'
            ];
            fields.forEach(function (field) {
                var select = document.getElementById('id_' + field);
                if (select && data[field]) {
                    // Setting field value from duty roster data
                    select.value = data[field];
                }
            });
        })
        .catch(error => {
            console.error('Error fetching duty assignment:', error);
        });
}

/**
 * Enhanced form validation with Bootstrap styling (optional validation)
 * @param {HTMLElement} towplane - The towplane select element
 * @returns {boolean} - True if validation passes (always true since field is optional)
 */
function validateTowplane(towplane) {
    // Since default_towplane is optional in Django form, only provide visual feedback
    // Remove any existing validation classes for consistent UX
    if (towplane) {
        towplane.classList.remove('is-invalid');
        var feedbackEl = towplane.parentNode.querySelector('.invalid-feedback');
        if (feedbackEl) {
            feedbackEl.remove();
        }
    }
    return true; // Always allow submission since field is optional
}

/**
 * Handler for duty assignment auto-population initialization
 */
function dutyAssignmentAutoPopulationHandler() {
    var dateInput = document.getElementById('id_log_date');
    if (dateInput) {
        // Auto-populate on page load if there's a date value
        if (dateInput.value) {
            // Auto-fetching duty assignment for loaded date
            fetchDutyAssignment(dateInput.value);
        }

        // Auto-populate when date changes
        dateInput.addEventListener('change', function () {
            var dateVal = this.value;
            if (!dateVal) return;
            // Fetching duty assignment for new date
            fetchDutyAssignment(dateVal);
        });
    }

    // Enhanced form validation for towplane
    var createForm = document.querySelector('form[method="POST"]');
    if (createForm) {
        createForm.addEventListener('submit', function (e) {
            var towplane = document.getElementById('id_default_towplane');
            validateTowplane(towplane); // Just clean up UI, don't prevent submission
        });
    }
}

// Initialize the functionality robustly
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', dutyAssignmentAutoPopulationHandler);
} else {
    dutyAssignmentAutoPopulationHandler();
}
