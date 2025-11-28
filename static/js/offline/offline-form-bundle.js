/**
 * Manage2Soar Offline Flight Form (Non-ES-Module Bundle)
 *
 * Renders and handles flight entry forms when offline, using cached reference data.
 * This version uses global namespaces (window.M2SOffline, window.M2SIndexedDB) instead
 * of ES modules to avoid CORS issues when loading from GCS.
 *
 * Part of Issue #315: PWA Fully-offline Logsheet data entry
 *
 * IMPORTANT: This script must be loaded AFTER indexeddb-bundle.js
 */

(function (global) {
    'use strict';

    // Get IndexedDB module from global namespace
    function getDB() {
        if (!global.M2SIndexedDB) {
            throw new Error('[OfflineForm] M2SIndexedDB not loaded. Ensure indexeddb-bundle.js is loaded first.');
        }
        return global.M2SIndexedDB;
    }

    // =========================================================
    // REFERENCE DATA FUNCTIONS
    // =========================================================

    /**
     * Check if we have cached reference data for offline use
     * @returns {Promise<boolean>}
     */
    async function hasReferenceData() {
        try {
            const db = getDB();
            await db.openDatabase();
            const members = await db.getAll('members');
            const gliders = await db.getAll('gliders');
            return members.length > 0 && gliders.length > 0;
        } catch (e) {
            console.error('[OfflineForm] Error checking reference data:', e);
            return false;
        }
    }

    /**
     * Get cached reference data for form dropdowns
     * @returns {Promise<object|null>}
     */
    async function getReferenceData() {
        try {
            const db = getDB();
            await db.openDatabase();
            const members = await db.getAll('members');
            const gliders = await db.getAll('gliders');
            const towplanes = await db.getAll('towplanes');
            const airfields = await db.getAll('airfields');

            return {
                members: members.sort((a, b) => (a.lastName || '').localeCompare(b.lastName || '')),
                gliders: gliders.filter(g => g.isActive !== false),
                towplanes: towplanes.filter(t => t.isActive !== false),
                airfields: airfields.filter(a => a.isActive !== false),
            };
        } catch (e) {
            console.error('[OfflineForm] Error getting reference data:', e);
            return null;
        }
    }

    // =========================================================
    // FORM RENDERING HELPERS
    // =========================================================

    function getCurrentTime() {
        const now = new Date();
        const h = now.getHours().toString().padStart(2, '0');
        const m = now.getMinutes().toString().padStart(2, '0');
        return `${h}:${m}`;
    }

    function renderSelect(name, id, options, labelFn, valueFn, emptyLabel) {
        emptyLabel = emptyLabel || '----';
        const optionsHtml = options.map(opt =>
            `<option value="${valueFn(opt)}">${labelFn(opt)}</option>`
        ).join('');

        return `
            <select name="${name}" id="${id}" class="form-select">
                <option value="">${emptyLabel}</option>
                ${optionsHtml}
            </select>
        `;
    }

    function renderAltitudeSelect() {
        const altitudes = [];
        // Match the real form: 0-7000 in 100ft steps
        for (let alt = 0; alt <= 7000; alt += 100) {
            if (alt > 0) {  // Skip 0, start from 100
                altitudes.push({ value: alt, label: `${alt}` });
            }
        }

        return `
            <select name="release_altitude" id="id_release_altitude" class="form-select">
                <option value="">--------------</option>
                ${altitudes.map(a => `<option value="${a.value}">${a.label}</option>`).join('')}
            </select>
        `;
    }

    // =========================================================
    // MAIN FORM RENDERING
    // =========================================================

    /**
     * Render the offline flight form HTML
     * @param {object} refData - Cached reference data
     * @param {number} logsheetId - ID of the logsheet
     * @returns {string} HTML string
     */
    function renderOfflineFlightForm(refData, logsheetId) {
        const { members, gliders, towplanes } = refData;

        // Separate members by role hints (if available)
        const allMembers = members;
        const instructors = members.filter(m => m.isInstructor);
        const towPilots = members.filter(m => m.isTowpilot);

        // Separate gliders by type
        const clubGliders = gliders.filter(g => g.clubOwned === true);
        const privateGliders = gliders.filter(g => g.clubOwned === false);

        return `
            <div class="modal-header bg-warning text-dark">
                <div class="d-flex align-items-center">
                    <i class="bi bi-wifi-off me-2 fs-4"></i>
                    <div>
                        <h5 class="modal-title mb-0">
                            <i class="bi bi-plus-circle me-1"></i>Add Flight (Offline Mode)
                        </h5>
                        <small class="opacity-75">Data will sync when back online</small>
                    </div>
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body p-4">
                <div class="alert alert-info border-0 mb-4">
                    <i class="bi bi-info-circle me-2"></i>
                    <strong>Working Offline</strong> - This flight will be saved locally and synced when you're back online.
                </div>

                <form id="offline-flight-form" data-logsheet-id="${logsheetId}">
                    <!-- Aircraft & Crew Section -->
                    <div class="flight-form-section flight-form-section--primary p-3 mb-4" style="background: rgba(13, 110, 253, 0.05); border-radius: 8px; border-left: 4px solid #0d6efd;">
                        <h6 class="text-primary mb-3">
                            <i class="bi bi-airplane-engines me-2"></i>Aircraft & Crew
                        </h6>

                        <div class="row g-3">
                            <!-- Glider Selection -->
                            <div class="col-md-6">
                                <label for="id_glider" class="form-label fw-semibold">
                                    <i class="bi bi-airplane me-1"></i>Glider <span class="text-danger">*</span>
                                </label>
                                <select name="glider" id="id_glider" class="form-select">
                                    <option value="">Choose a glider...</option>
                                    ${clubGliders.length > 0 ? `
                                    <optgroup label="🏆 Club Gliders">
                                        ${clubGliders.map(g => `<option value="${g.id}">${g.displayName || g.competitionNumber || g.nNumber}</option>`).join('')}
                                    </optgroup>
                                    ` : ''}
                                    ${privateGliders.length > 0 ? `
                                    <optgroup label="🏠 Private Gliders">
                                        ${privateGliders.map(g => `<option value="${g.id}">${g.displayName || g.competitionNumber || g.nNumber}</option>`).join('')}
                                    </optgroup>
                                    ` : ''}
                                </select>
                            </div>

                            <!-- Pilot Selection -->
                            <div class="col-md-6">
                                <label for="id_pilot" class="form-label fw-semibold">
                                    <i class="bi bi-person-badge me-1"></i>Pilot <span class="text-danger">*</span>
                                </label>
                                ${renderSelect('pilot', 'id_pilot', allMembers, m => m.displayName || m.name, m => m.id, '--------')}
                            </div>

                            <!-- Instructor -->
                            <div class="col-md-6">
                                <label for="id_instructor" class="form-label fw-semibold">
                                    <i class="bi bi-mortarboard me-1"></i>Instructor
                                </label>
                                ${renderSelect('instructor', 'id_instructor', instructors.length > 0 ? instructors : allMembers, m => m.displayName || m.name, m => m.id, '--------')}
                            </div>

                            <!-- Passenger (Member) -->
                            <div class="col-md-6">
                                <label for="id_passenger" class="form-label fw-semibold">
                                    <i class="bi bi-person me-1"></i>Passenger (Member)
                                </label>
                                ${renderSelect('passenger', 'id_passenger', allMembers, m => m.displayName || m.name, m => m.id, '--------')}
                            </div>

                            <!-- Passenger Name (Non-member) -->
                            <div class="col-md-6">
                                <label for="id_passenger_name" class="form-label fw-semibold">
                                    <i class="bi bi-person-plus me-1"></i>Passenger Name (Non-member)
                                </label>
                                <input type="text" name="passenger_name" id="id_passenger_name" class="form-control" placeholder="If not a member">
                            </div>
                        </div>
                    </div>

                    <!-- Tow Operations Section -->
                    <div class="flight-form-section flight-form-section--success p-3 mb-4" style="background: rgba(25, 135, 84, 0.05); border-radius: 8px; border-left: 4px solid #198754;">
                        <h6 class="text-success mb-3">
                            <i class="bi bi-truck me-2"></i>Tow Operations
                        </h6>

                        <div class="row g-3">
                            <!-- Tow Pilot -->
                            <div class="col-md-6">
                                <label for="id_tow_pilot" class="form-label fw-semibold">
                                    <i class="bi bi-person-gear me-1"></i>Tow Pilot
                                </label>
                                ${renderSelect('tow_pilot', 'id_tow_pilot', towPilots.length > 0 ? towPilots : allMembers, m => m.displayName || m.name, m => m.id, '--------')}
                            </div>

                            <!-- Towplane -->
                            <div class="col-md-6">
                                <label for="id_towplane" class="form-label fw-semibold">
                                    <i class="bi bi-airplane-engines me-1"></i>Towplane
                                </label>
                                ${renderSelect('towplane', 'id_towplane', towplanes, t => t.displayName || t.name || t.nNumber, t => t.id, '--------')}
                            </div>
                        </div>
                    </div>

                    <!-- Flight Times & Altitude Section -->
                    <div class="flight-form-section flight-form-section--warning p-3 mb-4" style="background: rgba(255, 193, 7, 0.1); border-radius: 8px; border-left: 4px solid #ffc107;">
                        <h6 class="text-warning mb-3">
                            <i class="bi bi-clock me-2"></i>Flight Times & Altitude
                        </h6>

                        <div class="row g-3">
                            <!-- Launch Time -->
                            <div class="col-md-4">
                                <label for="id_launch_time" class="form-label fw-semibold">
                                    <i class="bi bi-arrow-up-circle me-1"></i>Launch Time
                                </label>
                                <div class="input-group">
                                    <input type="time" name="launch_time" id="id_launch_time" class="form-control" placeholder="--:--">
                                    <button type="button" class="btn btn-outline-secondary btn-sm" id="now-launch-btn">
                                        <i class="bi bi-clock-fill me-1"></i>NOW
                                    </button>
                                </div>
                            </div>

                            <!-- Landing Time -->
                            <div class="col-md-4">
                                <label for="id_landing_time" class="form-label fw-semibold">
                                    <i class="bi bi-arrow-down-circle me-1"></i>Landing Time
                                </label>
                                <div class="input-group">
                                    <input type="time" name="landing_time" id="id_landing_time" class="form-control" placeholder="--:--">
                                    <button type="button" class="btn btn-outline-secondary btn-sm" id="now-landing-btn">
                                        <i class="bi bi-clock-fill me-1"></i>NOW
                                    </button>
                                </div>
                            </div>

                            <!-- Release Altitude -->
                            <div class="col-md-4">
                                <label for="id_release_altitude" class="form-label fw-semibold">
                                    <i class="bi bi-graph-up me-1"></i>Release Altitude (AGL)
                                </label>
                                <div class="input-group">
                                    ${renderAltitudeSelect()}
                                    <button type="button" class="btn btn-outline-info btn-sm" id="alt-2k-btn">2K</button>
                                    <button type="button" class="btn btn-outline-info btn-sm" id="alt-3k-btn">3K</button>
                                </div>
                                <div class="form-text">
                                    <i class="bi bi-info-circle me-1"></i>Altitude in feet (0–7000, 100ft steps)
                                </div>
                            </div>
                        </div>
                    </div>
                </form>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-warning" id="save-offline-flight-btn">
                    <i class="bi bi-download me-1"></i>
                    Save Offline
                </button>
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            </div>
        `;
    }

    // =========================================================
    // EVENT HANDLERS
    // =========================================================

    /**
     * Initialize offline form event handlers
     * Call this after rendering the form
     */
    function initOfflineFormHandlers(onSaveCallback) {
        // Now buttons for launch/landing time
        const launchNowBtn = document.getElementById('now-launch-btn');
        const landingNowBtn = document.getElementById('now-landing-btn');
        const launchInput = document.getElementById('id_launch_time');
        const landingInput = document.getElementById('id_landing_time');

        if (launchNowBtn && launchInput) {
            launchNowBtn.addEventListener('click', () => {
                launchInput.value = getCurrentTime();
            });
        }

        if (landingNowBtn && landingInput) {
            landingNowBtn.addEventListener('click', () => {
                landingInput.value = getCurrentTime();
            });
        }

        // Altitude quick buttons
        const alt2kBtn = document.getElementById('alt-2k-btn');
        const alt3kBtn = document.getElementById('alt-3k-btn');
        const altSelect = document.getElementById('id_release_altitude');

        if (alt2kBtn && altSelect) {
            alt2kBtn.addEventListener('click', () => {
                altSelect.value = '2000';
            });
        }

        if (alt3kBtn && altSelect) {
            alt3kBtn.addEventListener('click', () => {
                altSelect.value = '3000';
            });
        }

        // Save button
        const saveBtn = document.getElementById('save-offline-flight-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                await saveOfflineFlight(onSaveCallback);
            });
        }
    }

    // =========================================================
    // SAVE FLIGHT
    // =========================================================

    async function saveOfflineFlight(onSaveCallback) {
        const form = document.getElementById('offline-flight-form');
        if (!form) {
            console.error('[OfflineForm] Form not found');
            return;
        }

        const logsheetId = parseInt(form.dataset.logsheetId, 10);

        // Validate required fields
        const pilotSelect = document.getElementById('id_pilot');
        const gliderSelect = document.getElementById('id_glider');

        if (!pilotSelect.value) {
            alert('Please select a pilot');
            pilotSelect.focus();
            return;
        }

        if (!gliderSelect.value) {
            alert('Please select a glider');
            gliderSelect.focus();
            return;
        }

        // Collect form data
        const flightData = {
            pilot: parseInt(pilotSelect.value, 10) || null,
            instructor: parseInt(document.getElementById('id_instructor').value, 10) || null,
            glider: parseInt(gliderSelect.value, 10) || null,
            passenger: parseInt(document.getElementById('id_passenger').value, 10) || null,
            passenger_name: document.getElementById('id_passenger_name').value || '',
            towplane: parseInt(document.getElementById('id_towplane').value, 10) || null,
            tow_pilot: parseInt(document.getElementById('id_tow_pilot').value, 10) || null,
            launch_time: document.getElementById('id_launch_time').value || null,
            landing_time: document.getElementById('id_landing_time').value || null,
            release_altitude: parseInt(document.getElementById('id_release_altitude').value, 10) || null,
        };

        try {
            const db = getDB();
            const localId = await db.createPendingFlight(flightData, logsheetId);
            console.log('[OfflineForm] Flight saved with local ID:', localId);

            // Close modal
            const modalEl = document.getElementById('flightModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) {
                modal.hide();
            }

            // Show success message
            showOfflineFlightSaved(flightData);

            // Trigger callback to update UI
            if (onSaveCallback) {
                onSaveCallback(localId, flightData);
            }

            // Try to register for background sync
            if ('serviceWorker' in navigator && 'SyncManager' in window) {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('sync-flights');
                console.log('[OfflineForm] Background sync registered');
            }

        } catch (e) {
            console.error('[OfflineForm] Error saving flight:', e);
            alert('Failed to save flight locally. Please try again.');
        }
    }

    // =========================================================
    // UI FEEDBACK
    // =========================================================

    function showOfflineFlightSaved(flightData) {
        // Create toast container if not exists
        let toastContainer = document.getElementById('offline-toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'offline-toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3 mt-5';
            toastContainer.style.zIndex = '1100';
            document.body.appendChild(toastContainer);
        }

        const toastId = 'offline-saved-toast-' + Date.now();
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white bg-warning border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="bi bi-download me-2"></i>
                        <strong>Flight saved offline!</strong>
                        Will sync when online.
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>
        `;

        toastContainer.insertAdjacentHTML('beforeend', toastHtml);

        const toastEl = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastEl, { delay: 5000 });
        toast.show();

        toastEl.addEventListener('hidden.bs.toast', () => {
            toastEl.remove();
        });
    }

    // =========================================================
    // PENDING FLIGHTS INDICATOR
    // =========================================================

    async function getPendingFlightCount() {
        try {
            const db = getDB();
            const pending = await db.getPendingFlights();
            return pending.length;
        } catch (e) {
            console.error('[OfflineForm] Error getting pending count:', e);
            return 0;
        }
    }

    async function updatePendingIndicator() {
        const count = await getPendingFlightCount();
        const indicator = document.getElementById('pending-flights-indicator');

        if (indicator) {
            if (count > 0) {
                indicator.textContent = count;
                indicator.style.display = 'inline-block';
            } else {
                indicator.style.display = 'none';
            }
        }

        // Also update any sync status UI
        const syncStatus = document.getElementById('offline-sync-status');
        if (syncStatus && count > 0) {
            syncStatus.innerHTML = `
                <span class="badge bg-warning text-dark">
                    <i class="bi bi-cloud-arrow-up me-1"></i>
                    ${count} flight${count > 1 ? 's' : ''} pending sync
                </span>
            `;
            syncStatus.style.display = 'block';
        } else if (syncStatus) {
            syncStatus.style.display = 'none';
        }
    }

    // =========================================================
    // EXPORT TO GLOBAL NAMESPACE
    // =========================================================

    global.M2SOffline = {
        hasReferenceData,
        getReferenceData,
        renderOfflineFlightForm,
        initOfflineFormHandlers,
        updatePendingIndicator,
        getPendingFlightCount
    };

    console.log('[M2SOffline] Module loaded');

})(window);
