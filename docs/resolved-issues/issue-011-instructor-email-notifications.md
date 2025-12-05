# Issue #11: Instructor's Summary of Upcoming Ops (Email Notifications)

## Issue
**GitHub Issue**: #11  
**Problem**: Instructors needed email notifications when students sign up for instruction, with the ability to accept/reject requests and receive summary emails before instruction sessions.

## Requirements
1. Email notification to instructor when student signs up for instruction
2. Instructor ability to accept/reject instruction requests
3. Student notification when request is accepted/rejected
4. Summary email to instructors 48+ hours before instruction with student progress
5. Rich HTML emails (not plain text with emojis)
6. Follow style of pre-op summary emails
7. Use `noreply@{domain}` as from address

## Solution Implemented

### 1. Student Signup Notification

**Signal Handler** (`duty_roster/signals.py`):
- `send_student_signup_notification()` - Triggered on InstructionSlot creation
- Notifies both primary instructor and surge instructor (if assigned)
- Includes student progress snapshot (solo/checkride progress, session count)
- Creates in-system notification with link to review requests

**Email Template** (`instructors/templates/instructors/emails/student_signup_notification.html`):
- Professional HTML layout with club logo
- Student name and instruction date
- Progress bars showing solo and checkride progress
- Session count
- "Review Request" CTA button

### 2. Request Accept/Reject Response

**Signal Handler** (`duty_roster/signals.py`):
- `send_request_response_email()` - Triggered when `instructor_response` changes
- Pre-save signal stores original response to detect changes
- Sends appropriate email based on accept/reject status

**Email Template** (`instructors/templates/instructors/emails/request_response.html`):
- Clear accept/reject status indicator
- Instructor's note if provided
- Links to view requests and calendar

### 3. Instructor Summary Email (48-hour reminder)

**Management Command** (`instructors/management/commands/send_instructor_summary_emails.py`):
- Runs via CronJob 48 hours before instruction dates
- Aggregates all pending students for each instructor
- Uses `BaseCronJobCommand` for distributed locking

**Email Template** (`instructors/templates/instructors/emails/instructor_summary.html`):
- Summary of all students signed up
- Individual student cards with:
  - Photo (if available)
  - Progress bars
  - Session count
  - Request status (pending/accepted)
- Link to review all requests

### 4. From Email Address

```python
def _get_from_email(config):
    """Get the noreply@ from email address."""
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if "@" in default_from:
        domain = default_from.split("@")[-1]
        return f"noreply@{domain}"
    elif config and config.domain_name:
        return f"noreply@{config.domain_name}"
    else:
        return "noreply@manage2soar.com"
```

### 5. In-System Notifications

Both signup and response events create in-system `Notification` objects:
- Duplicate detection prevents spam
- Links directly to relevant pages
- Dismissible by user

## Files Created/Modified

### New Files
- `instructors/templates/instructors/emails/student_signup_notification.html`
- `instructors/templates/instructors/emails/student_signup_notification.txt`
- `instructors/templates/instructors/emails/request_response.html`
- `instructors/templates/instructors/emails/request_response.txt`
- `instructors/templates/instructors/emails/instructor_summary.html`
- `instructors/templates/instructors/emails/instructor_summary.txt`
- `instructors/management/commands/send_instructor_summary_emails.py`

### Modified Files
- `duty_roster/signals.py` - Added notification signal handlers
- `duty_roster/models.py` - Added `instructor_response` field to InstructionSlot
- `instructors/models.py` - StudentProgressSnapshot for progress tracking

## Email Flow

```
Student requests instruction
    ↓
Signal: send_student_signup_notification()
    ↓
Email to instructor(s) + in-system notification
    ↓
Instructor reviews at /duty-roster/instructor-requests/
    ↓
Instructor accepts/rejects
    ↓
Signal: send_request_response_email()
    ↓
Email to student + in-system notification
```

## Testing
- `instructors/tests/test_instructor_notifications.py` - Comprehensive test coverage
- Tests for duplicate notification prevention
- Tests for both instructor and surge instructor notification
- Tests for email content and template rendering

## Related Issues
- Issue #352: HTMLify Duty Notification Email (similar email enhancement)
- Issue #360: Instructor Requests Navigation

## Closed
December 5, 2025
