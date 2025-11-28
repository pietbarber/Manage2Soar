/**
 * Manage2Soar Service Worker
 *
 * Level 1: App Shell Caching - Caches static assets for faster loads
 * Level 2: Offline fallback - Shows friendly offline page when network unavailable
 *
 * Future: Level 3 will add IndexedDB for offline logsheet data entry
 */

const CACHE_NAME = 'manage2soar-v1';
const OFFLINE_URL = '/offline/';

// Static assets to cache on install
// These form the "app shell" - the basic UI that loads instantly
const STATIC_ASSETS = [
  '/',
  '/offline/',
  '/static/css/baseline.css',
  '/static/css/bootstrap.min.css',
  '/static/css/calendar.css',
  '/static/css/cms.css',
  '/static/css/cms-responsive.css',
  '/static/css/logbook.css',
  '/static/css/members.css',
  '/static/css/mobile-fixes.css',
  '/static/css/progress.css',
  '/static/analytics/analytics.css',
  '/static/js/service-worker-register.js',
  '/static/manifest.json',
  '/static/images/pwa-icon-192.png',
  '/static/images/pwa-icon-512.png',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[ServiceWorker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[ServiceWorker] Caching app shell');
        // Use addAll for critical assets, but don't fail if some are missing
        return cache.addAll(STATIC_ASSETS).catch((error) => {
          console.warn('[ServiceWorker] Some assets failed to cache:', error);
          // Cache what we can individually
          return Promise.all(
            STATIC_ASSETS.map((url) =>
              cache.add(url).catch(() => console.warn(`Failed to cache: ${url}`))
            )
          );
        });
      })
      .then(() => {
        console.log('[ServiceWorker] Install complete');
        // Activate immediately without waiting for old service worker
        return self.skipWaiting();
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

  // Only handle GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip cross-origin requests (CDNs, etc.)
  if (url.origin !== location.origin) {
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

  // For static assets, use cache-first strategy
  event.respondWith(
    caches.match(request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          // Return cached version, but also update cache in background
          fetch(request).then((response) => {
            if (response.ok) {
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, response);
              });
            }
          }).catch(() => {});
          return cachedResponse;
        }

        // Not in cache - fetch from network
        return fetch(request)
          .then((response) => {
            // Cache successful responses
            if (response.ok) {
              const responseClone = response.clone();
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, responseClone);
              });
            }
            return response;
          });
      })
  );
});

// Handle messages from the main thread
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
