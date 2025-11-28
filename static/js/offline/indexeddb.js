/**
 * Manage2Soar Offline IndexedDB Module
 *
 * Provides local storage for offline logsheet data entry.
 * Stores flights, members, gliders, towplanes, and airfields.
 *
 * Schema Version History:
 * - v1: Initial schema with all core tables
 */

const DB_NAME = 'manage2soar-offline';
const DB_VERSION = 1;

// Database instance (singleton)
let dbInstance = null;

/**
 * Open or create the IndexedDB database
 * @returns {Promise<IDBDatabase>}
 */
export async function openDatabase() {
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

            // Create object stores based on version
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
    // =====================================================
    // PENDING FLIGHTS - Flights created/edited offline
    // =====================================================
    const pendingFlights = db.createObjectStore('pendingFlights', {
        keyPath: 'localId',
        autoIncrement: true
    });
    // For finding flights by their server ID (if synced then edited)
    pendingFlights.createIndex('serverId', 'serverId', { unique: false });
    // For filtering by logsheet
    pendingFlights.createIndex('logsheetId', 'logsheetId', { unique: false });
    // For finding flights by sync status
    pendingFlights.createIndex('syncStatus', 'syncStatus', { unique: false });
    // For idempotency - prevent duplicate submissions
    pendingFlights.createIndex('idempotencyKey', 'idempotencyKey', { unique: true });

    // =====================================================
    // MEMBERS - Cached member list for offline lookups
    // =====================================================
    const members = db.createObjectStore('members', {
        keyPath: 'id'
    });
    members.createIndex('lastName', 'lastName', { unique: false });
    members.createIndex('isActive', 'isActive', { unique: false });
    members.createIndex('isInstructor', 'isInstructor', { unique: false });
    members.createIndex('isTowpilot', 'isTowpilot', { unique: false });

    // =====================================================
    // GLIDERS - Cached glider list
    // =====================================================
    const gliders = db.createObjectStore('gliders', {
        keyPath: 'id'
    });
    gliders.createIndex('nNumber', 'nNumber', { unique: true });
    gliders.createIndex('isActive', 'isActive', { unique: false });
    gliders.createIndex('clubOwned', 'clubOwned', { unique: false });

    // =====================================================
    // TOWPLANES - Cached towplane list
    // =====================================================
    const towplanes = db.createObjectStore('towplanes', {
        keyPath: 'id'
    });
    towplanes.createIndex('nNumber', 'nNumber', { unique: true });
    towplanes.createIndex('isActive', 'isActive', { unique: false });

    // =====================================================
    // AIRFIELDS - Cached airfield list
    // =====================================================
    const airfields = db.createObjectStore('airfields', {
        keyPath: 'id'
    });
    airfields.createIndex('identifier', 'identifier', { unique: true });
    airfields.createIndex('isActive', 'isActive', { unique: false });

    // =====================================================
    // LOGSHEETS - Cached logsheet metadata
    // =====================================================
    const logsheets = db.createObjectStore('logsheets', {
        keyPath: 'id'
    });
    logsheets.createIndex('logDate', 'logDate', { unique: false });
    logsheets.createIndex('airfieldId', 'airfieldId', { unique: false });

    // =====================================================
    // SYNC QUEUE - Track what needs to be synced
    // =====================================================
    const syncQueue = db.createObjectStore('syncQueue', {
        keyPath: 'id',
        autoIncrement: true
    });
    syncQueue.createIndex('type', 'type', { unique: false });
    syncQueue.createIndex('status', 'status', { unique: false });
    syncQueue.createIndex('createdAt', 'createdAt', { unique: false });

    // =====================================================
    // METADATA - Store sync timestamps, version info
    // =====================================================
    db.createObjectStore('metadata', {
        keyPath: 'key'
    });

    console.log('[IndexedDB] Schema v1 created successfully');
}

/**
 * Close the database connection
 */
export function closeDatabase() {
    if (dbInstance) {
        dbInstance.close();
        dbInstance = null;
    }
}

