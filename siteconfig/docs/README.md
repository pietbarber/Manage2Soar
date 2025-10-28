# SiteConfiguration fields

This document lists the important `SiteConfiguration` fields used by the application 

## Overview

The `SiteConfiguration` model stores site-wide settings and customizable role titles. There should only be one instance of this model. The admin UI provides an editor for the single SiteConfiguration object.

This app configures site-wide variables including:
- Whether the club uses a duty roster to assign instructors or duties
- Site-wide configuration like club name, URL, and logo
- **Configurable membership statuses** (new feature) - allows clubs to customize their membership status types

The app also includes the `MembershipStatus` model which allows clubs to define their own membership statuses instead of using hardcoded values. 

## Notable fields

- `club_name` (CharField)
  - Human-friendly club name used in the navbar and title.
  - Example default: `"Manage2Soar"` (the template will fall back to this if empty).

- `domain_name` (CharField)
  - Primary domain name for the site (e.g. `example.org`).

- `club_logo` (ImageField)
  - Optional logo image used in the navbar and for generating a favicon.

- `club_abbreviation` (CharField)
  - Short abbreviation used in small UIs.

- `membership_manager_title` (CharField)
  - New: customizable label for the person who manages membership (e.g. "Membership Manager", "Member Meister").
  - Default: `"Membership Manager"`
  - Used in templates (for example, the members detail page) so UI text can refer to the club's preferred job title.

- `equipment_manager_title` (CharField)
  - Customizable label for equipment manager.

- `duty_officer_title`, `assistant_duty_officer_title`, `instructor_title`, etc.
  - Existing terminology fields for various roles; used by the roster and scheduling UIs.

## Redaction notification dedupe

- `redaction_notification_dedupe_minutes` (PositiveIntegerField)
  - Number of minutes to suppress duplicate redaction notifications for the same member URL.
  - Default: `60` (minutes).
  - Behavior: when a member toggles redaction on/off, the system notifies roster managers; this field controls a time-window to avoid spamming the same recipient with repeated notifications for the same member URL.

## Scheduling toggles

- `schedule_instructors`, `schedule_tow_pilots`, `schedule_duty_officers`, `schedule_assistant_duty_officers`
  - Boolean toggles to enable/disable scheduling UI elements for specific roles.

## Notes

- Only one `SiteConfiguration` instance should exist. The model enforces this in its `clean()` method.
- The admin UI exposes these fields; to change behavior or defaults, edit this model and run any required migrations.

## Using `SiteConfiguration` from `manage.py shell`

Here are common examples you may find useful when working from a Django shell (`python manage.py shell`):

1. Read the current configuration

```python
from siteconfig.models import SiteConfiguration
sc = SiteConfiguration.objects.first()
print(sc.club_name)
print(sc.membership_manager_title)

# Access the dedupe window
print(sc.redaction_notification_dedupe_minutes)
```

2. Update a field (safe for one-off/admin fixes)

```python
from siteconfig.models import SiteConfiguration
sc = SiteConfiguration.objects.first()
sc.membership_manager_title = 'Membership Meister'
sc.redaction_notification_dedupe_minutes = 120
sc.save()
```

3. Create a SiteConfiguration (only do this if none exists)

```python
from siteconfig.models import SiteConfiguration
if not SiteConfiguration.objects.exists():
  SiteConfiguration.objects.create(
    club_name='My Club',
    domain_name='example.org',
    club_abbreviation='MC',
  )

# Always prefer editing via the Django admin for safety
```

4. Use from templates

In templates you can load the siteconfig with the provided template tag:

```django
{% load siteconfig_tags %}
{% get_siteconfig as siteconfig %}
{{ siteconfig.membership_manager_title }}
```

If you want more examples (for scripts or tests), tell me which patterns you need and I will add them.

---

# MembershipStatus Model

## Overview

The `MembershipStatus` model allows clubs to configure their own custom membership statuses instead of using hardcoded values. This addresses Issue #169 and makes the system flexible for different club structures.

## Key Features

