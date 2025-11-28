/**
 * Manage2Soar Offline IndexedDB Module (Non-ES-Module Bundle)
 *
 * Provides local storage for offline logsheet data entry.
 * This version uses a global namespace (window.M2SIndexedDB) instead of ES modules
 * to avoid CORS issues when loading from GCS.
 *
 * Schema Version History:
 * - v1: Initial schema with all core tables
 */

(function (global) {
    'use strict';

    const DB_NAME = 'manage2soar-offline';
    const DB_VERSION = 1;

    // Database instance (singleton)
    let dbInstance = null;

    /**
     * Open or create the IndexedDB database
     * @returns {Promise<IDBDatabase>}
     */
    async function openDatabase() {
        if (dbInstance) {
            return dbInstance;
        }

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                console.error('[IndexedDB] Failed to open database:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                dbInstance = request.result;
                console.log('[IndexedDB] Database opened successfully');
                resolve(dbInstance);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                console.log(`[IndexedDB] Upgrading from v${event.oldVersion} to v${event.newVersion}`);

                if (event.oldVersion < 1) {
                    createSchemaV1(db);
                }
            };
        });
    }

    /**
     * Create schema version 1
     * @param {IDBDatabase} db
     */
    function createSchemaV1(db) {
        // PENDING FLIGHTS
        const pendingFlights = db.createObjectStore('pendingFlights', {
            keyPath: 'localId',
            autoIncrement: true
        });
        pendingFlights.createIndex('serverId', 'serverId', { unique: false });
        pendingFlights.createIndex('logsheetId', 'logsheetId', { unique: false });
        pendingFlights.createIndex('syncStatus', 'syncStatus', { unique: false });
        pendingFlights.createIndex('idempotencyKey', 'idempotencyKey', { unique: true });

        // MEMBERS
        const members = db.createObjectStore('members', { keyPath: 'id' });
        members.createIndex('lastName', 'lastName', { unique: false });
        members.createIndex('isActive', 'isActive', { unique: false });
        members.createIndex('isInstructor', 'isInstructor', { unique: false });
        members.createIndex('isTowpilot', 'isTowpilot', { unique: false });

        // GLIDERS
        const gliders = db.createObjectStore('gliders', { keyPath: 'id' });
        gliders.createIndex('nNumber', 'nNumber', { unique: true });
        gliders.createIndex('isActive', 'isActive', { unique: false });
        gliders.createIndex('clubOwned', 'clubOwned', { unique: false });

        // TOWPLANES
        const towplanes = db.createObjectStore('towplanes', { keyPath: 'id' });
        towplanes.createIndex('nNumber', 'nNumber', { unique: true });
        towplanes.createIndex('isActive', 'isActive', { unique: false });

        // AIRFIELDS
        const airfields = db.createObjectStore('airfields', { keyPath: 'id' });
        airfields.createIndex('identifier', 'identifier', { unique: true });
        airfields.createIndex('isActive', 'isActive', { unique: false });

        // LOGSHEETS
        const logsheets = db.createObjectStore('logsheets', { keyPath: 'id' });
        logsheets.createIndex('logDate', 'logDate', { unique: false });
        logsheets.createIndex('airfieldId', 'airfieldId', { unique: false });

        // SYNC QUEUE
        const syncQueue = db.createObjectStore('syncQueue', {
            keyPath: 'id',
            autoIncrement: true
        });
        syncQueue.createIndex('type', 'type', { unique: false });
        syncQueue.createIndex('status', 'status', { unique: false });
        syncQueue.createIndex('createdAt', 'createdAt', { unique: false });

        // METADATA
        db.createObjectStore('metadata', { keyPath: 'key' });

        console.log('[IndexedDB] Schema v1 created successfully');
    }

    /**
     * Close the database connection
     */
    function closeDatabase() {
        if (dbInstance) {
            dbInstance.close();
            dbInstance = null;
        }
    }

    // =========================================================
    // GENERIC CRUD HELPERS
    // =========================================================

    async function put(storeName, data) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.put(data);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function get(storeName, key) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function getAll(storeName) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function getByIndex(storeName, indexName, value) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const index = store.index(indexName);
            const request = index.getAll(value);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function remove(storeName, key) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async function clear(storeName) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);
            const request = store.clear();
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async function count(storeName) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readonly');
            const store = tx.objectStore(storeName);
            const request = store.count();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    // =========================================================
    // PENDING FLIGHTS HELPERS
    // =========================================================

    const SyncStatus = {
        PENDING: 'pending',
        SYNCING: 'syncing',
        SYNCED: 'synced',
        CONFLICT: 'conflict',
        ERROR: 'error'
    };

    function generateIdempotencyKey() {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 15);
        return `flight-${timestamp}-${random}`;
    }

    async function createPendingFlight(flightData, logsheetId) {
        const pendingFlight = {
            ...flightData,
            logsheetId: logsheetId,
            serverId: null,
            syncStatus: SyncStatus.PENDING,
            idempotencyKey: generateIdempotencyKey(),
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            syncAttempts: 0,
            lastSyncError: null
        };

        const localId = await put('pendingFlights', pendingFlight);
        console.log(`[IndexedDB] Created pending flight ${localId}`);
        return localId;
    }

    async function getPendingFlights() {
        return getByIndex('pendingFlights', 'syncStatus', SyncStatus.PENDING);
    }

    async function getFlightsByLogsheet(logsheetId) {
        return getByIndex('pendingFlights', 'logsheetId', logsheetId);
    }

    async function getPendingFlightCount() {
        const pending = await getPendingFlights();
        return pending.length;
    }

    async function updateFlightSyncStatus(localId, status, extra = {}) {
        const flight = await get('pendingFlights', localId);
        if (flight) {
            flight.syncStatus = status;
            flight.updatedAt = new Date().toISOString();
            Object.assign(flight, extra);
            await put('pendingFlights', flight);
        }
    }

    async function markFlightSynced(localId, serverId) {
        await updateFlightSyncStatus(localId, SyncStatus.SYNCED, { serverId });
        console.log(`[IndexedDB] Flight ${localId} synced as server ID ${serverId}`);
    }

    async function markFlightConflict(localId, conflictData) {
        await updateFlightSyncStatus(localId, SyncStatus.CONFLICT, {
            conflictData,
            lastSyncError: 'Conflict detected'
        });
    }

    async function markFlightError(localId, error) {
        const flight = await get('pendingFlights', localId);
        if (flight) {
            await updateFlightSyncStatus(localId, SyncStatus.ERROR, {
                lastSyncError: error,
                syncAttempts: (flight.syncAttempts || 0) + 1
            });
        }
    }

    /**
     * Create a pending edit for an existing server flight
     * @param {number} serverId - The server flight ID being edited
     * @param {object} flightData - The edited flight data
     * @param {number} logsheetId - ID of the parent logsheet
     * @returns {Promise<number>} - Local ID of the pending edit
     */
    async function createPendingEdit(serverId, flightData, logsheetId) {
        // Check if we already have a pending edit for this flight
        const existing = await getByIndex('pendingFlights', 'serverId', serverId);
        const pendingEdit = existing.find(f => f.syncStatus === SyncStatus.PENDING);

        if (pendingEdit) {
            // Update the existing pending edit
            pendingEdit.flightData = flightData;
            pendingEdit.updatedAt = new Date().toISOString();
            await put('pendingFlights', pendingEdit);
            console.log(`[IndexedDB] Updated existing pending edit ${pendingEdit.localId} for server flight ${serverId}`);
            return pendingEdit.localId;
        }

        // Create a new pending edit
        const newEdit = {
            ...flightData,
            logsheetId: logsheetId,
            serverId: serverId,  // This is the key difference - we have a server ID
            syncStatus: SyncStatus.PENDING,
            editType: 'update',  // Mark as an edit, not a new flight
            idempotencyKey: generateIdempotencyKey(),
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            syncAttempts: 0,
            lastSyncError: null
        };

        const localId = await put('pendingFlights', newEdit);
        console.log(`[IndexedDB] Created pending edit ${localId} for server flight ${serverId}`);
        return localId;
    }

    /**
     * Get all pending edits (flights with serverId that need syncing)
     * @returns {Promise<object[]>}
     */
    async function getPendingEdits() {
        const pending = await getPendingFlights();
        return pending.filter(f => f.serverId !== null && f.editType === 'update');
    }

    /**
     * Get all pending new flights (flights without serverId)
     * @returns {Promise<object[]>}
     */
    async function getPendingNewFlights() {
        const pending = await getPendingFlights();
        return pending.filter(f => f.serverId === null || f.editType !== 'update');
    }

    /**
     * Create a pending operation (launch/landing) for an existing flight
     * @param {string} operationType - 'launch' or 'landing'
     * @param {number} flightId - The server flight ID
     * @param {string} time - The time value (HH:MM format)
     * @param {number} logsheetId - ID of the parent logsheet
     * @returns {Promise<number>} - Local ID of the pending operation
     */
    async function createPendingOperation(operationType, flightId, time, logsheetId) {
        const operation = {
            operationType: operationType,  // 'launch' or 'landing'
            serverId: flightId,
            time: time,
            logsheetId: logsheetId,
            syncStatus: SyncStatus.PENDING,
            editType: 'operation',  // Distinguish from flight edits
            idempotencyKey: generateIdempotencyKey(),
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            syncAttempts: 0,
            lastSyncError: null
        };

        const localId = await put('pendingFlights', operation);
        console.log(`[IndexedDB] Created pending ${operationType} operation ${localId} for flight ${flightId}`);
        return localId;
    }

    /**
     * Get all pending operations (launch/landing)
     * @returns {Promise<object[]>}
     */
    async function getPendingOperations() {
        const pending = await getPendingFlights();
        return pending.filter(f => f.editType === 'operation');
    }

    // =========================================================
    // REFERENCE DATA HELPERS
    // =========================================================

    async function bulkPut(storeName, records) {
        const db = await openDatabase();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readwrite');
            const store = tx.objectStore(storeName);

            let completed = 0;
            const total = records.length;

            if (total === 0) {
                resolve();
                return;
            }

            for (const record of records) {
                const request = store.put(record);
                request.onsuccess = () => {
                    completed++;
                    if (completed === total) {
                        resolve();
                    }
                };
                request.onerror = () => {
                    reject(request.error);
                };
            }

            tx.onerror = () => reject(tx.error);
        });
    }

    async function refreshReferenceData(data) {
        const now = new Date().toISOString();

        if (data.members) {
            await clear('members');
            await bulkPut('members', data.members);
            await put('metadata', { key: 'membersLastSync', value: now });
        }

        if (data.gliders) {
            await clear('gliders');
            await bulkPut('gliders', data.gliders);
            await put('metadata', { key: 'glidersLastSync', value: now });
        }

        if (data.towplanes) {
            await clear('towplanes');
            await bulkPut('towplanes', data.towplanes);
            await put('metadata', { key: 'towplanesLastSync', value: now });
        }

        if (data.airfields) {
            await clear('airfields');
            await bulkPut('airfields', data.airfields);
            await put('metadata', { key: 'airfieldsLastSync', value: now });
        }

        console.log('[IndexedDB] Reference data refreshed');
    }

    async function getLastSyncTime(dataType) {
        const meta = await get('metadata', `${dataType}LastSync`);
        return meta ? meta.value : null;
    }

    // =========================================================
    // UTILITY FUNCTIONS
    // =========================================================

    function isIndexedDBAvailable() {
        return 'indexedDB' in window;
    }

    async function getDatabaseStats() {
        const stats = {
            pendingFlights: await count('pendingFlights'),
            members: await count('members'),
            gliders: await count('gliders'),
            towplanes: await count('towplanes'),
            airfields: await count('airfields'),
            syncQueue: await count('syncQueue')
        };

        const pending = await getPendingFlights();
        stats.pendingFlightCount = pending.length;

        return stats;
    }

    async function deleteDatabase() {
        closeDatabase();
        return new Promise((resolve, reject) => {
            const request = indexedDB.deleteDatabase(DB_NAME);
            request.onsuccess = () => {
                console.log('[IndexedDB] Database deleted');
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    // =========================================================
    // EXPORT TO GLOBAL NAMESPACE
    // =========================================================

    global.M2SIndexedDB = {
        // Database
        openDatabase,
        closeDatabase,
        isIndexedDBAvailable,
        getDatabaseStats,
        deleteDatabase,

        // CRUD
        put,
        get,
        getAll,
        getByIndex,
        remove,
        clear,
        count,
        bulkPut,

        // Pending Flights
        SyncStatus,
        generateIdempotencyKey,
        createPendingFlight,
        createPendingEdit,
        createPendingOperation,
        getPendingFlights,
        getPendingEdits,
        getPendingNewFlights,
        getPendingOperations,
        getFlightsByLogsheet,
        getPendingFlightCount,
        updateFlightSyncStatus,
        markFlightSynced,
        markFlightConflict,
        markFlightError,

        // Reference Data
        refreshReferenceData,
        getLastSyncTime
    };

    console.log('[M2SIndexedDB] Module loaded');

})(window);
