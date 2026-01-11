# Kiosk Token Authentication (Issue #364)

This document describes the kiosk authentication system that enables passwordless login for dedicated club devices (e.g., the club laptop at the airfield).

## Problem Statement

The club laptop at the airfield needs to allow duty officers to enter flight data without:
- Requiring them to remember individual passwords
- Using a shared password on a "post-it note" that could be compromised
- Risking lockout if someone accidentally clicks logout

## Solution Overview

A **magic URL + device binding** system that:
1. Uses a cryptographically secure token in a bookmarked URL
2. Binds the token to a specific device via browser fingerprinting
3. Auto-reauthenticates if the session expires
4. Hides the logout button for kiosk users
5. Provides full audit logging and revocation capabilities

## Architecture

```mermaid
flowchart TD
    subgraph Setup ["Initial Setup (One-Time)"]
        A[Admin creates KioskToken] --> B[Generate Magic URL]
        B --> C[Visit URL on Laptop]
        C --> D[Collect Device Fingerprint]
        D --> E[Bind Fingerprint to Token]
        E --> F[Bookmark URL / Install PWA]
    end

    subgraph Daily ["Daily Use"]
        G[Open PWA/Bookmark] --> H{Session Valid?}
        H -->|Yes| I[✓ Access Granted]
        H -->|No| J{Kiosk Cookie?}
        J -->|Yes| K[Auto-Reauth Middleware]
        K --> L{Fingerprint Match?}
        L -->|Yes| I
        L -->|No| M[✗ Access Denied]
        J -->|No| N[Redirect to Login]
    end

    subgraph Security ["Security Controls"]
        O[Token Revocation] --> P[Immediate Access Denial]
        Q[Token Regeneration] --> R[Old URL Invalidated]
        S[Device Unbinding] --> T[Allows Re-binding]
    end
```

## Components

### 1. KioskToken Model

Located in `members/models.py`:

| Field | Type | Purpose |
|-------|------|---------|
| `user` | ForeignKey | Role account to authenticate as |
| `token` | CharField | Cryptographic token (auto-generated) |
| `name` | CharField | Human-readable identifier |
| `device_fingerprint` | CharField | SHA-256 hash of device characteristics |
| `is_active` | BooleanField | Can be revoked instantly |
| `landing_page` | CharField | Where to redirect after auth |
| `last_used_at` | DateTimeField | For auditing |
| `last_used_ip` | GenericIPAddressField | For auditing |

### 2. Device Fingerprinting

JavaScript in the binding/verification pages collects:
- User Agent
- Screen resolution and color depth
- Timezone
- Platform and language
- Hardware concurrency (CPU cores)
- Canvas fingerprint (GPU-specific)
- WebGL renderer info
- Audio context sample rate

These are combined and hashed to create a semi-unique device identifier.

### 3. Auto-Reauth Middleware

`utils.middleware.KioskAutoLoginMiddleware`:
- Runs on every request AFTER Django's AuthenticationMiddleware
- Checks for `kiosk_token` and `kiosk_fingerprint` cookies
- If present and valid, automatically logs in the user
- Prevents logout from locking out kiosk users

### 4. Template Tag

`{% is_kiosk_session as kiosk_mode %}`:
- Returns True if current session is a kiosk session
- Used to hide logout button for kiosk users
- Displays "(Kiosk)" indicator in navbar

## Workflow Diagrams

### Initial Device Binding

```mermaid
sequenceDiagram
    participant Admin
    participant Django Admin
    participant Laptop Browser
    participant Server

    Admin->>Django Admin: Create KioskToken
    Django Admin->>Admin: Display Magic URL
    Admin->>Laptop Browser: Enter Magic URL
    Laptop Browser->>Server: GET /kiosk/<token>/
    Server->>Laptop Browser: Binding Page
    Laptop Browser->>Laptop Browser: Collect Fingerprint (JS)
    Laptop Browser->>Server: POST /kiosk/<token>/bind/
    Server->>Server: Hash Fingerprint
    Server->>Server: Store in KioskToken
    Server->>Server: Log User In
    Server->>Laptop Browser: Set Cookies + Redirect
    Laptop Browser->>Laptop Browser: Install as PWA
```

### Daily Authentication

