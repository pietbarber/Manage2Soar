# Issue #360: Instructor Requests Navigation

## Issue
**GitHub Issue**: #360  
**Problem**: The `/duty-roster/instructor-requests/` page existed but had no visible navigation. Instructors receiving emails about student requests had no easy way to find the review page. Additionally, the club logo was getting stretched in email templates.

## Requirements
1. Add navigation link to Instructor Requests page
2. Add "Review Requests" link in duty calendar day popup for instructors
3. Add notification indicator in main nav when instructor has pending requests
4. Ensure notifications point to instructor-requests link
5. Fix stretched logo in instructor email templates

## Solution Implemented

### 1. Navbar Badge for Pending Requests

**Context Processor** (`duty_roster/context_processors.py`):
```python
def instructor_pending_requests(request):
    """Add pending instruction request count to template context."""
    # Returns {"instructor_pending_count": N} for instructors
    # Uses caching (5-minute TTL) to avoid DB queries on every page load
    # Cache invalidated via signals when InstructionSlot changes
```

**Added to Settings** (`manage2soar/settings.py`):
```python
TEMPLATES = [{
    "OPTIONS": {
        "context_processors": [
            ...
            "duty_roster.context_processors.instructor_pending_requests",
        ],
    },
}]
```

**Navbar Update** (`templates/base.html`):
- Added "Instructor Tools" dropdown with badge showing pending count
- "Student Requests" link with pending count badge
- Accessibility: `aria-label` for screen readers

### 2. Calendar Day Popup Button

**Template Update** (`duty_roster/templates/duty_roster/calendar_day_modal.html`):
```html
{% if user.is_authenticated and user.instructor %}
<a href="{% url 'duty_roster:instructor_requests' %}"
   class="btn btn-outline-primary">
    <i class="fas fa-clipboard-check me-1"></i>
    Review Student Requests
</a>
{% endif %}
```

### 3. Cache Invalidation

**Signal Handlers** (`duty_roster/signals.py`):
- `post_save` handler invalidates cache when InstructionSlot created/updated
- `post_delete` handler invalidates cache when InstructionSlot deleted
- Both primary and surge instructor caches are invalidated

```python
def _invalidate_instructor_cache_for_slot(instance):
    """Invalidate cache for a slot's instructors."""
    if instance.assignment.instructor:
        invalidate_instructor_pending_cache(instance.assignment.instructor.id)
    if instance.assignment.surge_instructor:
        invalidate_instructor_pending_cache(instance.assignment.surge_instructor.id)
```

### 4. Fixed Logo Stretching

**Email Templates Updated**:
- `instructors/templates/instructors/emails/student_signup_notification.html`
- `instructors/templates/instructors/emails/request_response.html`
- `instructors/templates/instructors/emails/instructor_summary.html`

**Fix**: Removed fixed `width="200" height="60"` attributes, replaced with:
```html
<img src="{{ club_logo_url }}" alt="{{ club_name }}"
     style="max-height: 60px; max-width: 200px; height: auto; width: auto;">
```

## Performance Optimizations

### Query Optimization
Changed from subquery to JOIN for better performance:
```python
# Before (subquery)
my_assignments = DutyAssignment.objects.filter(...)
pending_count = InstructionSlot.objects.filter(assignment__in=my_assignments, ...)

# After (JOIN)
pending_count = InstructionSlot.objects.filter(
    assignment__date__gte=today,
    instructor_response="pending",
).filter(
    Q(assignment__instructor=user) | Q(assignment__surge_instructor=user)
).exclude(status="cancelled").count()
```

### Caching
- 5-minute cache TTL for pending count
- Cache key: `instructor_pending_count_{user_id}`
- Automatic invalidation on InstructionSlot changes

## Files Created/Modified

### New Files
- `duty_roster/context_processors.py`
- `duty_roster/tests/test_context_processors.py` (12 tests)

### Modified Files
- `manage2soar/settings.py` - Added context processor
- `templates/base.html` - Added navbar badge and dropdown
- `duty_roster/templates/duty_roster/calendar_day_modal.html` - Added review button
- `duty_roster/signals.py` - Added cache invalidation handlers
- `instructors/templates/instructors/emails/*.html` - Fixed logo sizing

## Testing
- 12 tests for context processor covering:
  - Unauthenticated users return 0
  - Non-instructors return 0
  - Correct pending count for instructors
  - Future dates only
  - Excludes cancelled slots
  - Surge instructor visibility
  - Cache usage and invalidation
  - Delete signal cache invalidation

## Related Issues
- Issue #11: Instructor's summary of upcoming ops (prerequisite)

## Pull Request
PR #361: Add instructor requests navigation and fix logo stretching

## Closed
December 5, 2025
