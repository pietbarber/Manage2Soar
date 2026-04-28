# Instructor-related Notifications

This document describes the notifications emitted by the `instructors` app.

## When notifications are created

- InstructionReport created or updated: when an instructor files or edits an instruction report for a student a notification is created for the student. The notification message includes the instructor's display name and the report date. The notification links to the student's instruction record page anchored to the recorded date (for example `/instructors/instruction-record/<member_id>/#flight-2025-10-11`) so the student sees the report within the full site layout.

- GroundInstruction created or updated: when ground instruction is logged a notification is created for the student. The message includes the instructor and date and links to the student's member view when available.

- MemberQualification created or updated: when a qualification is awarded a notification is created for the member. The message includes the qualification name, awarding instructor (if any) and date. It links to the member's profile when available.

- MemberBadge awarded: when a badge is awarded, a notification is created for the member and links to the badge board.

## Email Notifications (Issue #366)

In addition to in-app notifications, instruction reports trigger email delivery:

## Instructor SPR Reminder Flow (Issue #887)

Instructor SPR reminders now happen in two stages:

- **Immediate in-app reminder on landed flight**: `logsheet.signals.notify_instructor_on_flight_created()` creates a dashboard notification when an instruction flight lands. This remains the fastest in-product cue that a report is needed.
- **Daily consolidated email reminder**: `notify_pending_sprs` sends one email per instructor for missing Student Progress Reports from the most recent finalized flying day within its lookback window that still has pending reports. This reduces noise for instructors who flew with multiple students in one day.
- **Weekly overdue escalation**: `notify_late_sprs` still handles unresolved reports once they become overdue.

### Pending SPR digest behavior

- **Recipient**: The flight instructor
- **Cadence**: Daily CronJob
- **Grouping**: One email per instructor per flight date
- **Source data**: Finalized logsheets only
- **Content**: Student list plus direct links to each report form and the instructor dashboard
- **Deduplication**: Uses the existing notification table to avoid resending the same day-specific reminder on reruns

### Timezone note

The first implementation uses a UTC Cron schedule and computes the target date from UTC (via `timezone.now().date()`), so the "previous day" boundary is always midnight UTC regardless of the server's local timezone. The job is intended to run after the previous flying day has closed, but tenant-specific timezone delivery is not yet configurable in `SiteConfiguration`.

### When emails are sent

- **After instruction report submission**: When an instructor submits an instruction report (new or updated), an email is sent to the student with the full report details.

- **Update indicator**: If the report is an update to an existing report, the email subject includes "Updated:" prefix and a prominent banner in the email body indicates this is an update to a previously submitted report.

### Email recipients

- **TO**: The student receives the instruction report email
- **CC**: If an "instructors" mailing list exists (configured via the MailingList model in siteconfig), all subscribers are CC'd on the email. This allows the instructor team to stay informed of all instruction activities.

### Email content

The instruction report email includes:
- Report date and instructor name
- New qualifications awarded (if any) with expiration dates
- Lesson scores with score descriptions
- Instructor notes/essay
- Link to the student's training logbook
- Score legend explaining the rating system (1-4 and !)

### Configuration

Email delivery is automatic and requires no configuration beyond:
1. Valid SiteConfiguration with `domain_name` set (used for from address and URLs)
2. Optional: "instructors" MailingList for CC functionality

### Implementation

- **Utility function**: `instructors/utils.py::send_instruction_report_email()`
- **Templates**: `instructors/templates/instructors/emails/instruction_report.html` and `.txt`
- **View integration**: Called from `fill_instruction_report()` view after successful save
- **Tests**: `instructors/tests/test_instruction_report_email.py` (13 tests)

## Deduplication rules

Notifications use a simple message-based dedupe: if an undismissed notification exists for the same user with an identical message, a new notification is not created. Messages include instructor/date context so multiple instructors creating records for the same student on the same day will produce distinct messages.

This avoids schema changes while still preventing immediate duplicates.

## Why we anchor to the instruction-record page

Earlier the notification linked to the instruction-report detail view (which in the UI is shown inside a modal). The modal does not include the site's full `base.html` chrome, CSS or JavaScript, so following that link produced a raw, unstyled page. Linking to the member instruction-record page with an anchor ensures the student sees the record within the full site layout.

## Tests and behavior

- Unit tests live in `instructors/tests/test_instructor_notifications.py` and assert notification creation and dedupe behavior.
- The tests explicitly call the signal handlers in order to avoid import ordering issues during test collection; the handlers are also registered via the app's `ready()` lifecycle and a defensive import in `instructors/__init__.py`.

If you change the notification text or link format, update the tests accordingly.
