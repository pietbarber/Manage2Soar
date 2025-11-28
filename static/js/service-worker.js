/**
 * Manage2Soar Service Worker
 *
 * Level 1: Page Caching - Caches navigation pages for faster loads
 * Level 2: Offline fallback - Shows friendly offline page when network unavailable
 * Level 3: Offline logsheet - IndexedDB for offline flight data entry with Background Sync
 *
 * Note: Static assets (CSS, JS, images) are served from GCS with proper caching
 * headers, so we don't cache them here. We focus on HTML pages and the offline
 * fallback experience.
 */

const CACHE_NAME = 'manage2soar-v3';
const OFFLINE_URL = '/offline/';

// Pages to cache on install - these are served by Django, not GCS
const CORE_PAGES = [
    '/',
    '/offline/',
    '/manifest.json',
];

// Logsheet pages to cache for offline access
const LOGSHEET_PAGES = [
    '/logsheet/',
];

// API endpoints that should work offline via IndexedDB
const OFFLINE_APIS = [
    '/logsheet/api/offline/reference-data/',
    '/logsheet/api/offline/flights/sync/',
    '/logsheet/api/offline/sync-status/',
];

// Import IndexedDB module for offline data management
// Note: This uses importScripts for service worker compatibility
// The actual module is loaded dynamically to avoid bundling issues
let M2SOfflineDB = null;
let M2SSyncManager = null;
let offlineDB = null;
let syncManager = null;

// Initialize offline modules (lazy loading)
async function initOfflineModules() {
    if (offlineDB) return;

    try {
        // Import the modules
        // Using dynamic import for service worker context
        importScripts('/static/js/offline/indexeddb.js');
        importScripts('/static/js/offline/sync-manager.js');

        // Initialize database and sync manager
        if (typeof M2SOfflineDB !== 'undefined') {
            offlineDB = new M2SOfflineDB();
            await offlineDB.init();

            if (typeof M2SSyncManager !== 'undefined') {
                syncManager = new M2SSyncManager(offlineDB);
            }

            console.log('[ServiceWorker] Offline modules initialized');
        }
    } catch (e) {
        console.warn('[ServiceWorker] Failed to initialize offline modules:', e);
    }
}

// Install event - cache core pages
self.addEventListener('install', (event) => {
    console.log('[ServiceWorker] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[ServiceWorker] Caching core pages');
                // Cache core pages and logsheet pages
                const allPages = [...CORE_PAGES, ...LOGSHEET_PAGES];
                return cache.addAll(allPages);
            })
            .then(() => {
                console.log('[ServiceWorker] Install complete');
                return self.skipWaiting();
            })
            .catch((error) => {
                console.warn('[ServiceWorker] Install failed:', error);
                // Re-throw to prevent broken service worker from activating
                throw error;
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[ServiceWorker] Activating...');
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => {
                            console.log('[ServiceWorker] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                console.log('[ServiceWorker] Activate complete');
                // Take control of all pages immediately
                return self.clients.claim();
            })
    );
});

// Fetch event - serve from cache, fall back to network, then offline page
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Only handle GET requests for caching
    // POST requests for offline API are handled separately
    if (request.method !== 'GET') {
        // Check if this is an offline API call that should be queued
        if (isOfflineApiRequest(url.pathname) && request.method === 'POST') {
            event.respondWith(handleOfflineApiPost(request));
        }
        return;
    }

    // Skip cross-origin requests (CDNs, etc.)
    if (url.origin !== location.origin) {
        return;
    }

    // Check if this is an offline API endpoint
    if (isOfflineApiRequest(url.pathname)) {
        event.respondWith(handleOfflineApiGet(request, url));
        return;
    }

    // For navigation requests (HTML pages), use network-first strategy
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    // Cache successful responses for offline use
                    if (response.ok) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    // Network failed - try cache, then offline page
                    return caches.match(request)
                        .then((cachedResponse) => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            // Return offline page
                            return caches.match(OFFLINE_URL);
                        });
                })
        );
        return;
    }

    // For non-navigation requests (API calls, etc.), pass through to network
    // Static assets are served from GCS with proper caching headers
    event.respondWith(
        fetch(request).catch(() => {
            // Network failed for non-navigation request
            return new Response('Service unavailable', {
                status: 503,
                statusText: 'Service Unavailable',
                headers: { 'Content-Type': 'text/plain' }
            });
        })
    );
});

// Check if request is to an offline API endpoint
function isOfflineApiRequest(pathname) {
    return OFFLINE_APIS.some(api => pathname.startsWith(api) || pathname === api.replace(/\/$/, ''));
}

