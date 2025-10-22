# Signals in logsheet/signals.py

This document describes all signals in `logsheet/signals.py`.

---

## notify_meisters_on_issue
- Signal handler to notify rostermeisters when a new maintenance issue is created.

---

## notify_instructor_on_flight_created

- Purpose: create a `notifications.Notification` for an instructor when an instruction
	flight requires a post-flight report.

- When it runs:
	- On creation of a `Flight` that is already completed (status == "landed").
	- Additionally, when an existing `Flight` is updated and transitions from a
		non-landed state to `landed` (for example: the flight was created with a
		`launch_time` only and later edited to add a `landing_time`). This transition
		is detected via a `pre_save` handler which stores the previous `status`.

- Conditions checked before creating a notification:
	- The record is newly created OR it just transitioned to `landed`.
	- Both `pilot` and `instructor` are present and are different people.
	- The instructor does not already have an undismissed notification for the
		same `log_date` (deduplication). The dedupe is implemented by checking for
		an existing `Notification` whose message contains the `log_date` ISO string.

- Notification content & routing:
	- Message: "You have an instruction flight to complete a report for {pilot} on {log_date}."
	- URL: points to the instructors dashboard (`reverse('instructors:instructors-dashboard')`) so
		instructors can find and complete pending reports.

- Logging and diagnostics:
	- The signal emits debug logs explaining why it skipped (not created, missing
		fields, not transitioned to landed, etc.) and an info log when a
		`Notification` is created. This helps troubleshoot admin-edit flows where
		the notification might not have been created previously.

Notes & Caveats
- The current dedupe strategy is message-based (message contains ISO `log_date`).
	This is intentionally simple but somewhat brittle — a future improvement is to
	add structured fields to the `Notification` model (for example `type` and
	`related_date`) and enforce a DB-level uniqueness constraint to make dedupe
	race-safe and query-friendly.


## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
- [Management Commands](management.md)
