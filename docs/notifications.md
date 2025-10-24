Notification deduplication for member redaction toggles
=====================================================

This project creates a `notifications.Notification` entry for member managers when a
member toggles their `redact_contact` flag. To avoid spamming member managers, the
toggle handler deduplicates notifications created for the same member URL within a
short time window.

Configuration
-------------
- `REDACTION_NOTIFICATION_DEDUPE_MINUTES` (int): number of minutes to use for
  deduplication. If set, this value takes precedence.
- `REDACTION_NOTIFICATION_DEDUPE_HOURS` (float): legacy configuration accepted for
  backward compatibility. Used only if `REDACTION_NOTIFICATION_DEDUPE_MINUTES` is
  not set.

Defaults
--------
If neither setting is provided, the dedupe window defaults to 60 minutes.
Related: the Logsheet app creates instructor notifications for completed
instruction flights (see `logsheet/docs/signals.md`); those notifications are
deduplicated by `log_date` and route instructors to the instructors dashboard.

New: the `instructors` app now creates notifications for students and members when
instruction-related records are created or updated (InstructionReport, GroundInstruction,
MemberQualification, MemberBadge). See `instructors/docs/notifications.md` for details
on message format, dedupe behavior and link targets.

Examples
--------
In your `manage2soar/settings.py` or environment-specific settings file:

REDACTION_NOTIFICATION_DEDUPE_MINUTES = 15  # dedupe for 15 minutes
