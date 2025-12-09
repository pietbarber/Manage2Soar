# Email Template Style Guide

This document establishes the visual and technical standards for all automated email notifications sent by Manage2Soar.

## Quick Reference

**Logo Sizing:** `max-height: 60px; max-width: 200px; height: auto;`  
**Header Background:** `background-color: #667eea;` (solid purple) OR with gradient fallback  
**Text Color:** `#ffffff` (white) on colored backgrounds  
**Email Width:** `600px` max-width  
**Font Stack:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`

---

## Logo Standards

### Required Logo Styling
All email templates MUST use this exact logo styling:

```html
<img src="{{ club_logo_url }}" alt="{{ club_name }}"
     style="max-height: 60px; max-width: 200px; height: auto; margin-bottom: 15px;">
```

### ✅ Correct Logo Style
- **Rectangular** display (no circular cropping)
- **Maximum height:** 60px
- **Maximum width:** 200px
- **Aspect ratio:** Preserved with `height: auto`
- **No background:** No white background or padding around logo
- **No border-radius:** Logo displays in its original rectangular format

### ❌ Incorrect Logo Styles (Do Not Use)
- ~~`border-radius: 50%`~~ - Creates circular "porthole" effect
- ~~`width: 80px; height: 80px`~~ - Fixed dimensions distort logo
- ~~`max-width: 200px` only~~ - Without max-height constraint, logos become too large
- ~~`background-color: white; padding: 10px;`~~ - Adds unwanted white circle behind logo

---

## Header Background Colors

### Email Client Compatibility
Different email clients have varying support for CSS features:

| Email Client | Gradient Support | Fallback Required |
|--------------|------------------|-------------------|
| Gmail        | ✅ Full support  | No                |
| Apple Mail/iCloud | ✅ Full support | No           |
| Outlook (all versions) | ❌ No support | **Yes**     |
| Yahoo Mail   | ❌ No support    | **Yes**           |

### Background Color Standards

#### Option 1: Solid Background (Recommended for Maximum Compatibility)
Use for templates where consistent rendering across all email clients is critical:

```html
<td style="background-color: #667eea; padding: 30px 40px; text-align: center;">
```

**Used in:**
- Duty Delinquency Report
- Maintenance Digest
- Late SPRs Notification

**Advantages:**
- ✅ 100% reliable across all email clients
- ✅ No hidden text issues
- ✅ Simpler CSS

#### Option 2: Gradient with Fallback (Visual Enhancement)
Use for templates where gradient aesthetics are desired:

```html
<td style="background-color: #667eea; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 20px;">
```

**Used in:**
- Surge Instructor Alert
- Surge Towpilot Alert
- Ad-hoc Proposed/Confirmed/Expiration
- Ops Intent Notification
- Operations Cancelled
- Instruction Cancellation

**How it works:**
1. `background-color: #667eea;` - Fallback for Outlook/Yahoo
2. `background: linear-gradient(...)` - Enhanced gradient for modern clients
3. CSS cascade ensures modern clients use gradient, older clients use solid color

**Result:**
- Modern clients (Gmail, iCloud): Beautiful purple-to-violet gradient
- Older clients (Outlook, Yahoo): Solid purple background
- All clients: White text remains visible

### Color Palette

| Color | Hex Code | Usage |
|-------|----------|-------|
| Primary Purple | `#667eea` | Main header background |
| Secondary Purple | `#764ba2` | Gradient end color |
| Success Green | `#276749` | Accepted/confirmed states |
| Error Red | `#c53030` | Rejected/cancelled states |
| Warning Orange | `#ed8936` | Alerts and warnings |
| Warning Yellow | `#ffc107` | Caution banners |
| White | `#ffffff` | Header text color |
| Light Gray | `#e0e0e0` | Secondary header text |

---

## Email Structure

### Standard Email Template Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!--[if mso]>
    <style type="text/css">
        table { border-collapse: collapse; }
        td { padding: 0; }
    </style>
    <![endif]-->
    <title>Email Subject</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f4f4;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td align="center" style="padding: 20px 0;">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0"
                       style="max-width: 600px; background-color: #ffffff; border-radius: 8px;">

                    <!-- Header with Logo -->
                    <tr>
                        <td style="background-color: #667eea; padding: 30px 40px; text-align: center;">
                            {% if club_logo_url %}
                            <img src="{{ club_logo_url }}" alt="{{ club_name }}"
                                 style="max-height: 60px; max-width: 200px; height: auto; margin-bottom: 15px;">
                            {% endif %}
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">
                                Email Title
                            </h1>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <!-- Email content here -->
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f4f4f4; padding: 20px; text-align: center;">
                            <p style="margin: 0; color: #666666; font-size: 12px;">
                                This is an automated message from {{ club_name }}.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

---

## Typography

### Font Stack
Always use the system font stack for maximum compatibility:

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
```

### Text Sizing

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| H1 (Email Title) | 24px | bold | #ffffff (on colored bg) |
| H2 (Section Headers) | 18-20px | 600 | #2d3748 |
| Body Text | 15-16px | normal | #4a5568 |
| Subtitle/Meta | 14-16px | normal | #718096 or #e0e0e0 |
| Footer Text | 12px | normal | #666666 |

---

## Buttons and Links

### Primary Action Button
```html
<a href="{{ url }}" style="display: inline-block;
   background-color: #667eea; color: #ffffff;
   text-decoration: none; padding: 12px 30px;
   border-radius: 4px; font-weight: bold; font-size: 16px;">
    Button Text
