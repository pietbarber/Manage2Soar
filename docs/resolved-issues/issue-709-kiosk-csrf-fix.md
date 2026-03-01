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

`KioskAutoLoginMiddleware` calls `django.contrib.auth.login()` **only when the kiosk session has
expired** (`not request.user.is_authenticated`). `login()` internally calls `rotate_token()`,
which overwrites `request.META["CSRF_COOKIE"]` with a new secret mid-request.

The sequence that caused every failure:

1. Browser GETs `/logsheet/manage/69/` — user is **already authenticated**; KioskAutoLoginMiddleware
   **skips** `login()`. Django renders the page, baking `{% csrf_token %}` (derived from secret S1) into HTML.
2. The kiosk session expires server-side (short `SESSION_COOKIE_AGE`).
3. User clicks a button — browser POSTs with the CSRF token from step 1.
4. `CsrfViewMiddleware.process_request` runs (position 5) — reads the stable cookie, sets `META["CSRF_COOKIE"] = S1`.
5. `KioskAutoLoginMiddleware` runs (position 7) — user is no longer authenticated → calls `login()` → `rotate_token()` **overwrites** `META["CSRF_COOKIE"]` with a new secret S2.
6. `CsrfViewMiddleware.process_view` compares the submitted token (masked S1) against `META["CSRF_COOKIE"]` (now S2) → **403**.

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

### Primary fix: Reorder MIDDLEWARE so KioskAutoLoginMiddleware runs before CsrfViewMiddleware

The root cause is a middleware ordering problem. The fix moves `AuthenticationMiddleware` and
`KioskAutoLoginMiddleware` above `CsrfViewMiddleware` in `MIDDLEWARE`:

```python
# Before fix (broken):
"django.middleware.csrf.CsrfViewMiddleware",    # position 5 — stores old secret in META
"django.contrib.auth.middleware.AuthenticationMiddleware",
"utils.middleware.KioskAutoLoginMiddleware",    # position 7 — rotate_token() overwrites META

# After fix (correct):
"django.contrib.auth.middleware.AuthenticationMiddleware",
"utils.middleware.KioskAutoLoginMiddleware",    # rotate_token() sets META = new_secret
"django.middleware.csrf.CsrfViewMiddleware",    # process_request OVERWRITES META with cookie value -> validates OK
```

**Why this works:** `CsrfViewMiddleware.process_request` reads the CSRF secret from
`request.COOKIES` and stores it in `request.META["CSRF_COOKIE"]`. If KioskAutoLoginMiddleware
has already run `rotate_token()` (writing a new random string to META), `process_request`
overwrites it with the stable cookie value — exactly what `process_view` needs to validate
the POST token against.

No `@csrf_exempt` on any view. Full CSRF protection is preserved.

Regression tests in `logsheet/tests/test_kiosk_csrf.py` verify:
1. The middleware ordering is structurally correct.
2. Kiosk POSTs succeed with CSRF enforcement active in both active-session and
   post-session-expiry scenarios.

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

- `manage2soar/settings.py` — MIDDLEWARE reordered: `AuthenticationMiddleware` + `KioskAutoLoginMiddleware` moved before `CsrfViewMiddleware`; `django.security` and `django.request` loggers added
- `utils/middleware.py` — docstring updated to document required ordering constraint
- `logsheet/views.py` — `@ensure_csrf_cookie` on `manage_logsheet` only (all `@csrf_exempt` decorators removed — full CSRF protection restored)
- `logsheet/tests/test_kiosk_csrf.py` — regression tests: middleware order assertions + functional kiosk POST tests with `enforce_csrf_checks=True`
- `logsheet/templates/logsheet/logsheet_manage.html` — hidden csrf-anchor form; raw-cookie fallback removed from `getCsrfToken()`
- `static/js/offline/sync-manager.js` — raw-cookie CSRF fallback removed
- `static/js/service-worker.js` — cache version bump v19 → v20
- `manage2soar/urls.py` — service_worker_view reads from STATIC_ROOT first
- `Dockerfile` — gunicorn access/error logging
