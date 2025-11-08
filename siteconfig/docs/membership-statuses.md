# Configurable Membership Statuses

## Overview

As of Issue #169, Manage2Soar supports configurable membership statuses instead of hardcoded values. This allows clubs to customize their membership types according to their specific needs.

## Why This Change Was Made

Previously, membership statuses were hardcoded in `members/constants/membership.py`. This caused problems because:

1. **Different clubs have different needs**: Some clubs have 3 membership types, others have 20+
2. **Status names vary**: What one club calls "Full Member", another might call "Regular Member"  
3. **Flexibility required**: Clubs need to be able to add new statuses or retire old ones
4. **Administrative burden**: Code changes were required to modify membership statuses

## How It Works

### Database-Driven Configuration

The new system uses the `MembershipStatus` model in the `siteconfig` app to store:
- **Status name**: The display name (e.g., "Full Member")
- **Active flag**: Whether this status grants member access
- **Sort order**: Display order in lists and dropdowns
- **Description**: Optional explanation of the status

### Dynamic Integration

The system dynamically loads membership statuses throughout the application:

- **Member.is_active_member()**: Queries database for active statuses
- **Form dropdowns**: Populate from database instead of hardcoded lists
- **Admin interfaces**: Use current status list for filtering and editing
- **Analytics and reports**: Filter by currently active statuses

### Backward Compatibility

All existing member records continue to work. The migration:
1. Creates the new `MembershipStatus` table
2. Populates it with all previously hardcoded statuses
3. Preserves all existing member data

## Administrator Guide

### Managing Membership Statuses

1. **Access the admin**: Go to `/admin/siteconfig/membershipstatus/`
2. **Required permissions**: Must be a Webmaster or Member Manager
3. **Add new status**: Click "Add Membership Status"
4. **Edit existing**: Click on any status name to modify
5. **Delete unused**: Only delete statuses not used by any members

### Best Practices

1. **Plan your statuses**: Decide on naming convention before adding many statuses
2. **Use sort order**: Organize statuses logically (active types first, then inactive)
3. **Be descriptive**: Add descriptions for complex or unusual status types
4. **Check before deleting**: Ensure no members have a status before removing it

### Common Status Configurations

**Small Club (3-5 statuses)**:
- Full Member (active, sort_order=10)
- Student Member (active, sort_order=20)
- Inactive (inactive, sort_order=100)
- Non-Member (inactive, sort_order=110)

**Large Club (15+ statuses)**:
- Charter Member (active, sort_order=5)
- Full Member (active, sort_order=10)
- Family Member (active, sort_order=15)
- Student Member (active, sort_order=20)
- Introductory Member (active, sort_order=25)
- Service Member (active, sort_order=30)
- Honorary Member (active, sort_order=35)
- Emeritus Member (active, sort_order=40)
- Probationary Member (active, sort_order=45)
- Pending (inactive, sort_order=100)
- Inactive (inactive, sort_order=110)
- Non-Member (inactive, sort_order=120)
- Deceased (inactive, sort_order=200)

## Developer Guide

### Using Dynamic Statuses in Code

```python
# Get active membership statuses
from members.utils.membership import get_active_membership_statuses
active_statuses = get_active_membership_statuses()

# Filter members by active status
from members.models import Member
active_members = Member.objects.filter(membership_status__in=active_statuses)

# Check if member is active (uses dynamic lookup)
member = Member.objects.get(pk=123)
if member.is_active_member():
    # Grant access to member features
    pass

# Get all status choices for forms
choices = Member.get_membership_status_choices()
```

### Adding New Features

When adding features that need to distinguish between member types:

1. **Use `get_active_membership_statuses()`** instead of importing constants
2. **Always check `member.is_active_member()`** for access control
3. **Consider specific status filtering** if you need more granular control
4. **Test with different status configurations** to ensure flexibility

### Migration Patterns

If you need to modify the membership status system:

```python
# In a data migration
def update_membership_statuses(apps, schema_editor):
    MembershipStatus = apps.get_model('siteconfig', 'MembershipStatus')

    # Add a new status
    MembershipStatus.objects.get_or_create(
        name="Trial Member",
        defaults={
            'is_active': True,
            'sort_order': 12,
            'description': 'Members in trial period'
        }
    )

    # Update existing status
    status = MembershipStatus.objects.get(name='Student Member')
    status.sort_order = 5
    status.save()
```

## Testing

The system includes comprehensive tests:

- **Model tests**: `siteconfig/tests/test_siteconfig.py`
- **Integration tests**: `members/tests/test_models.py`
- **Utility tests**: `members/tests/test_utils.py`

When adding features, ensure tests cover:
1. Database queries for active statuses
2. Form choice generation
3. Member access control with various statuses
4. Edge cases (empty status list, nonexistent statuses)

## Troubleshooting

### Member Can't Access Site After Status Change

1. **Check status is active**: Verify `is_active=True` in admin
2. **Verify member's status**: Check the member's `membership_status` field matches exactly
3. **Clear cache**: Restart application if using cached authentication
4. **Check superuser**: Superusers bypass membership checks

### Status Not Appearing in Dropdowns  

1. **Check sort order**: Very high sort orders may appear at bottom
2. **Verify creation**: Ensure status was saved successfully
3. **Check permissions**: Some forms may filter by user permissions

### Performance Concerns

The dynamic system queries the database for active statuses. This is cached at the application level, but for high-traffic sites:

1. **Consider caching**: Add Redis/Memcached for status lists
2. **Monitor queries**: Use Django Debug Toolbar to check query patterns
3. **Optimize ordering**: Database indexes on `sort_order` and `is_active` fields

## Migration Details

The migration process involved:

1. **New model creation**: `siteconfig.MembershipStatus`
2. **Data population**: All hardcoded statuses copied to database
3. **Field updates**: Member.membership_status field extended to 50 characters
4. **Code updates**: 15+ files updated to use dynamic lookups
5. **Test updates**: All tests modified to work with database-driven statuses

Files modified:
- `members/models.py` - Dynamic choice methods
- `members/utils/membership.py` - Dynamic utility functions  
- `members/views.py` - Dynamic status filtering
- `logsheet/forms.py` - Dynamic dropdown population
- `instructors/views.py` - Dynamic member filtering
- `analytics/views.py` - Dynamic access control
- Multiple test files for compatibility

## Future Enhancements

Potential improvements to consider:

1. **Status permissions**: Fine-grained permissions per status type
2. **Status transitions**: Workflow for changing member statuses
3. **Status history**: Track when members change status
4. **Bulk operations**: Tools for bulk status changes
5. **Import/export**: CSV import/export of status configurations
6. **Status templates**: Pre-configured status sets for different club types

## Related Issues

- **Issue #169**: Original request for configurable membership statuses
- **Issue #181**: Crispy forms removal (exposed some hardcoded status dependencies)

## Conclusion

The configurable membership status system provides the flexibility clubs need while maintaining backward compatibility and system integrity. The dynamic approach ensures that membership status changes take effect immediately across the entire application.
