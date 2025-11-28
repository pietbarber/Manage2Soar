# Issue #291: PWA App Trigger

## Problem
Users wanted the ability to "install" Manage2Soar as a native-like app on their mobile devices and desktops. Without PWA (Progressive Web App) support, users had to always open a browser and navigate to the site, with no offline fallback when network connectivity was lost.

## Solution
Implemented Level 1 + Level 2 PWA support:

1. **Web App Manifest** - Enables "Add to Home Screen" functionality
2. **Service Worker** - Caches static assets for faster loads and provides offline fallback
3. **Offline Page** - Friendly UI when network is unavailable instead of browser error
4. **Offline Indicator** - Banner at bottom of page when user loses connectivity

## Implementation Details

### Files Created

| File | Purpose |
|------|---------|
| `static/manifest.json` | PWA manifest defining app name, icons, colors, display mode |
| `static/js/service-worker.js` | Caches static assets, serves offline page when network fails |
| `static/js/service-worker-register.js` | Registers service worker, handles online/offline status events |
| `templates/offline.html` | Friendly offline page with retry button and cached page links |
| `static/images/pwa-icon-192.png` | App icon for home screen (192x192) |
| `static/images/pwa-icon-512.png` | App icon for splash screen (512x512) |

### Files Modified

| File | Changes |
|------|---------|
| `manage2soar/urls.py` | Added `/offline/` route and `/service-worker.js` endpoint |
| `templates/base.html` | Added manifest link, Apple meta tags, offline indicator, SW registration |

### Service Worker Strategies

The service worker uses different caching strategies depending on request type:

- **Navigation requests (HTML pages)**: Network-first with cache fallback
  - Try network first to get fresh content
  - If network fails, serve from cache
  - If nothing cached, show offline page

- **Static assets (CSS, JS, images)**: Cache-first with background update
  - Serve cached version immediately for speed
  - Update cache in background for next visit

### Manifest Configuration

```json
{
  "name": "Manage2Soar",
  "short_name": "M2S",
  "start_url": "/",
  "display": "standalone",
  "theme_color": "#212529",
  "icons": [...]
}
```

### URL Routes Added

```python
path("offline/", TemplateView.as_view(template_name="offline.html"), name="offline"),
path("service-worker.js", service_worker_view, name="service-worker"),
```

The service worker is served from the root URL (`/service-worker.js`) rather than `/static/js/` because service workers can only control pages within their scope. A service worker at `/static/js/service-worker.js` could only control URLs under `/static/js/`.

## PWA Capability Levels

This implementation covers Levels 1-2 of a 4-level PWA maturity model:

| Level | Feature | Status |
|-------|---------|--------|
| 1 | App Shell Caching | ✅ Implemented |
| 2 | Offline UI / Indicator | ✅ Implemented |
| 3 | Offline Data Entry (IndexedDB + Background Sync) | 🔮 Future (Issue #62) |
| 4 | Full Offline App | 🔮 Future |

## Testing

### Manual Testing
1. Visit site in Chrome/Edge
2. Look for install icon in address bar (or menu → "Install Manage2Soar")
3. Install the app
4. Test offline mode:
   - Open DevTools → Network → Toggle "Offline"
   - Reload page → Should see offline page
   - Toggle back online → Auto-refresh

### Verifying Service Worker
- DevTools → Application → Service Workers
- Should show `service-worker.js` as "activated and running"
- Cache Storage should show `manage2soar-{hash}` with cached assets

### Cache Versioning
The service worker cache is automatically versioned using a build hash:
1. **BUILD_HASH env var** - Set during Docker build (preferred)
2. **File mtime** - Falls back to service-worker.js modification time
3. **Date hash** - Ultimate fallback, changes daily

To pass a build hash during Docker build:
```bash
docker build --build-arg BUILD_HASH=$(git rev-parse --short HEAD) -t manage2soar .
```

## Future Enhancements (Issue #62)

The service worker foundation enables future offline logsheet capability:

1. **IndexedDB storage** for flight entries when offline
2. **Background Sync API** to POST queued data when back online
3. **Pre-cached member/glider lists** for offline form dropdowns
4. **Sync status indicator** showing pending uploads

## Related Issues
- **Issue #62**: Off-line Logsheet Data Entry (future enhancement using this foundation)
