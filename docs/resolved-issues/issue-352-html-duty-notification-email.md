# Issue #352: HTMLify Duty Notification Email

## Issue
**GitHub Issue**: #352  
**Problem**: Pre-operations duty notification emails were plain text with emojis, looking unprofessional and lacking important information about signed-up students and members planning to fly.

## Requirements
- Change from address to `noreply@` instead of `members@`
- Include site logo from SiteConfiguration (fallback to M2S logo)
- List students signed up for instruction
- List private owners and members indicating they want to fly
- Remove emojis from email content
- Minimize external image dependencies
- Include URL to check the duty roster
- Start with a gentle reminder of upcoming duty

## Solution Implemented

### 1. Rich HTML Email Template (`duty_roster/templates/duty_roster/emails/preop_notification.html`)

Created a professional HTML email template with:
- **Header**: Club logo (from SiteConfiguration) with fallback styling
- **Greeting**: Personalized "Hello {first_name}," format
- **Assignment Summary**: Table showing date, role, and field name
- **Students Section**: List of students signed up for instruction with count
- **Flying Members Section**: Private owners and members planning to fly
- **Call to Action**: Button linking to duty calendar
- **Footer**: Club name and calendar link

### 2. Plain Text Fallback (`duty_roster/templates/duty_roster/emails/preop_notification.txt`)

Maintained plain text version for email clients that don't support HTML:
- Clean formatting without emojis
- Same information structure as HTML version
- Clear section headers

### 3. Updated Email Sending Logic (`duty_roster/management/commands/send_preop_emails.py`)

- Changed from address to `noreply@{domain}` using `_get_from_email()` helper
- Added context variables for students and flying members
- Included site URL and calendar links
- Properly pulls club logo from SiteConfiguration

### 4. Email Helper Function (`duty_roster/signals.py`)

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

## Email Design
- Consistent with other M2S HTML emails
- Mobile-responsive layout
- Minimal external dependencies (only club logo if configured)
- Professional color scheme matching site branding

## Files Modified
- `duty_roster/management/commands/send_preop_emails.py`
- `duty_roster/templates/duty_roster/emails/preop_notification.html` (new)
- `duty_roster/templates/duty_roster/emails/preop_notification.txt` (updated)

## Testing
- Verified HTML rendering in multiple email clients
- Confirmed plain text fallback works correctly
- Tested with and without SiteConfiguration logo
- Verified student and flying member lists populate correctly

## Related Issues
- Issue #11: Instructor's summary of upcoming ops (similar email enhancement)

## Closed
December 5, 2025
