# Billing App - Decorator Documentation

## Overview

The billing app uses two decorators to gate access to financial operations. These decorators enforce both **application-level gating** (is billing enabled?) and **role-based authorization** (is the user a treasurer?).

---

## Application-Level Gating

### `billing_app_required`

**Location**: `billing/decorators.py`

**Purpose**: Ensures the billing application is enabled site-wide before allowing access to any billing view. When billing is disabled, users are silently redirected home with an informational message.

```python
from billing.decorators import billing_app_required

@billing_app_required
def some_billing_view(request):
    # Only reached if SiteConfiguration.billing_app_enabled=True
    ...
```

**Behavior**:

| Condition | Result |
|-----------|--------|
| `billing_app_enabled=True` | View executes normally |
| `billing_app_enabled=False` | Redirects to "/" with info message "Billing is disabled for this site." |

**Implementation**:

```python
from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from siteconfig.models import SiteConfiguration

def billing_app_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not SiteConfiguration.objects.filter(
            billing_app_enabled=True
        ).exists():
            messages.info(request, "Billing is disabled for this site.")
            return redirect("/")
        return view_func(request, *args, **kwargs)
    return wrapper
```

**Usage Notes**:

- Applied first (outermost) in decorator stacks — checked before role checks
- Uses `SiteConfiguration.objects.filter(...).exists()` which hits the database on every request
- No caching layer currently; consider adding per-request memoization if performance becomes an issue
- Does not check user authentication — that is the responsibility of downstream decorators

---

## Role-Based Authorization

### `treasurer_required`

**Location**: `billing/views.py`

**Purpose**: Restricts access to treasurer-only billing views. Users must be either a superuser or have the `treasurer` flag set on their Member profile.

```python
from billing.views import treasurer_required

@treasurer_required
def ledger_list(request):
    # Only accessible to superusers or treasurers
    ...
```

**Behavior**:

| Condition | Result |
|-----------|--------|
| User is authenticated + superuser | View executes normally |
| User is authenticated + treasurer flag=True | View executes normally |
| User is authenticated + not treasurer/not superuser | Returns 403 HttpResponseForbidden |
| User is not authenticated | Redirects to login page with return URL |

**Implementation**:

```python
from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden

def treasurer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_superuser or request.user.treasurer):
            return HttpResponseForbidden("Treasurer access is required.")
        return view_func(request, *args, **kwargs)
    return wrapper
```

**Member Profile Integration**:

This project uses `members.Member` as `AUTH_USER_MODEL` (subclassing `AbstractUser`).
The `treasurer` flag is defined directly on that user model and accessed as `request.user.treasurer`.

---

## Decorator Stacking Order

When multiple decorators apply, order matters. Billing views stack them as follows:

```python
@billing_app_required     # 1st: Is billing enabled? (checked first)
@treasurer_required       # 2nd: Is user treasurer? (checked second)
def ledger_list(request):
    ...
```

**Execution flow**:

```
Request arrives
    ↓
billing_app_enabled check (SiteConfiguration)
    ↓
If disabled → redirect to "/" with info message
    ↓
If enabled → continue
    ↓
Authentication check (is_authenticated?)
    ↓
If not authenticated → redirect to login
    ↓
If authenticated → role check (superuser or treasurer?)
    ↓
If not authorized → 403 Forbidden
    ↓
If authorized → view executes
```

**Why this order matters**:

1. **Application gate first** — If billing is disabled, there is no reason to check user permissions; skip early
2. **Authentication before authorization** — Verify identity before checking role (standard Django pattern)
3. **`@wraps` preservation** — All decorators use `functools.wraps` so `__name__`, `__doc__`, and `__module__` are preserved for admin integration

---

## Comparison with Other Apps

| App | Decorator | Purpose | Location |
|-----|-----------|---------|----------|
| **billing** | `billing_app_required` | App-level gate | `billing/decorators.py` |
| **billing** | `treasurer_required` | Role-based gate | `billing/views.py` |
| **members** | `active_member_required` | Membership status gate | `members/decorators.py` |
| **members** | `safety_officer_required` | Safety role gate | `members/decorators.py` |
| **instructors** | `instructor_required` | Instructor role gate | `instructors/decorators.py` |
| **instructors** | `member_or_instructor_required` | Member or instructor gate | `instructors/decorators.py` |
| **members/api** | `api_key_required` | API key validation | `members/api.py` |

---

## Testing

```bash
# Test billing decorators via integration tests
pytest billing/tests/test_billing_disabled.py billing/tests/test_views.py -v
```

### Example Test Patterns

```python
from django.test import TestCase, override_settings
from siteconfig.models import SiteConfiguration

class BillingAppRequiredTest(TestCase):
    def test_disabled_billing_redirects(self):
        """When billing is disabled, view returns redirect."""
        SiteConfiguration.objects.update(billing_app_enabled=False)
        response = self.client.get("/billing/ledgers/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    @override_settings(BILLING_ENABLED=True)
    def test_enabled_billing_proceeds(self):
        """When billing is enabled, view executes."""
        SiteConfiguration.objects.update(billing_app_enabled=True)
        response = self.client.get("/billing/ledgers/")
        self.assertEqual(response.status_code, 200)
```

---

## Related Documentation

- [Architecture Overview](architecture.md) - System design and flow
- [Data Models](models.md) - Detailed field specifications
- [API Reference](api.md) - Service layer API
- [Development Guide](development.md) - Contributing to billing app
- [Testing Guide](testing.md) - Billing test suite organization
