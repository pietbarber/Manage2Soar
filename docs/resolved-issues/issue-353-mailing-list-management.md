# Issue #353: Configurable Mailing List Management

## Issue
**GitHub Issue**: #353  
**PR**: #365  
**Problem**: Mailing lists were hardcoded in `members/api.py`, making it difficult for clubs to customize their email distribution lists without modifying source code.

## Requirements
- Create a configurable mailing list system in Django admin
- Allow webmasters to define lists with flexible criteria
- Support multiple criteria per list using OR logic
- Integrate with the existing `email_lists` API endpoint
- Restrict management permissions to webmasters only

## Solution Implemented

### 1. New Models (`siteconfig/models.py`)

**MailingListCriterion (TextChoices Enum)**
Defines 12 available criteria for mailing list membership:
- `active_member` - Active club members with valid email
- `instructor`, `towpilot`, `duty_officer`, `assistant_duty_officer` - Operational roles
- `director`, `secretary`, `treasurer`, `webmaster`, `member_manager`, `rostermeister` - Board/management roles
- `private_glider_owner` - Owners of active private (non-club) gliders

**MailingList Model**
```python
class MailingList(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    criteria = models.JSONField(default=list)
    sort_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Key methods:
- `clean()`: Validates at least one criterion is selected
- `get_subscribers()`: Returns queryset of matching Members using OR logic
- `_criterion_to_query()`: Converts criterion code to Django Q object with base active filter
- `get_subscriber_emails()`: Returns list of email addresses
- `get_subscriber_count()`: Returns subscriber count

### 2. Admin Interface (`siteconfig/admin.py`)

**MailingListAdminForm**
- Uses `MultipleChoiceField` with `CheckboxSelectMultiple` widget for intuitive criteria selection
- Converts between JSONField storage and form checkboxes

**MailingListAdmin**
- Webmaster-only permissions via `_has_webmaster_permission()` helper
- Displays subscriber count in list view
- Collapsible Timestamps fieldset for metadata

### 3. API Integration (`members/api.py`)

The `email_lists` API endpoint was updated to dynamically generate lists from the database:

```python
# API response format
{
    "lists": {
        "instructors": {
            "description": "All active club instructors",
            "count": 12,
            "emails": ["instructor1@example.com", ...]
        },
        ...
    }
}
```

### 4. Database Migration

Migration `0018_mailinglist` creates the new table with all required fields.

## Design Decisions

### OR Logic for Criteria
When multiple criteria are selected, members matching ANY criterion are included. This allows flexible list definitions like "board" = directors OR secretary OR treasurer.

### Defensive Base Active Filter
The `_criterion_to_query()` method includes both `membership_status__in=active_statuses` and `is_active=True` checks. While `Member.save()` auto-syncs `is_active` with `membership_status`, the defensive filter handles edge cases (manual DB updates, signal failures).

### Email Validation
All criteria automatically filter out members with empty or null email addresses to prevent invalid entries in mailing lists.

### Webmaster Permissions
Only users with `Member.webmaster=True` can manage mailing lists, maintaining appropriate access control.

## Files Modified/Created
- `siteconfig/models.py` - Added `MailingList` and `MailingListCriterion`
- `siteconfig/admin.py` - Added `MailingListAdminForm` and `MailingListAdmin`
- `siteconfig/migrations/0018_mailinglist.py` - Database migration
- `members/api.py` - Updated to use dynamic mailing lists
- `siteconfig/tests/test_mailing_list.py` - Comprehensive test suite (31 tests)

## Testing
- 31 tests covering model validation, subscriber queries, admin form, and API integration
- Tests for all 12 criteria types
- Edge cases: empty criteria validation, invalid criteria codes, empty email filtering
- Admin permission tests for webmaster-only access

## Related Documentation
- `siteconfig/docs/models.md` - Model documentation with usage examples
- `siteconfig/docs/README.md` - App overview

## Closed
January 2025