</a>
```

### With Gradient (Optional)
```html
<a href="{{ url }}" style="display: inline-block;
   background-color: #667eea;
   background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
   color: #ffffff; text-decoration: none;
   padding: 12px 30px; border-radius: 4px;
   font-weight: bold; font-size: 16px;">
    Button Text
</a>
```

---

## Emoji Usage

### Approved Emojis for Email Headers

| Emoji | Usage | Example Template |
|-------|-------|------------------|
| 🚨 | Urgent alerts, surge notifications | Surge Instructor/Towpilot Alert |
| 📊 | Reports and analytics | Duty Delinquency Report |
| 🔧 | Maintenance issues | Maintenance Digest |
| ✅ | Confirmations, success | Ad-hoc Confirmed |
| ⚠️ | Warnings, expiration | Ad-hoc Expiration |
| 📅 | Calendar/scheduling | Ops Intent, Pre-op Duty |
| 👋 | Greetings, contact | Visitor Contact |
| 📝 | Forms, applications | Application Submitted |

### Emoji Guidelines
- ✅ Use sparingly (one emoji per email header maximum)
- ✅ Place emoji at the beginning of titles
- ✅ Ensure emoji meaning is clear and reinforces the message
- ❌ Don't use multiple emojis in one title
- ❌ Don't rely solely on emoji to convey critical information

---

## Banner and Alert Styling

### Warning/Caution Banner
```html
<tr>
    <td style="padding: 20px 40px; background-color: #fff3cd; border-left: 5px solid #ffc107;">
        <p style="margin: 0; color: #856404; font-size: 18px; font-weight: bold;">
            ⚠️ Important Notice
        </p>
    </td>
</tr>
```

### Error/Critical Banner
```html
<tr>
    <td style="padding: 20px 40px; background-color: #dc3545; text-align: center;">
        <p style="margin: 0; color: #ffffff; font-size: 18px; font-weight: bold;">
            🚨 FINAL NOTICE
        </p>
    </td>
</tr>
```

### Success/Confirmation Banner
```html
<tr>
    <td style="padding: 20px 40px; background-color: #f0fff4; border-left: 4px solid #38a169;">
        <p style="margin: 0; color: #276749; font-size: 18px; font-weight: bold;">
            ✅ Confirmed
        </p>
    </td>
</tr>
```

---

## Template Checklist

When creating a new email template, verify:

- [ ] Logo uses `max-height: 60px; max-width: 200px; height: auto;`
- [ ] Logo has NO `border-radius` or circular styling
- [ ] Header background uses solid color OR gradient with fallback
- [ ] White text (`#ffffff`) on all colored backgrounds
- [ ] Email width constrained to `600px` max-width
- [ ] System font stack used throughout
- [ ] Mobile-friendly with `viewport` meta tag
- [ ] Outlook compatibility tags included `<!--[if mso]>`
- [ ] Footer includes club name and automated message notice
- [ ] Tested in Gmail, Outlook, Yahoo, and Apple Mail
- [ ] All URLs use absolute paths (with domain)
- [ ] Logo URL uses `get_absolute_club_logo_url()` helper

---

## Testing Requirements

### Manual Testing
All email templates MUST be tested in these environments:

1. **Gmail** (web and mobile app)
2. **Outlook** (web and desktop client)
3. **Yahoo Mail** (web)
4. **Apple Mail / iCloud** (web and iOS app)

### Test Scripts
Use the test scripts in `email-tests/` directory:

```bash
# Test a specific email notification
./email-tests/test-[number].sh

# Test all affected emails after style changes
for script in 8 10 12 13 14 15 16 17 18 19 20 21; do
    ./email-tests/test-${script}.sh
    sleep 2
done
```

### What to Verify
- ✅ Logo displays at correct size (not too large, not too small)
- ✅ Logo is rectangular (not circular)
- ✅ Background colors display correctly (no white backgrounds)
- ✅ All text is visible (no white-on-white text)
- ✅ Emojis render correctly
- ✅ Buttons are clickable
- ✅ Mobile responsive layout works

---

## Common Issues and Solutions

### Issue: White text invisible on white background (Outlook/Yahoo)
**Cause:** CSS gradient not supported, no fallback background-color  
**Solution:** Add `background-color: #667eea;` BEFORE the gradient:
```html
style="background-color: #667eea; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"
```

### Issue: Logo appears as small circle
**Cause:** Using `border-radius: 50%` with fixed width/height  
**Solution:** Remove border-radius, use `max-height: 60px; max-width: 200px; height: auto;`

### Issue: Logo too large
**Cause:** Missing `max-height` constraint  
**Solution:** Always include both `max-height: 60px` AND `max-width: 200px`

### Issue: Email title confusing (e.g., "Accepted" with rejection text)
**Cause:** Template context missing `is_accepted` boolean  
**Solution:** Ensure all context variables are properly set in view/signal that sends email

---

## Related Documentation

- **Email Notifications Overview:** `docs/notifications.md`
- **CronJob Email System:** `docs/cronjob-architecture.md`
- **Test Email Scripts:** `email-tests/README.md`
- **Email Dev Mode:** `utils/email.py` - EMAIL_DEV_MODE settings

---

## History

**Created:** December 8, 2025  
**Last Updated:** December 8, 2025  
**Related Issues:** #383 - Email style consistency fixes

**Major Revisions:**
- Initial style guide based on 21+ email templates in production
- Standardized logo sizing and removed circular "porthole" styling
- Established gradient fallback pattern for Outlook/Yahoo compatibility
- Documented emoji usage and color palette standards
