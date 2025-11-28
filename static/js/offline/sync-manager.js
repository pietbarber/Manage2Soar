/**
 * Offline Sync Manager for Manage2Soar
 *
 * Handles background sync of offline flight data with the server.
 * Works with IndexedDB storage and service worker Background Sync API.
 *
 * Part of Issue #315: PWA Fully-offline Logsheet data entry
 */

class M2SSyncManager {
    constructor(db) {
        this.db = db;
        this.syncInProgress = false;
        this.lastSyncAttempt = null;
        this.syncListeners = [];

        // API endpoints
        this.endpoints = {
            referenceData: '/api/offline/reference-data/',
            flightSync: '/api/offline/flights/sync/',
            syncStatus: '/api/offline/sync-status/'
        };

        // Sync configuration
        this.config = {
            maxRetries: 3,
            retryDelayMs: 5000,
            batchSize: 10,
            conflictResolutionStrategy: 'server-wins' // 'server-wins', 'client-wins', 'manual'
        };
    }

    /**
     * Register a listener for sync events
     * @param {Function} callback - Function to call on sync events
     */
    addSyncListener(callback) {
        this.syncListeners.push(callback);
    }

    /**
     * Remove a sync listener
     * @param {Function} callback - The callback to remove
     */
    removeSyncListener(callback) {
        this.syncListeners = this.syncListeners.filter(cb => cb !== callback);
    }

    /**
     * Notify all listeners of a sync event
     * @param {string} event - Event type: 'start', 'progress', 'complete', 'error', 'conflict'
     * @param {Object} data - Event data
     */
    notifySyncListeners(event, data) {
        this.syncListeners.forEach(callback => {
            try {
                callback(event, data);
            } catch (e) {
                console.error('Sync listener error:', e);
            }
        });
    }

    /**
     * Check if we're currently online
     * @returns {boolean}
     */
    isOnline() {
        return navigator.onLine;
    }

    /**
     * Queue a flight for later sync
     * @param {Object} flightData - The flight data to queue
     * @returns {Promise<number>} - The queue ID
     */
    async queueFlight(flightData) {
        // Generate idempotency key if not present
        if (!flightData.idempotencyKey) {
            flightData.idempotencyKey = this.generateIdempotencyKey();
        }

        // Add to sync queue
        const queueItem = {
            type: 'flight',
            action: flightData.id ? 'update' : 'create',
            data: flightData,
            idempotencyKey: flightData.idempotencyKey,
            retryCount: 0
        };

        const queueId = await this.db.addToSyncQueue(queueItem);

        // Also save to local flights store for UI display
        const localFlight = {
            ...flightData,
            syncStatus: 'pending',
            queueId: queueId,
            localId: flightData.localId || `local-${Date.now()}`
        };

        if (!localFlight.id) {
            // New flight - add to local store
            await this.db.addFlight(localFlight);
        } else {
            // Update existing flight
            await this.db.updateFlight(localFlight);
        }

        // Try to register for background sync
        await this.registerBackgroundSync();

        this.notifySyncListeners('queued', { queueId, flight: localFlight });

        return queueId;
    }

