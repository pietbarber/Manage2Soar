# Redaction of Personal Contact Information

This document describes the "redact contact" feature: members can choose to suppress their personal contact information from the public member directory. The implementation is intentionally template/JS-driven and avoids adding persistent audit models unless explicitly requested.

## What is redacted
- Email address
- Phone and mobile numbers
- Postal address
- vCard / contact QR image

## How it's stored
- `Member.redact_contact` is a Boolean on the `Member` model. When true, templates should avoid rendering personal contact values directly to non-privileged viewers.

## Who can still view redacted info
- Members themselves (profile owner) always see their own contact info.
- Staff (users with `is_staff` or superusers) can see contact info in the UI.
- Rostermeisters can view redacted information only on the member detail page. The list view intentionally displays the word "Redacted" for suppressed members to respect membership privacy at-a-glance.

## UX details
- Member list (`members:member_list`): any member with `redact_contact` displays the muted text "Redacted" in the Phone and Email columns for all viewers. This prevents accidental exposure on lists.
- Member detail (`members:member_view`): rostermeisters who need to lookup a redacted member should open the member detail page and use the admin tools or view the member record. Per-field inline reveals have been removed from the UI; an informational modal notifies rostermeisters that the member has redacted their contact information.

## JavaScript behavior
- The per-field inline reveal script was removed in favor of a simpler policy: redacted members show "Redacted" in list contexts and rostermeisters must open the member record to view details. The member view still contains an informational modal for rostermeisters; the page uses the site's standard `{% block extra_scripts %}` to ensure any page scripts run after Bootstrap is loaded.

## Notifications
- Toggling `Member.redact_contact` triggers a notification to rostermeisters. The view that toggles this setting includes dedupe logic in notifications to avoid spam; see tests in `members/tests/` for details.

## Audit logging
- There is no audit log for reveals in this design. If you require auditing of who viewed redacted data, we can add a `RedactionRevealLog` model and a protected reveal endpoint (this would require a migration and explicit approval).

## Testing guidance
- Unit tests should cover:
  - Members toggling `redact_contact` (permission checks and notification creation).
  - Template rendering for list and detail views based on user roles (owner/staff/rostermeister/other).
  - JavaScript behavior is tested manually or via an integration test (Selenium / Playwright) if you want to assert the modal and reveal flows.

## Files changed / touched
- `members/templates/members/member_list.html` — list view now displays "Redacted" for suppressed members.
- `members/templates/members/member_view.html` — informational modal and updated rendering for redacted fields.
- `templates/base.html` — added `{% block extra_scripts %}` to ensure page scripts run after Bootstrap is available.
