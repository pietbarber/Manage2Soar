/**
 * Manage2Soar Service Worker
 *
 * Level 1: App Shell Caching - Caches navigation pages for faster loads
 * Level 2: Offline fallback - Shows friendly offline page when network unavailable
 *
 * Future: Level 3 will add IndexedDB for offline logsheet data entry
 *
 * Note: Static assets (CSS, JS, images) are served from GCS with proper caching
 * headers, so we don't cache them here. We focus on HTML pages and the offline
 * fallback experience.
 */

const CACHE_NAME = 'manage2soar-v2';
const OFFLINE_URL = '/offline/';

// Pages to cache on install - these are served by Django, not GCS
const CORE_PAGES = [
  '/',
  '/offline/',
  '/manifest.json',
];

// Install event - cache core pages
self.addEventListener('install', (event) => {
  console.log('[ServiceWorker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[ServiceWorker] Caching core pages');
        return cache.addAll(CORE_PAGES);
      })
      .then(() => {
        console.log('[ServiceWorker] Install complete');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.warn('[ServiceWorker] Install failed:', error);
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

  // For non-navigation requests (API calls, etc.), pass through to network
  // Static assets are served from GCS with proper caching headers
  event.respondWith(fetch(request));
});

// Handle messages from the main thread
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