    /**
     * Generate a unique idempotency key for deduplication
     * @returns {string}
     */
    generateIdempotencyKey() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 15);
        return `flight-${timestamp}-${random}`;
    }

    /**
     * Register for background sync with service worker
     */
    async registerBackgroundSync() {
        if ('serviceWorker' in navigator && 'sync' in window.SyncManager) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('sync-flights');
                console.log('Background sync registered: sync-flights');
            } catch (e) {
                console.warn('Background sync registration failed:', e);
                // Fall back to immediate sync if online
                if (this.isOnline()) {
                    this.syncNow();
                }
            }
        } else if (this.isOnline()) {
            // Fallback for browsers without Background Sync
            this.syncNow();
        }
    }

    /**
     * Perform immediate sync of all pending items
     * @returns {Promise<Object>} - Sync result
     */
    async syncNow() {
        if (this.syncInProgress) {
            console.log('Sync already in progress');
            return { status: 'in-progress' };
        }

        if (!this.isOnline()) {
            console.log('Cannot sync - offline');
            return { status: 'offline' };
        }

        this.syncInProgress = true;
        this.lastSyncAttempt = new Date();
        this.notifySyncListeners('start', {});

        const result = {
            status: 'complete',
            synced: 0,
            failed: 0,
            conflicts: [],
            errors: []
        };

        try {
            // Get pending items from sync queue
            const pendingItems = await this.db.getSyncQueue();
            const totalItems = pendingItems.length;

            if (totalItems === 0) {
                this.syncInProgress = false;
                this.notifySyncListeners('complete', result);
                return result;
            }

            // Process items in batches
            for (let i = 0; i < totalItems; i += this.config.batchSize) {
                const batch = pendingItems.slice(i, i + this.config.batchSize);
                const batchResult = await this.syncBatch(batch);

                result.synced += batchResult.synced;
                result.failed += batchResult.failed;
                result.conflicts.push(...batchResult.conflicts);
                result.errors.push(...batchResult.errors);

                this.notifySyncListeners('progress', {
                    processed: i + batch.length,
                    total: totalItems,
                    synced: result.synced,
                    failed: result.failed
                });
            }

        } catch (e) {
            console.error('Sync error:', e);
            result.status = 'error';
            result.errors.push({ message: e.message });
            this.notifySyncListeners('error', { error: e });
        } finally {
            this.syncInProgress = false;
        }

        this.notifySyncListeners('complete', result);
        return result;
    }

    /**
     * Sync a batch of items
     * @param {Array} batch - Items to sync
     * @returns {Promise<Object>} - Batch result
     */
    async syncBatch(batch) {
        const result = {
            synced: 0,
            failed: 0,
            conflicts: [],
            errors: []
        };

        // Group by type for efficient API calls
        const flightItems = batch.filter(item => item.type === 'flight');

        if (flightItems.length > 0) {
            const flightResult = await this.syncFlights(flightItems);
            result.synced += flightResult.synced;
            result.failed += flightResult.failed;
            result.conflicts.push(...flightResult.conflicts);
            result.errors.push(...flightResult.errors);
        }

        return result;
    }

    /**
     * Sync flight items to server
     * @param {Array} items - Flight items to sync
     * @returns {Promise<Object>}
     */
    async syncFlights(items) {
        const result = {
            synced: 0,
            failed: 0,
            conflicts: [],
            errors: []
        };

        try {
            // Prepare request payload
            const payload = {
                flights: items.map(item => ({
                    idempotencyKey: item.idempotencyKey,
                    action: item.action,
                    data: item.data
                }))
            };

            // Get CSRF token
            const csrfToken = this.getCSRFToken();

            const response = await fetch(this.endpoints.flightSync, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }

            const serverResult = await response.json();

            // Process results for each flight
            for (const itemResult of serverResult.results) {
                const queueItem = items.find(i => i.idempotencyKey === itemResult.idempotencyKey);

                if (itemResult.status === 'success') {
                    // Mark as synced in queue
                    await this.db.markSynced(queueItem.id);

                    // Update local flight with server ID and synced status
                    if (queueItem.data.localId) {
                        const localFlights = await this.db.getFlightsByLogsheet(queueItem.data.logsheet_id);
                        const localFlight = localFlights.find(f => f.localId === queueItem.data.localId);
                        if (localFlight) {
                            await this.db.updateFlight({
                                ...localFlight,
                                id: itemResult.serverId,
                                syncStatus: 'synced'
                            });
                        }
                    }

                    result.synced++;

                } else if (itemResult.status === 'conflict') {
                    // Handle conflict based on strategy
                    await this.handleConflict(queueItem, itemResult);
                    result.conflicts.push({
                        idempotencyKey: itemResult.idempotencyKey,
                        reason: itemResult.reason,
                        serverData: itemResult.serverData
                    });

                } else if (itemResult.status === 'duplicate') {
                    // Already synced - just mark as done
                    await this.db.markSynced(queueItem.id);
                    result.synced++;

                } else {
                    // Failed
                    queueItem.retryCount++;
                    queueItem.lastError = itemResult.error;

                    if (queueItem.retryCount >= this.config.maxRetries) {
                        queueItem.status = 'failed';
                        result.failed++;
                        result.errors.push({
                            idempotencyKey: itemResult.idempotencyKey,
                            error: itemResult.error
                        });
                    }

                    // Update queue item with retry count
                    await this.updateQueueItem(queueItem);
                }
            }

        } catch (e) {
            console.error('Flight sync error:', e);
            // Mark all items for retry
            for (const item of items) {
                item.retryCount++;
                if (item.retryCount >= this.config.maxRetries) {
                    result.failed++;
                } else {
                    await this.updateQueueItem(item);
                }
            }
            result.errors.push({ message: e.message });
        }

        return result;
    }

    /**
     * Handle a sync conflict
     * @param {Object} queueItem - The conflicting queue item
     * @param {Object} conflictInfo - Info about the conflict from server
     */
    async handleConflict(queueItem, conflictInfo) {
        switch (this.config.conflictResolutionStrategy) {
            case 'server-wins':
                // Accept server version, discard local changes
                await this.db.markSynced(queueItem.id);
                if (conflictInfo.serverData) {
                    await this.db.updateFlight({
                        ...conflictInfo.serverData,
                        syncStatus: 'synced'
                    });
                }
                break;

            case 'client-wins':
                // Force push local version (would need server support)
                queueItem.data.forceOverwrite = true;
                await this.updateQueueItem(queueItem);
                break;

            case 'manual':
                // Mark for manual resolution
                queueItem.status = 'conflict';
                queueItem.conflictInfo = conflictInfo;
                await this.updateQueueItem(queueItem);
                this.notifySyncListeners('conflict', { queueItem, conflictInfo });
                break;
        }
    }

    /**
     * Update a queue item in IndexedDB
     * @param {Object} queueItem - The item to update
     */
    async updateQueueItem(queueItem) {
        const db = await this.db.getDatabase();
        const tx = db.transaction('syncQueue', 'readwrite');
        const store = tx.objectStore('syncQueue');
        await store.put(queueItem);
    }

    /**
     * Get CSRF token from cookie
     * @returns {string}
     */
    getCSRFToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    }

    /**
     * Fetch and cache reference data (members, gliders, etc)
     * @returns {Promise<Object>}
     */
    async refreshReferenceData() {
        if (!this.isOnline()) {
            console.log('Cannot refresh reference data - offline');
            return { status: 'offline' };
        }

        try {
            const response = await fetch(this.endpoints.referenceData, {
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }

            const data = await response.json();

            // Store each type of reference data
            if (data.members) {
                await this.db.bulkAddMembers(data.members);
            }
            if (data.gliders) {
                await this.db.bulkAddGliders(data.gliders);
            }
            if (data.towplanes) {
                await this.db.bulkAddTowplanes(data.towplanes);
            }
            if (data.airfields) {
                await this.db.bulkAddAirfields(data.airfields);
            }

            // Update cache timestamp
            await this.db.setMetadata('referenceDataCached', new Date().toISOString());
            await this.db.setMetadata('referenceDataVersion', data.version || 1);

            return { status: 'success', cached: new Date() };

        } catch (e) {
            console.error('Reference data refresh error:', e);
            return { status: 'error', error: e.message };
        }
    }

    /**
     * Get sync status for UI display
     * @returns {Promise<Object>}
     */
    async getSyncStatus() {
        const pendingItems = await this.db.getSyncQueue();
        const pendingFlights = pendingItems.filter(i => i.type === 'flight' && i.status !== 'failed');
        const failedFlights = pendingItems.filter(i => i.type === 'flight' && i.status === 'failed');
        const conflictFlights = pendingItems.filter(i => i.type === 'flight' && i.status === 'conflict');

        const referenceDataCached = await this.db.getMetadata('referenceDataCached');

        return {
            online: this.isOnline(),
            syncInProgress: this.syncInProgress,
            lastSyncAttempt: this.lastSyncAttempt,
            pendingCount: pendingFlights.length,
            failedCount: failedFlights.length,
            conflictCount: conflictFlights.length,
            referenceDataCached: referenceDataCached,
            hasUnsynced: pendingFlights.length > 0 || failedFlights.length > 0 || conflictFlights.length > 0
        };
    }

    /**
     * Clear synced items from the queue
     * @returns {Promise<number>} - Number of items cleared
     */
    async clearSyncedItems() {
        return await this.db.clearSynced();
    }

    /**
     * Retry failed sync items
     * @returns {Promise<Object>}
     */
    async retryFailed() {
        const pendingItems = await this.db.getSyncQueue();
        const failedItems = pendingItems.filter(i => i.status === 'failed');

        // Reset retry count for failed items
        for (const item of failedItems) {
            item.retryCount = 0;
            item.status = 'pending';
            await this.updateQueueItem(item);
        }

        // Trigger sync
        return await this.syncNow();
    }
}

// Export for use in service worker and main app
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { M2SSyncManager };
}