- **Configurable statuses**: Clubs can add, edit, or remove membership statuses as needed
- **Active/Inactive control**: Each status can be marked as active (grants member access) or inactive
- **Sort ordering**: Control the display order in dropdowns and lists
- **Backward compatibility**: Existing members are unaffected during the transition

## Fields

- `name` (CharField, unique)
  - The display name for the membership status (e.g., "Full Member", "Student Member")
  - Must be unique across all statuses

- `is_active` (BooleanField, default=True)
  - Whether members with this status are considered "active" and can access member features
  - Active members can log in and use member-only functionality

- `sort_order` (PositiveIntegerField, default=100)
  - Controls display order in dropdowns and lists (lower numbers appear first)
  - Useful for organizing statuses logically (e.g., Full Members before Student Members)

- `description` (TextField, optional)
  - Optional description explaining what this membership status means
  - Helpful for administrators managing multiple status types

## Admin Interface

The admin interface at `/admin/siteconfig/membershipstatus/` allows authorized users to:

- Add new membership statuses
- Edit existing statuses (name, active status, sort order, description)
- Delete unused statuses (⚠️ be careful - existing members may reference them)

**Permissions**: Only Webmasters and Member Managers can manage membership statuses.

## Usage Examples

### From Django shell

1. **View all membership statuses**:
```python
from siteconfig.models import MembershipStatus
for status in MembershipStatus.objects.all():
    print(f"{status.name} - Active: {status.is_active} - Order: {status.sort_order}")
```

2. **Get active statuses only**:
```python
active_statuses = list(MembershipStatus.get_active_statuses())
print("Active statuses:", active_statuses)
```

3. **Create a new membership status**:
```python
MembershipStatus.objects.create(
    name="Trial Member",
    is_active=True,
    sort_order=15,
    description="New members on trial period"
)
```

4. **Update a status**:
```python
status = MembershipStatus.objects.get(name="Student Member")
status.sort_order = 5  # Move to top of list
status.save()
```

### From code

The system automatically uses dynamic membership statuses throughout the application:

```python
from members.utils.membership import get_active_membership_statuses
from members.models import Member

# Get current active statuses
active_statuses = get_active_membership_statuses()

# Filter members by active status
active_members = Member.objects.filter(membership_status__in=active_statuses)

# Check if a member is active (uses dynamic statuses)
member = Member.objects.get(username="john_doe")
if member.is_active_member():
    print("Member has access to member features")
```

## Migration and Backward Compatibility

The system includes migrations that:
1. Create the `MembershipStatus` table
2. Populate it with all previously hardcoded membership statuses
3. Update the `Member` model to use dynamic choices

**No existing data is lost** - all current member statuses are preserved and continue to work.

## Default Initial Statuses

The migration creates these initial membership statuses:

**Active Statuses** (is_active=True):
- Charter Member, Full Member, Probationary Member
- FAST Member, Introductory Member, Affiliate Member
- Family Member, Service Member, Student Member
- Transient Member, Emeritus Member, Honorary Member
- Founding Member, SSEF Member, Temporary Member

**Inactive Statuses** (is_active=False):
- Inactive, Non-Member, Pending, Deceased

Clubs can modify, add to, or remove from this list as needed.

## Troubleshooting

### Q: I changed a status from active to inactive, but members still have access
A: The change takes effect immediately. If members still have access, check:
1. The member's actual `membership_status` field value
2. Whether they have superuser privileges (superusers bypass membership checks)
3. Any cached authentication that may need to be cleared

### Q: Can I safely delete a membership status?
A: **Be very careful**. Check if any existing members have that status first:
```python
status_name = "Old Status"
members_with_status = Member.objects.filter(membership_status=status_name)
if members_with_status.exists():
    print(f"Warning: {members_with_status.count()} members still have this status")
```

### Q: How do I add a new membership status?
A: Use the admin interface at `/admin/siteconfig/membershipstatus/` or create via Django shell as shown above.

## Related Documentation

- See `members/docs/models.md` for Member model documentation
- See `members/utils/membership.py` for membership utility functions
- Issue #169: Original feature request for configurable membership statuses