```mermaid
sequenceDiagram
    participant User
    participant PWA
    participant Middleware
    participant Django Auth
    participant KioskToken

    User->>PWA: Click app icon
    PWA->>Middleware: GET /logsheet/
    Middleware->>Middleware: Check session
    alt Session Valid
        Middleware->>PWA: ✓ Serve page
    else Session Expired
        Middleware->>Middleware: Check kiosk cookies
        alt Has Cookies
            Middleware->>KioskToken: Validate token + fingerprint
            alt Valid
                Middleware->>Django Auth: login(user)
                Middleware->>PWA: ✓ Serve page
            else Invalid
                Middleware->>PWA: Redirect to login
            end
        else No Cookies
            Middleware->>PWA: Redirect to login
        end
    end
```

### Security: Stolen URL Attack

```mermaid
sequenceDiagram
    participant Attacker
    participant Server
    participant KioskToken
    participant AccessLog

    Note over Attacker: Attacker obtains magic URL
    Attacker->>Server: GET /kiosk/<token>/
    Server->>Attacker: Verification Page
    Attacker->>Attacker: Collect fingerprint (different device)
    Attacker->>Server: POST /kiosk/<token>/verify/
    Server->>KioskToken: Validate fingerprint
    KioskToken-->>Server: ✗ Mismatch!
    Server->>AccessLog: Log failed attempt
    Server->>Attacker: 403 "Different device"
```

## Admin Interface

### Kiosk Tokens List

- View all tokens with status, binding state, last use
- Actions: Revoke, Regenerate, Unbind

### Token Detail

- Magic URL display (copy to clipboard)
- Device fingerprint (read-only)
- Usage statistics
- Notes field

### Access Logs

- Timestamp, token, status, IP, fingerprint
- Filter by status (success, fingerprint_mismatch, etc.)
- Date hierarchy for easy navigation

## Security Considerations

### What's Protected

| Attack | Protection |
|--------|------------|
| URL theft | Device fingerprint binding |
| Session hijacking | Fingerprint validation on reauth |
| Ex-member revenge | Token revocation |
| Brute force | Long cryptographic tokens |
| Accidental logout | Auto-reauth middleware |

### What's NOT Protected

| Risk | Mitigation |
|------|------------|
| Physical access to laptop | Physical security at airfield |
| Sophisticated fingerprint spoofing | Requires technical skill + original device access |
| Admin token leak | Limit admin access |

### Recommendations

1. **Rotate tokens periodically** (e.g., annually)
2. **Monitor access logs** for unusual patterns
3. **Use Role Account** membership type for kiosk users
4. **Train duty officers** not to share the magic URL

## Files Modified/Created

### New Files
- `members/views_kiosk.py` - Kiosk login/binding views
- `members/templates/members/kiosk/` - Templates
- `members/tests/test_kiosk_auth.py` - Tests
- `members/migrations/0017_kiosk_token.py` - Migration

### Modified Files
- `members/models.py` - KioskToken, KioskAccessLog models
- `members/admin.py` - Admin interfaces
- `members/urls.py` - URL routes
- `members/templatetags/member_extras.py` - `is_kiosk_session` tag
- `utils/middleware.py` - KioskAutoLoginMiddleware
- `manage2soar/settings.py` - Middleware registration
- `templates/base.html` - Hide logout for kiosk users

## Usage Instructions

### For Administrators

1. **Create Role Account:**
   - Go to Admin → Members → Add Member
   - Username: `kiosk-laptop` (or similar)
   - Membership Status: "Role Account"
   - No password needed

2. **Create Kiosk Token:**
   - Go to Admin → Kiosk Tokens → Add
   - Select the role account
   - Give it a name (e.g., "Club Laptop")
   - Choose landing page
   - Save

3. **Set Up Device:**
   - Copy the Magic URL from the token detail page
   - On the laptop, open the URL in Chrome/Edge
   - Wait for "Device Registered!" message
   - Install as PWA (optional but recommended)
   - Bookmark the landing page

4. **Revoke if Needed:**
   - Go to Admin → Kiosk Tokens
   - Uncheck "Active" on the token
   - Or use the "Revoke tokens" action

### For Duty Officers

1. Open the PWA or bookmarked page
2. You're automatically logged in
3. Enter flight data as normal
4. No logout needed (session handles itself)

## Troubleshooting

### "Device Mismatch" Error
- The laptop's browser was updated or fingerprint changed
- **Fix:** Admin unbinds device, then re-visit magic URL

### Kiosk Can't Access System
- Token may be revoked or regenerated
- **Fix:** Check token status in admin, re-bookmark if needed

### Logout Button Missing
- This is by design for kiosk users
- The "(Kiosk)" indicator confirms kiosk mode
