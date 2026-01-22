document.addEventListener('DOMContentLoaded', function () {
    // Calculate percentage totals
    function updatePercentageTotal() {
        const selects = document.querySelectorAll('select[name$="_percent"]');
        let total = 0;

        selects.forEach(select => {
            total += parseInt(select.value) || 0;
        });

        const totalElement = document.getElementById('percentageTotal');
        const statusElement = document.getElementById('percentageStatus');
        const alertElement = document.getElementById('percentageAlert');

        if (totalElement) {
            totalElement.innerHTML = `Current total: <strong>${total}%</strong>`;

            // Update alert styling based on total
            // Accept 99-100% to handle rounding (e.g., 33% + 66% = 99%)
            alertElement.className = 'alert mt-3 mb-0';
            if (total >= 99 && total <= 100) {
                alertElement.classList.add('alert-success');
                statusElement.textContent = 'Perfect! You will be scheduled for duty.';
            } else if (total === 0) {
                alertElement.classList.add('alert-info');
                statusElement.textContent = 'You will not be scheduled for any duty.';
            } else {
                alertElement.classList.add('alert-danger');
                statusElement.textContent = 'Must equal 99-100% (rounding accepted) to be scheduled for duty.';
            }
        }
    }

    // Initialize visual state based on server data
    function initializeCalendarState() {
        document.querySelectorAll('.calendar-checkbox').forEach(checkbox => {
            const label = checkbox.closest('.calendar-day-label');
            const dayCell = checkbox.closest('.calendar-day');

            if (checkbox.checked) {
                // Checkbox is checked on server - ensure visual state matches
                dayCell.classList.add('selected-blackout');
                if (!label.querySelector('.blackout-icon')) {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-times-circle blackout-icon position-absolute text-danger';
                    label.appendChild(icon);
                }
            } else {
                // Checkbox is not checked - ensure visual state is clear
                dayCell.classList.remove('selected-blackout');
                const existingIcon = label.querySelector('.blackout-icon');
                if (existingIcon) {
                    existingIcon.remove();
                }
            }
        });
    }

    // Handle calendar checkbox interactions
    function setupCalendarInteractions() {
        document.querySelectorAll('.calendar-day-label').forEach(label => {
            label.addEventListener('click', function (e) {
                const checkbox = this.querySelector('.calendar-checkbox');
                const dayCell = this.closest('.calendar-day');

                if (checkbox && !checkbox.disabled) {
                    // Prevent double-toggle from label's default behavior
                    e.preventDefault();

                    // Toggle checkbox state
                    checkbox.checked = !checkbox.checked;

                    // Get blackout icon AFTER potential DOM changes
                    const blackoutIcon = this.querySelector('.blackout-icon');

                    // Update visual state to match checkbox state
                    if (checkbox.checked) {
                        // Checkbox is checked = date will be blacked out
                        dayCell.classList.add('selected-blackout');
                        if (!blackoutIcon) {
                            const icon = document.createElement('i');
                            icon.className = 'fas fa-times-circle blackout-icon position-absolute text-danger';
                            this.appendChild(icon);
                        }
                    } else {
                        // Checkbox is unchecked = date will NOT be blacked out
                        dayCell.classList.remove('selected-blackout');
                        if (blackoutIcon) {
                            blackoutIcon.remove();
                        }
                    }
                }
            });
        });
    }

    // Add event listeners to percentage selects
    document.querySelectorAll('select[name$="_percent"]').forEach(select => {
        select.addEventListener('change', updatePercentageTotal);
    });

    // Initial calculations and setup
    updatePercentageTotal();
    initializeCalendarState();
    setupCalendarInteractions();
});
