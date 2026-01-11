# Kiosk Authentication

This module provides passwordless authentication for dedicated kiosk devices.

## Overview

The kiosk authentication system allows club devices (like the airfield laptop) to access Manage2Soar without requiring users to enter passwords. It uses:

1. **Magic URLs** with cryptographic tokens
2. **Device fingerprinting** to bind tokens to specific hardware
3. **Auto-reauth middleware** to prevent lockouts

## Models

### KioskToken

Represents a kiosk authentication token.

```python
class KioskToken(models.Model):
    user = models.ForeignKey(Member)  # Role account
    token = models.CharField()         # Crypto token (auto-generated)
    name = models.CharField()          # Human-readable name
    device_fingerprint = models.CharField()  # SHA-256 hash
    is_active = models.BooleanField()  # Revocation flag
    landing_page = models.CharField()  # Redirect destination
    last_used_at = models.DateTimeField()
    last_used_ip = models.GenericIPAddressField()
```

### KioskAccessLog

Audit log for all kiosk access attempts.

```python
class KioskAccessLog(models.Model):
    kiosk_token = models.ForeignKey(KioskToken)
    token_value = models.CharField()
    timestamp = models.DateTimeField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_fingerprint = models.CharField()
    status = models.CharField()  # success, invalid_token, fingerprint_mismatch, etc.
```

## Views

Located in `members/views_kiosk.py`:

| View | URL | Purpose |
|------|-----|---------|
| `kiosk_login` | `/members/kiosk/<token>/` | Magic URL entry point |
| `kiosk_bind_device` | `/members/kiosk/<token>/bind/` | Bind device fingerprint |
| `kiosk_verify_device` | `/members/kiosk/<token>/verify/` | Verify bound device |

## Middleware

`utils.middleware.KioskAutoLoginMiddleware`:

- Placed after `AuthenticationMiddleware` in the middleware stack
- Checks for `kiosk_token` and `kiosk_fingerprint` cookies
- Auto-authenticates valid kiosk sessions

## Template Tags

`{% is_kiosk_session as kiosk_mode %}`:

- Returns True if current session is a kiosk session
- Used to conditionally hide logout button

## Security

### Device Fingerprinting

JavaScript collects:
- User Agent, screen resolution, timezone
- Canvas fingerprint (GPU-specific)
- WebGL renderer information
- Audio context properties

Combined and SHA-256 hashed for storage.

### Attack Prevention

| Attack | Protection |
|--------|------------|
| URL theft | Device binding - URL useless on other devices |
| Session hijacking | Fingerprint validated on every auto-reauth |
| Token compromise | Instant revocation via admin |

## Admin Interface

### KioskTokenAdmin

- List view with status, binding state, last use
- Actions: Revoke, Regenerate, Unbind
- Magic URL display on detail page

### KioskAccessLogAdmin

- Read-only audit trail
- Filterable by status and date
- Shows IP addresses and fingerprint previews

## Files

- `members/models.py` - KioskToken, KioskAccessLog
- `members/views_kiosk.py` - Views
- `members/templates/members/kiosk/` - Templates
- `members/admin.py` - Admin interfaces
- `members/tests/test_kiosk_auth.py` - Tests
- `utils/middleware.py` - KioskAutoLoginMiddleware

## See Also

- [Issue #364 Resolution](../../docs/resolved-issues/issue-364-kiosk-authentication.md)
