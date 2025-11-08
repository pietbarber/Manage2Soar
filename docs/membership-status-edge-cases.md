# Membership Status Edge Cases and Protections

## Overview
This document describes the edge case scenarios for membership status deletion and the protections implemented to prevent data integrity issues.

## Edge Case: Deleting In-Use Membership Statuses

### Problem
When a MembershipStatus is deleted while members still reference it:
- Members retain their `membership_status` string field
- However, `is_active_member()` returns `False` because the status no longer exists in the database
- This effectively "breaks" member access without warning

### Example Scenario
```python
# 1. Status exists and member is active
status = MembershipStatus.objects.get(name="Full Member")  
member.membership_status = "Full Member"
member.is_active_member()  # Returns True

# 2. Admin deletes status (without protection)
status.delete()

# 3. Member access is now broken
member.membership_status  # Still "Full Member" (string retained)
member.is_active_member()  # Returns False! (status doesn't exist)
```

## Protection Mechanisms

### 1. Model-Level Protection
**File:** `siteconfig/models.py` - `MembershipStatus.delete()` override

```python
def delete(self, *args, **kwargs):
    from members.models import Member
    member_count = Member.objects.filter(membership_status=self.name).count()
    if member_count > 0:
        raise ValidationError(
            f"Cannot delete membership status '{self.name}' because "
            f"{member_count} members currently have this status. "
            "Please change their status first or mark this status as inactive."
        )
    super().delete(*args, **kwargs)
```

**Protection Level:** Prevents deletion at the database/ORM level
**Scope:** All deletion attempts (admin, shell, programmatic)

### 2. Admin-Level Protection
**File:** `siteconfig/admin.py` - `MembershipStatusAdmin` overrides

```python
def delete_model(self, request, obj):
    try:
        super().delete_model(request, obj)
    except ValidationError as e:
        messages.error(request, str(e))

def delete_queryset(self, request, queryset):
    failed_deletions = []
    for obj in queryset:
        try:
            obj.delete()
        except ValidationError as e:
            failed_deletions.append(f"{obj.name}: {e}")

    if failed_deletions:
        messages.error(request, "Some items could not be deleted:\n" +
                      "\n".join(failed_deletions))
```

**Protection Level:** User-friendly error messages in Django admin
**Scope:** Admin interface bulk and individual deletions

## Testing Coverage

### Test Cases Implemented
1. **Deletion Protection Test:** Verifies ValidationError is raised when deleting in-use status
2. **Successful Deletion Test:** Confirms unused statuses can be deleted normally
3. **Integration Test:** Tests the complete workflow of protection and eventual deletion
4. **Edge Case Scenarios:** Tests behavior with deleted, null, and nonexistent statuses

### Test Files
- `siteconfig/tests/test_siteconfig.py` - Model-level protection tests
- `members/tests/test_utils.py` - Integration and utility function tests

## Safe Operations

### Adding New Statuses ✅
Always safe - no existing references to break.

### Modifying Existing Statuses ✅
- Changing `is_active`: Safe, affects access immediately
- Changing `description`: Safe, cosmetic only
- Changing `sort_order`: Safe, affects display order only
- **Changing `name`:** ⚠️ **DANGEROUS** - breaks existing member references

### Deleting Statuses
- **Unused statuses:** ✅ Safe with protections in place
- **In-use statuses:** 🛡️ **Protected** - deletion blocked with clear error message

## Best Practices for Administrators

### Safe Status Retirement Process
1. **Mark as Inactive First:** Set `is_active = False` to prevent new assignments
2. **Migrate Members:** Update all members to use different statuses
3. **Verify No Usage:** Check that no members reference the old status
4. **Delete Safely:** Now deletion will succeed without protection errors

### Recommended Admin Workflow
```python
# 1. Find members using the status
members_with_status = Member.objects.filter(membership_status="Old Status")
print(f"Found {members_with_status.count()} members to migrate")

# 2. Update them to new status
members_with_status.update(membership_status="New Status")

# 3. Now deletion will succeed
old_status = MembershipStatus.objects.get(name="Old Status")
old_status.delete()  # No error!
```

## Emergency Recovery

If a status was somehow deleted (e.g., database manipulation):

### Option 1: Recreate Status
```python
MembershipStatus.objects.create(
    name="Full Member",  # Exact same name as before
    is_active=True
)
# Members with this status string will be active again
```

### Option 2: Migrate Affected Members
```python
# Find members with orphaned status
affected_members = Member.objects.filter(membership_status="Deleted Status")
# Update them to valid status
affected_members.update(membership_status="Full Member")
```

## Technical Implementation Notes

### No Foreign Key Constraints
The system uses string-based references rather than foreign keys for flexibility. This means:
- ✅ **Benefit:** Easy to manage, no complex constraint handling
- ⚠️ **Risk:** No automatic database-level protection (hence our custom protections)
- 🛡️ **Mitigation:** Model-level validation provides the protection we need

### Performance Considerations
- Protection check runs a `count()` query on Member table
- Impact is minimal for deletion operations (rare)
- No performance impact on normal member operations

### Backwards Compatibility
- Existing members retain their status strings
- Migration populated database with all historical statuses
- No member access disrupted during implementation

## Related Documentation
- [Membership Statuses Configuration Guide](./membership-statuses.md)
- [Issue #169 Implementation](../README.md#issue-169)
- [Database Schema: Members App](../members/docs/models.md)