// Handle GET requests for offline API (reference data, sync status)
async function handleOfflineApiGet(request, url) {
    try {
        // Try network first
        const response = await fetch(request);
        if (response.ok) {
            // Cache reference data in IndexedDB for offline use
            if (url.pathname.includes('reference-data')) {
                await initOfflineModules();
                const data = await response.clone().json();
                if (offlineDB && data.success) {
                    await cacheReferenceData(data);
                }
            }
            return response;
        }
        throw new Error('Network response not ok');
    } catch (e) {
        // Network failed - serve from IndexedDB if available
        console.log('[ServiceWorker] Network failed, serving from cache:', url.pathname);

        await initOfflineModules();

        if (url.pathname.includes('reference-data')) {
            return serveReferenceDataFromCache();
        } else if (url.pathname.includes('sync-status')) {
            return serveSyncStatusFromCache();
        }

        // Default offline response
        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'You are offline'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Handle POST requests for offline API (flight sync)
async function handleOfflineApiPost(request) {
    try {
        // Try network first
        const response = await fetch(request.clone());
        if (response.ok) {
            return response;
        }
        throw new Error('Network response not ok');
    } catch (e) {
        // Network failed - queue for background sync
        console.log('[ServiceWorker] Queuing POST for background sync');

        try {
            const data = await request.json();
            await initOfflineModules();

            if (syncManager && data.flights) {
                // Queue each flight for sync
                for (const flight of data.flights) {
                    await syncManager.queueFlight(flight.data);
                }

                // Register for background sync
                await self.registration.sync.register('sync-flights');

                return new Response(JSON.stringify({
                    success: true,
                    offline: true,
                    queued: data.flights.length,
                    message: 'Flights queued for sync when online'
                }), {
                    status: 202, // Accepted
                    headers: { 'Content-Type': 'application/json' }
                });
            }
        } catch (queueError) {
            console.error('[ServiceWorker] Failed to queue:', queueError);
        }

        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'Failed to queue for sync'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Cache reference data in IndexedDB
async function cacheReferenceData(data) {
    if (!offlineDB) return;

    try {
        if (data.members) {
            await offlineDB.bulkAddMembers(data.members);
        }
        if (data.gliders) {
            await offlineDB.bulkAddGliders(data.gliders);
        }
        if (data.towplanes) {
            await offlineDB.bulkAddTowplanes(data.towplanes);
        }
        if (data.airfields) {
            await offlineDB.bulkAddAirfields(data.airfields);
        }

        // Store metadata
        await offlineDB.setMetadata('referenceDataVersion', data.version);
        await offlineDB.setMetadata('referenceDataCached', new Date().toISOString());
        await offlineDB.setMetadata('flightTypes', JSON.stringify(data.flight_types || []));
        await offlineDB.setMetadata('releaseAltitudes', JSON.stringify(data.release_altitudes || []));
        await offlineDB.setMetadata('launchMethods', JSON.stringify(data.launch_methods || []));

        console.log('[ServiceWorker] Reference data cached');
    } catch (e) {
        console.error('[ServiceWorker] Failed to cache reference data:', e);
    }
}

// Serve reference data from IndexedDB cache
async function serveReferenceDataFromCache() {
    if (!offlineDB) {
        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'Offline database not available'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    try {
        const members = await offlineDB.getAllMembers();
        const gliders = await offlineDB.getAllGliders();
        const towplanes = await offlineDB.getAllTowplanes();
        const airfields = await offlineDB.getAllAirfields();
        const version = await offlineDB.getMetadata('referenceDataVersion');
        const cachedAt = await offlineDB.getMetadata('referenceDataCached');
        const flightTypes = JSON.parse(await offlineDB.getMetadata('flightTypes') || '[]');
        const releaseAltitudes = JSON.parse(await offlineDB.getMetadata('releaseAltitudes') || '[]');
        const launchMethods = JSON.parse(await offlineDB.getMetadata('launchMethods') || '[]');

        return new Response(JSON.stringify({
            success: true,
            offline: true,
            cached_at: cachedAt,
            version: version,
            members: members,
            gliders: gliders,
            towplanes: towplanes,
            airfields: airfields,
            flight_types: flightTypes,
            release_altitudes: releaseAltitudes,
            launch_methods: launchMethods
        }), {
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (e) {
        console.error('[ServiceWorker] Failed to serve reference data from cache:', e);
        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'Failed to read cached data'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Serve sync status from local state
async function serveSyncStatusFromCache() {
    if (!syncManager) {
        return new Response(JSON.stringify({
            success: true,
            online: false,
            pendingCount: 0,
            message: 'Sync manager not available'
        }), {
            headers: { 'Content-Type': 'application/json' }
        });
    }

    try {
        const status = await syncManager.getSyncStatus();
        return new Response(JSON.stringify({
            success: true,
            ...status
        }), {
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (e) {
        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'Failed to get sync status'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

// Background Sync event - sync pending flights when online
self.addEventListener('sync', (event) => {
    console.log('[ServiceWorker] Sync event:', event.tag);

    if (event.tag === 'sync-flights') {
        event.waitUntil(syncPendingFlights());
    }
});

// Sync pending flights to server
async function syncPendingFlights() {
    console.log('[ServiceWorker] Syncing pending flights...');

    try {
        await initOfflineModules();

        if (!syncManager) {
            console.warn('[ServiceWorker] Sync manager not available');
            return;
        }

        const result = await syncManager.syncNow();
        console.log('[ServiceWorker] Sync complete:', result);

        // Notify clients about sync completion
        const clients = await self.clients.matchAll();
        clients.forEach(client => {
            client.postMessage({
                type: 'sync-complete',
                result: result
            });
        });

        return result;
    } catch (e) {
        console.error('[ServiceWorker] Sync failed:', e);
        throw e; // Re-throw to trigger retry
    }
}

// Handle messages from the main thread
self.addEventListener('message', (event) => {
    if (event.data === 'skipWaiting') {
        self.skipWaiting();
    }

    if (event.data === 'sync-now') {
        // Manually trigger sync
        syncPendingFlights().then(result => {
            event.source.postMessage({
                type: 'sync-complete',
                result: result
            });
        });
    }

    if (event.data === 'get-sync-status') {
        // Return current sync status
        initOfflineModules().then(() => {
            if (syncManager) {
                syncManager.getSyncStatus().then(status => {
                    event.source.postMessage({
                        type: 'sync-status',
                        status: status
                    });
                });
            }
        });
    }

    if (event.data === 'refresh-reference-data') {
        // Trigger reference data refresh
        initOfflineModules().then(() => {
            if (syncManager) {
                syncManager.refreshReferenceData().then(result => {
                    event.source.postMessage({
                        type: 'reference-data-refreshed',
                        result: result
                    });
                });
            }
        });
    }
});
