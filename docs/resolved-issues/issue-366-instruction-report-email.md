# Issue #366: Instruction Report Email Delivery

## Issue
**GitHub Issue**: #366  
**Problem**: After an instructor fills out an instruction report, the student did not receive an email copy of the report. Additionally, the instructor team had no way to stay informed of instruction activities across all students.

## Requirements
- After instruction report is written, send a copy to the student
- If there is an "instructors" mailing list (configured via MailingList model), CC instructors
- Include any new qualifications that were awarded during the session
- When the report is updated, clearly indicate it's an update to an existing report

## Solution Implemented

### 1. Email Sending Utility (`instructors/utils.py`)

Added `send_instruction_report_email()` function that:
- Sends HTML and plain text email to the student
- Optionally CCs the instructors mailing list if configured
- Includes new qualifications in the email
- Uses "Updated:" prefix for update emails
- Respects the project's EMAIL_DEV_MODE for safe testing

```python
def send_instruction_report_email(report, is_update=False, new_qualifications=None):
    """Send instruction report email to student and optionally CC instructors."""
```

### 2. Email Templates

**HTML Template** (`instructors/templates/instructors/emails/instruction_report.html`):
- Professional styled email matching other M2S HTML emails
- Update banner prominently displayed for updated reports
- New qualifications section with celebration styling
- Training items covered with color-coded scores
- Instructor notes section
- Score legend for reference
- Link to student's training logbook

**Plain Text Template** (`instructors/templates/instructors/emails/instruction_report.txt`):
- Clean formatting for email clients without HTML support
- Same information structure as HTML version

### 3. View Integration (`instructors/views.py`)

Modified `fill_instruction_report()` view to:
- Track whether the report is new or an update (`is_existing_report`)
- Capture newly awarded qualifications
- Call `send_instruction_report_email()` after successful save

```python
# Track if this is an update to an existing report
is_update = is_existing_report
new_qualification = None  # Track newly awarded qualification

# ... qualification processing ...
if is_qualified:
    new_qualification = mq

# Send instruction report email to student (and CC instructors if configured)
new_qualifications = [new_qualification] if new_qualification else None
send_instruction_report_email(
    report,
    is_update=is_update,
    new_qualifications=new_qualifications,
)
```

## Email Design

### Subject Line
- New report: `Instruction Report - {Student Name} - {Date}`
- Updated report: `Updated: Instruction Report - {Student Name} - {Date}`

### Recipients
- **TO**: Student's email address
- **CC**: All subscribers of the "instructors" MailingList (if configured)
  - Student is automatically removed from CC if they happen to be on the instructors list

### From Address
- Uses `noreply@{domain_name}` from SiteConfiguration

### Content Sections
1. Header with club logo and report date
2. Update banner (if applicable)
3. New qualifications (if any)
4. Training items with scores
5. Instructor notes
6. Score legend
7. Call to action (View Logbook button)
8. Footer with club info

## Files Modified/Created
- `instructors/utils.py` - Added `send_instruction_report_email()` function
- `instructors/views.py` - Integrated email sending into `fill_instruction_report()` view
- `instructors/templates/instructors/emails/instruction_report.html` (new)
- `instructors/templates/instructors/emails/instruction_report.txt` (new)
- `instructors/tests/test_instruction_report_email.py` (new) - 13 tests
- `instructors/docs/notifications.md` - Updated with email notification documentation

## Testing

13 tests covering:
- Email sent to student
- Email contains lesson scores and instructor notes
- Update subject prefix and banner
- New qualifications displayed
- No email for students without email address
- CC to instructors mailing list
- Student not duplicated in CC if on instructors list
- No CC when no instructors list exists
- Simulator session noted
- From email uses configured domain
- Logbook URL included

## Integration with MailingList (Issue #353)

This feature leverages the MailingList model from Issue #353:
- Queries for an "instructors" mailing list by name (case-insensitive)
- Uses `get_subscriber_emails()` to get all instructor email addresses
- Respects the `is_active` flag on the mailing list

## Related Documentation
- `instructors/docs/notifications.md` - Full notification documentation
- `siteconfig/docs/models.md` - MailingList model documentation

## Closed
December 2025
