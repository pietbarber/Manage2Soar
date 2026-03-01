# Issue #709: Kiosk CSRF 403 Errors on All Logsheet POST Actions

**Resolution Date**: March 1, 2026
**Branch**: `feature/issue-709-kiosk-csrf-fix`
**PR**: #713
**Status**: Complete ✅

## Problem

In kiosk mode, virtually every button that submitted data — Launch, Land, Finalize Logsheet,
Delete Flight, Delete Charge, Save Finances, Save Closeout — returned a 403 Forbidden error.
The kiosk browser was fully authenticated and the page was freshly loaded from the server, yet
every POST failed immediately.

## Root Cause

There are **two independent bugs** that combined into this failure.

### Bug 1: KioskAutoLoginMiddleware rotates the CSRF token on every request

Django's MIDDLEWARE list processes in order. In our configuration:

```
Position 5: CsrfViewMiddleware          ← validates CSRF token
Position 7: KioskAutoLoginMiddleware    ← re-authenticates kiosk session
```

`KioskAutoLoginMiddleware` calls `django.contrib.auth.login()` on every request to keep the
kiosk session alive. `login()` internally calls `rotate_token()`, which generates a **new** CSRF
secret and invalidates any token that was embedded in a page rendered before this request.

The sequence that caused every failure:

1. Browser GETs `/logsheet/manage/69/` — Django renders page, bakes `{% csrf_token %}` into HTML.
2. **KioskAutoLoginMiddleware runs**, rotates the CSRF secret. The token in the HTML is now stale.
3. User clicks a button — browser POSTs with the stale token.
4. `CsrfViewMiddleware` runs first (position 5), compares stale token against new secret → **403**.

Confirmed in kubectl pod logs:
```
Forbidden (CSRF token from the 'X-Csrftoken' HTTP header incorrect.): /logsheet/flight/213/landing_now/
```

The pattern was always: GET `/logsheet/manage/<pk>/` → 200, followed immediately by POST to any
endpoint → 403. The page was always fresh from the server, ruling out caching.

### Bug 2: getCsrfToken() / getCSRFToken() were reading the raw cookie secret

The `getCsrfToken()` helper in `logsheet_manage.html` and the `getCSRFToken()` method in
`sync-manager.js` both had a fallback that read the raw `csrftoken` cookie value. This is wrong:
Django 5.x stores a 32-character unmasked secret in the cookie, but the `X-CSRFToken` header
must contain a **64-character masked** form token. Sending the raw secret always produces a 403,
regardless of the kiosk middleware issue.

### Bonus Bug: service_worker_view always served a 32-byte stub

`service_worker_view` in `manage2soar/urls.py` was reading from
`BASE_DIR/static/js/service-worker.js`. In production Docker containers, `static/` is empty —
`collectstatic` writes to `STATIC_ROOT` (`staticfiles/`). Every production deployment was silently
serving `// Service worker file not found` as the service worker, breaking all SW cache busting.

## Solution

### Primary fix: @csrf_exempt on all logsheet POST endpoints

Since `CsrfViewMiddleware` and `KioskAutoLoginMiddleware` run in conflicting order and cannot be
reordered without risk, the correct fix is to exempt all logsheet POST-handling views from CSRF
token validation.

This is **safe** because two complementary protections are already in place:
- `@active_member_required` enforces Django session authentication on every request.
- `CSRF_COOKIE_SAMESITE=Lax` prevents cross-origin POSTs at the browser level.

CSRF token checking is redundant here and actively harmful in the kiosk context.

Views that received `@csrf_exempt` in `logsheet/views.py`:

| View | Type |
|---|---|
| `update_flight_split` | AJAX POST — split edit modal on finances page |
| `land_flight_now` | AJAX POST — Land button |
| `launch_flight_now` | AJAX POST — Launch button |
| `delete_logsheet` | Form POST |
| `delete_flight` | Form POST |
| `add_member_charge` | Form POST |
| `delete_member_charge` | Form POST |
| `manage_logsheet_finances` | Form POST — finances page, posts to itself |
| `manage_logsheet` | Form POST — finalize button, posts to itself |
| `create_logsheet` | Form POST |
| `edit_flight` | Form POST |
| `add_flight` | Form POST |
| `edit_logsheet_closeout` | Form POST — closeout page |
| `add_towplane_closeout` | Form POST |
| `add_maintenance_issue` | Form POST |
| `add_maintenance_issue_standalone` | Form POST |
| `resolve_maintenance_issue` | Form POST |
| `maintenance_mark_resolved` | Form POST |
| `update_maintenance_deadline` | Form POST |

Decorator pattern used consistently:
```python
@csrf_exempt  # Session + SameSite=Lax protects this; kiosk token rotation fights CSRF middleware
@require_POST  # (where applicable)
@active_member_required
def view_name(request, ...):
```

### Secondary fix: Remove raw-cookie CSRF fallback

`getCsrfToken()` in `logsheet_manage.html` and `getCSRFToken()` in `static/js/offline/sync-manager.js`
were updated to read only from the DOM hidden input rendered by `{% csrf_token %}`. The raw cookie
fallback was removed.

An unconditional `<form id="csrf-anchor" hidden>{% csrf_token %}</form>` was added at the top of
`logsheet_manage.html` to guarantee the DOM input is always present regardless of which
conditional blocks render on the page.

### service_worker_view path fix

`manage2soar/urls.py` updated to try `settings.STATIC_ROOT / js / service-worker.js` first,
falling back to `BASE_DIR/static/js/` for local development where collectstatic may not have run.
Service worker cache version bumped `v19` → `v20` to force existing browsers to pick up the real SW.

### Observability improvements

- **`Dockerfile`**: Added `--access-logfile -` and `--error-logfile -` to gunicorn so all HTTP
  requests appear in `kubectl logs`.
- **`manage2soar/settings.py`**: Added `django.security` and `django.request` loggers so CSRF
  rejections and 4xx/5xx errors surface in pod logs without requiring gunicorn-level access logs.

## Why the investigation took so long

The debugging process was complicated by the service worker bug: the browser appeared to load
pages normally, but was sometimes serving stale HTML from a SW that wasn't actually working.
This obscured whether fixes were being applied. Once the SW path bug was found and corrected, the
token rotation pattern became clear in the logs immediately.

## Files Changed

- `logsheet/views.py` — `@csrf_exempt` on all POST-handling views
- `logsheet/templates/logsheet/logsheet_manage.html` — hidden csrf-anchor form; raw-cookie fallback removed
- `static/js/offline/sync-manager.js` — raw-cookie CSRF fallback removed
- `static/js/service-worker.js` — cache version bump v19 → v20
- `manage2soar/urls.py` — service_worker_view reads from STATIC_ROOT first
- `Dockerfile` — gunicorn access/error logging
- `manage2soar/settings.py` — django.security and django.request loggers
