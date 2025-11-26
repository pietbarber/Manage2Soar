# Issue #275: Role Accounts and Active Member Status

**Status:** Resolved  
**PR:** #293  
**Date:** November 2025

## Problem Statement

The codebase had inconsistent handling of active membership statuses:

1. **Duplicated Fallback Logic**: Multiple files contained identical try/except blocks that fell back to legacy constants when the `siteconfig.MembershipStatus` model wasn't available
2. **Direct Constant Usage**: Code was importing `DEFAULT_ACTIVE_STATUSES` and `ALLOWED_MEMBERSHIP_STATUSES` directly from `members/constants/membership.py` instead of using the configurable `siteconfig.MembershipStatus` model
3. **No Role Account Support**: There was no way to distinguish system/robot accounts (superuser, import bots, field laptops) from human members

## Solution Overview

### 1. Centralized Membership Status Helpers

Enhanced `members/utils/membership.py` to be the **single source of truth** for membership status queries:

```python
from members.utils.membership import (
    get_active_membership_statuses,   # Replaces DEFAULT_ACTIVE_STATUSES
    get_all_membership_statuses,      # Replaces ALLOWED_MEMBERSHIP_STATUSES
)
```

**New Features:**
- Proper docstrings and type hints
- Logging when fallback to legacy constants occurs
- `DeprecationWarning` emitted when legacy constants are accessed
- New `get_all_membership_statuses()` function for complete status list

### 2. Removed Inline Fallback Blocks

Refactored the following files to use the centralized helpers:

| File | Location | Change |
|------|----------|--------|
| `members/models.py` | `is_active_member()` method | Uses `get_active_membership_statuses()` |
| `duty_roster/management/commands/report_duty_delinquents.py` | 3 locations | Uses centralized helper |
| `logsheet/views.py` | `manage_logsheet_finances()` | Uses centralized helper |

**Before (duplicated in multiple files):**
```python
try:
    from siteconfig.models import MembershipStatus
    active_status_names = list(MembershipStatus.get_active_statuses())
except ImportError:
    from members.constants.membership import DEFAULT_ACTIVE_STATUSES
    active_status_names = DEFAULT_ACTIVE_STATUSES
```

**After (centralized):**
```python
from members.utils.membership import get_active_membership_statuses
active_status_names = get_active_membership_statuses()
```

### 3. Deprecated Legacy Constants

Updated `members/constants/membership.py` with:
- Detailed deprecation notice at top of file
- Comments above each deprecated constant
- Added "Role Account" to `MEMBERSHIP_STATUS_CHOICES`

```python
"""
DEPRECATION NOTICE:
===================
These constants are DEPRECATED and will be removed in a future version.

Instead of using these constants directly, use the centralized helpers:

    from members.utils.membership import (
        get_active_membership_statuses,   # Replaces DEFAULT_ACTIVE_STATUSES
        get_all_membership_statuses,      # Replaces ALLOWED_MEMBERSHIP_STATUSES
    )
"""
```

### 4. Added "Role Account" Membership Status

Created migration `siteconfig/migrations/0016_add_role_account_status.py`:

| Property | Value |
|----------|-------|
| **Name** | Role Account |
| **is_active** | False |
| **sort_order** | 250 |
| **Description** | System or robot account used for automated processes |

**Use Cases:**
- Superuser accounts
- Import bots
- Field laptop accounts  
- Other automated/service accounts

Role accounts are intentionally marked as **not active**, meaning they:
- Don't appear in member lists
- Can't be assigned duties
- Don't receive member-only notifications
- Can still authenticate and perform system functions

## Files Changed

### Core Implementation
- `members/utils/membership.py` - Enhanced centralized helpers
- `members/models.py` - Uses centralized helper in `is_active_member()`
- `members/constants/membership.py` - Added deprecation notices

### Refactored to Use Helpers
- `duty_roster/management/commands/report_duty_delinquents.py`
- `logsheet/views.py`

### New Migration
- `siteconfig/migrations/0016_add_role_account_status.py`

### Documentation Updates
- `instructors/docs/management.md` - Updated reference
- `instructors/management/commands/backfill_student_progress_snapshot.py` - Updated docstring
- `members/tests/test_forms.py` - Updated comments
- `members/tests/test_views.py` - Updated comments

## Testing

All tests pass:
- 96 tests in `members/` and `siteconfig/` apps
- 157 tests in `duty_roster/`, `logsheet/`, and notification commands
- Migration applies cleanly

## Migration Notes

The migration adds a new row to `siteconfig_membershipstatus`:

```sql
INSERT INTO siteconfig_membershipstatus (name, is_active, sort_order, description)
VALUES ('Role Account', FALSE, 250, 'System or robot account...');
```

This is additive and requires no data migration of existing members.

## Future Work

Issue #275 also mentions:
- **Token-based login for field laptop accounts** - Certificate-based authentication
- **Token renewal workflow** - Time-limited access tokens

These are significant features that should be tracked as separate issues.

## Related Issues

- Issue #169: MembershipStatus Configuration (original siteconfig work)
- Issue #288: Duty Delinquents Notification Fix (similar active status fixes)
- Issue #290: Notification Cleanup System (also used active status helpers)

## Usage Guide

### Checking if a Member is Active

```python
# In model method (preferred)
member.is_active_member()

# In view or utility code
from members.utils.membership import get_active_membership_statuses
if member.membership_status in get_active_membership_statuses():
    # Member is active
```

### Getting All Membership Statuses

```python
from members.utils.membership import get_all_membership_statuses
all_statuses = get_all_membership_statuses()
```

### Creating a Role Account

```python
from members.models import Member

bot_account = Member.objects.create(
    username="import_bot",
    email="bot@example.com",
    first_name="Import",
    last_name="Bot",
    membership_status="Role Account",
    is_superuser=False,
)
```
