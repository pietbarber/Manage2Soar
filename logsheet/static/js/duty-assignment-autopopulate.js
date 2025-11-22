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
            console.log('Duty assignment data received:', data);
            var fields = [
                'duty_officer', 'assistant_duty_officer', 'duty_instructor',
                'surge_instructor', 'tow_pilot', 'surge_tow_pilot'
            ];
            fields.forEach(function (field) {
                var select = document.getElementById('id_' + field);
                if (select && data[field]) {
                    console.log('Setting', field, 'to', data[field]);
                    select.value = data[field];
                }
            });
        })
        .catch(error => {
            console.error('Error fetching duty assignment:', error);
        });
}

/**
 * Enhanced form validation with Bootstrap styling
 * @param {HTMLElement} towplane - The towplane select element
 * @returns {boolean} - True if validation passes
 */
function validateTowplane(towplane) {
    if (towplane && (!towplane.value || towplane.value === '')) {
        // Add Bootstrap validation class
        towplane.classList.add('is-invalid');

        // Create or update validation feedback
        var feedbackEl = towplane.parentNode.querySelector('.invalid-feedback');
        if (!feedbackEl) {
            feedbackEl = document.createElement('div');
            feedbackEl.className = 'invalid-feedback';
            towplane.parentNode.appendChild(feedbackEl);
        }
        feedbackEl.textContent = 'Please select a default towplane before creating the logsheet.';

        towplane.focus();
        return false;
    }

    // Remove validation classes if validation passes
    towplane.classList.remove('is-invalid');
    var feedbackEl = towplane.parentNode.querySelector('.invalid-feedback');
    if (feedbackEl) {
        feedbackEl.remove();
    }

    return true;
}

/**
 * Initialize duty assignment auto-population for logsheet forms
 */
function initDutyAssignmentAutoPopulation() {
    document.addEventListener('DOMContentLoaded', function () {
        var dateInput = document.getElementById('id_log_date');
        if (dateInput) {
            // Auto-populate on page load if there's a date value
            if (dateInput.value) {
                console.log('Page loaded with date:', dateInput.value, '- fetching duty assignment');
                fetchDutyAssignment(dateInput.value);
            }

            // Auto-populate when date changes
            dateInput.addEventListener('change', function () {
                var dateVal = this.value;
                if (!dateVal) return;
                console.log('Date changed to:', dateVal, '- fetching duty assignment');
                fetchDutyAssignment(dateVal);
            });
        }

        // Enhanced form validation for towplane
        var createForm = document.querySelector('form[method="POST"]');
        if (createForm) {
            createForm.addEventListener('submit', function (e) {
                var towplane = document.getElementById('id_default_towplane');
                if (!validateTowplane(towplane)) {
                    e.preventDefault();
                }
            });
        }
    });
}

// Initialize the functionality
initDutyAssignmentAutoPopulation();