// =========================================================
// GENERIC CRUD HELPERS
// =========================================================

/**
 * Add or update a record in an object store
 * @param {string} storeName - Name of the object store
 * @param {object} data - Data to store
 * @returns {Promise<IDBValidKey>}
 */
export async function put(storeName, data) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const request = store.put(data);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/**
 * Get a record by key
 * @param {string} storeName - Name of the object store
 * @param {IDBValidKey} key - Primary key
 * @returns {Promise<object|undefined>}
 */
export async function get(storeName, key) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const request = store.get(key);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/**
 * Get all records from an object store
 * @param {string} storeName - Name of the object store
 * @returns {Promise<object[]>}
 */
export async function getAll(storeName) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const request = store.getAll();

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

/**
 * Get records by index value
 * @param {string} storeName - Name of the object store
 * @param {string} indexName - Name of the index
 * @param {IDBValidKey} value - Index value to match
 * @returns {Promise<object[]>}
 */
export async function getByIndex(storeName, indexName, value) {
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

/**
 * Delete a record by key
 * @param {string} storeName - Name of the object store
 * @param {IDBValidKey} key - Primary key
 * @returns {Promise<void>}
 */
export async function remove(storeName, key) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const request = store.delete(key);

        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

/**
 * Clear all records from an object store
 * @param {string} storeName - Name of the object store
 * @returns {Promise<void>}
 */
export async function clear(storeName) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const request = store.clear();

        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

/**
 * Count records in an object store
 * @param {string} storeName - Name of the object store
 * @returns {Promise<number>}
 */
export async function count(storeName) {
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

/**
 * Sync status constants for pending flights
 */
export const SyncStatus = {
    PENDING: 'pending',      // Not yet synced
    SYNCING: 'syncing',      // Currently being synced
    SYNCED: 'synced',        // Successfully synced
    CONFLICT: 'conflict',    // Conflict detected, needs resolution
    ERROR: 'error'           // Sync failed
};

/**
 * Generate a unique idempotency key for a flight
 * @returns {string}
 */
export function generateIdempotencyKey() {
    const timestamp = Date.now();
    const random = Math.random().toString(36).substring(2, 15);
    return `flight-${timestamp}-${random}`;
}

/**
 * Create a new pending flight
 * @param {object} flightData - Flight form data
 * @param {number} logsheetId - ID of the parent logsheet
 * @returns {Promise<number>} - Local ID of the created flight
 */
export async function createPendingFlight(flightData, logsheetId) {
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

/**
 * Get all pending (unsynced) flights
 * @returns {Promise<object[]>}
 */
export async function getPendingFlights() {
    return getByIndex('pendingFlights', 'syncStatus', SyncStatus.PENDING);
}

/**
 * Get all flights for a specific logsheet
 * @param {number} logsheetId
 * @returns {Promise<object[]>}
 */
export async function getFlightsByLogsheet(logsheetId) {
    return getByIndex('pendingFlights', 'logsheetId', logsheetId);
}

/**
 * Get count of pending flights
 * @returns {Promise<number>}
 */
export async function getPendingFlightCount() {
    const pending = await getPendingFlights();
    return pending.length;
}

/**
 * Update a pending flight's sync status
 * @param {number} localId - Local flight ID
 * @param {string} status - New sync status
 * @param {object} [extra] - Extra data to merge (e.g., serverId, error)
 */
export async function updateFlightSyncStatus(localId, status, extra = {}) {
    const flight = await get('pendingFlights', localId);
    if (flight) {
        flight.syncStatus = status;
        flight.updatedAt = new Date().toISOString();
        Object.assign(flight, extra);
        await put('pendingFlights', flight);
    }
}

/**
 * Mark a flight as synced
 * @param {number} localId - Local flight ID
 * @param {number} serverId - Server-assigned flight ID
 */
export async function markFlightSynced(localId, serverId) {
    await updateFlightSyncStatus(localId, SyncStatus.SYNCED, { serverId });
    console.log(`[IndexedDB] Flight ${localId} synced as server ID ${serverId}`);
}

/**
 * Mark a flight as having a conflict
 * @param {number} localId - Local flight ID
 * @param {object} conflictData - Details about the conflict
 */
export async function markFlightConflict(localId, conflictData) {
    await updateFlightSyncStatus(localId, SyncStatus.CONFLICT, {
        conflictData,
        lastSyncError: 'Conflict detected'
    });
}

/**
 * Mark a flight sync as failed
 * @param {number} localId - Local flight ID
 * @param {string} error - Error message
 */
export async function markFlightError(localId, error) {
    const flight = await get('pendingFlights', localId);
    if (flight) {
        await updateFlightSyncStatus(localId, SyncStatus.ERROR, {
            lastSyncError: error,
            syncAttempts: (flight.syncAttempts || 0) + 1
        });
    }
}

// =========================================================
// REFERENCE DATA HELPERS
// =========================================================

/**
 * Bulk update reference data (members, gliders, etc.)
 * @param {string} storeName - Object store name
 * @param {object[]} records - Records to store
 * @returns {Promise<void>}
 */
export async function bulkPut(storeName, records) {
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

/**
 * Refresh all reference data from the server
 * @param {object} data - Object with members, gliders, towplanes, airfields arrays
 */
export async function refreshReferenceData(data) {
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

/**
 * Get last sync timestamp for a data type
 * @param {string} dataType - e.g., 'members', 'gliders'
 * @returns {Promise<string|null>}
 */
export async function getLastSyncTime(dataType) {
    const meta = await get('metadata', `${dataType}LastSync`);
    return meta ? meta.value : null;
}

// =========================================================
// SYNC QUEUE HELPERS
// =========================================================

/**
 * Add an item to the sync queue
 * @param {string} type - Type of operation (e.g., 'createFlight', 'updateFlight')
 * @param {object} data - Data to sync
 * @returns {Promise<number>}
 */
export async function addToSyncQueue(type, data) {
    const item = {
        type,
        data,
        status: 'pending',
        createdAt: new Date().toISOString(),
        attempts: 0,
        lastError: null
    };
    return put('syncQueue', item);
}

/**
 * Get all pending sync items
 * @returns {Promise<object[]>}
 */
export async function getPendingSyncItems() {
    return getByIndex('syncQueue', 'status', 'pending');
}

/**
 * Mark a sync item as completed
 * @param {number} id - Sync queue item ID
 */
export async function markSyncItemComplete(id) {
    const item = await get('syncQueue', id);
    if (item) {
        item.status = 'completed';
        item.completedAt = new Date().toISOString();
        await put('syncQueue', item);
    }
}

/**
 * Mark a sync item as failed
 * @param {number} id - Sync queue item ID
 * @param {string} error - Error message
 */
export async function markSyncItemFailed(id, error) {
    const item = await get('syncQueue', id);
    if (item) {
        item.status = 'failed';
        item.lastError = error;
        item.attempts++;
        await put('syncQueue', item);
    }
}

// =========================================================
// UTILITY FUNCTIONS
// =========================================================

/**
 * Check if IndexedDB is available
 * @returns {boolean}
 */
export function isIndexedDBAvailable() {
    return 'indexedDB' in window;
}

/**
 * Get database statistics
 * @returns {Promise<object>}
 */
export async function getDatabaseStats() {
    const stats = {
        pendingFlights: await count('pendingFlights'),
        members: await count('members'),
        gliders: await count('gliders'),
        towplanes: await count('towplanes'),
        airfields: await count('airfields'),
        syncQueue: await count('syncQueue')
    };

    // Get pending flight count specifically
    const pending = await getPendingFlights();
    stats.pendingFlightCount = pending.length;

    return stats;
}

/**
 * Delete the entire database (use with caution!)
 * @returns {Promise<void>}
 */
export async function deleteDatabase() {
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
