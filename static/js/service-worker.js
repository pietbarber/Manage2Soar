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

const CACHE_NAME = 'manage2soar-v18';
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

// Note: Service workers cannot directly access IndexedDB modules loaded in the page.
// Instead, we use postMessage to communicate with the main page for sync operations.
// The main page has M2SIndexedDB and M2SOffline loaded and handles the actual data operations.

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

    // For logsheet AJAX requests (modals, partials), use network-first with cache fallback
    if (isLogsheetAjaxRequest(url.pathname)) {
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
                    // Network failed - try cache first
                    return caches.match(request)
                        .then((cachedResponse) => {
                            if (cachedResponse) {
                                return cachedResponse;
                            }
                            // Return offline-friendly HTML for modals with auto-retry
                            return new Response(`
                                <div class="alert alert-warning m-3" id="offline-modal-alert">
                                    <div class="d-flex align-items-center justify-content-between">
                                        <div>
                                            <i class="bi bi-wifi-off me-2"></i>
                                            <strong>You're offline.</strong>
                                            This action requires an internet connection.
                                        </div>
                                        <button type="button" class="btn btn-sm btn-outline-warning" onclick="location.reload()">
                                            <i class="bi bi-arrow-clockwise me-1"></i>Retry
                                        </button>
                                    </div>
                                    <div class="small mt-2 text-muted" id="offline-status-text">
                                        Waiting for connection...
                                    </div>
                                </div>
                                <script>
                                    // Auto-detect when back online
                                    function checkOnline() {
                                        if (navigator.onLine) {
                                            const statusText = document.getElementById('offline-status-text');
                                            const alert = document.getElementById('offline-modal-alert');
                                            if (statusText) {
                                                statusText.innerHTML = '<i class="bi bi-wifi text-success me-1"></i>Connection restored! <a href="#" onclick="location.reload(); return false;">Click to retry</a> or the page will reload automatically...';
                                            }
                                            if (alert) {
                                                alert.classList.remove('alert-warning');
                                                alert.classList.add('alert-success');
                                            }
                                            // Auto-reload after a brief delay
                                            setTimeout(() => location.reload(), 2000);
                                        }
                                    }
                                    window.addEventListener('online', checkOnline);
                                    // Also poll in case the event doesn't fire
                                    const pollInterval = setInterval(() => {
                                        if (navigator.onLine) {
                                            checkOnline();
                                            clearInterval(pollInterval);
                                        }
                                    }, 1000);
                                    // Initial check
                                    checkOnline();
                                </script>
                            `, {
                                status: 503,
                                statusText: 'Service Unavailable',
                                headers: { 'Content-Type': 'text/html' }
                            });
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

// Check if request is a logsheet AJAX request (modals, partials)
function isLogsheetAjaxRequest(pathname) {
    // Match logsheet modal/partial endpoints like:
    // /logsheet/manage/1234/edit-flight/5678/
    // /logsheet/manage/1234/add-flight/
    // /logsheet/manage/1234/delete-flight/5678/
    const logsheetPatterns = [
        /^\/logsheet\/manage\/\d+\/edit-flight\/\d+\/?$/,
        /^\/logsheet\/manage\/\d+\/add-flight\/?$/,
        /^\/logsheet\/manage\/\d+\/delete-flight\/\d+\/?$/,
        /^\/logsheet\/manage\/\d+\/flight-details\/\d+\/?$/,
        /^\/logsheet\/api\/(?!offline)/,  // Non-offline logsheet APIs
    ];
    return logsheetPatterns.some(pattern => pattern.test(pathname));
}

// Handle GET requests for offline API (reference data, sync status)
async function handleOfflineApiGet(request, url) {
    try {
        // Try network first
        const response = await fetch(request);
        if (response.ok) {
            return response;
        }
        throw new Error('Network response not ok');
    } catch (e) {
        // Network failed - return offline indicator
        // The page's JavaScript will handle serving from IndexedDB
        console.log('[ServiceWorker] Network failed for API:', url.pathname);

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
        // Network failed - return offline indicator
        // The page's JavaScript handles storing to IndexedDB
        console.log('[ServiceWorker] Network failed for POST, returning offline response');

        return new Response(JSON.stringify({
            success: false,
            offline: true,
            error: 'You are offline. Changes saved locally.'
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
// This notifies all clients to perform the sync using their loaded M2SIndexedDB
async function syncPendingFlights() {
    console.log('[ServiceWorker] Syncing pending flights - notifying clients...');

    try {
        // Notify all clients to perform sync
        const clients = await self.clients.matchAll({ type: 'window' });

        if (clients.length === 0) {
            console.log('[ServiceWorker] No clients available for sync');
            return { success: false, reason: 'no_clients' };
        }

        // Send sync message to all clients
        clients.forEach(client => {
            client.postMessage({
                type: 'perform-sync',
                timestamp: new Date().toISOString()
            });
        });

        console.log('[ServiceWorker] Sync message sent to', clients.length, 'client(s)');
        return { success: true, clientsNotified: clients.length };

    } catch (e) {
        console.error('[ServiceWorker] Sync notification failed:', e);
        throw e; // Re-throw to trigger retry
    }
}

// Handle messages from the main thread
self.addEventListener('message', (event) => {
    if (event.data === 'skipWaiting') {
        self.skipWaiting();
    }

    if (event.data === 'sync-now') {
        // Manually trigger sync - notify page to perform sync
        syncPendingFlights().then(result => {
            if (event.source) {
                event.source.postMessage({
                    type: 'sync-triggered',
                    result: result
                });
            }
        });
    }

    if (event.data === 'get-sync-status') {
        // Tell the page to report its own sync status
        // (The page has access to IndexedDB, not the service worker)
        if (event.source) {
            event.source.postMessage({
                type: 'request-sync-status'
            });
        }
    }
});
