# Member-Facing Notification Display Policy

Members see only recent notifications. This is a **display** policy: it
controls what is shown, not what is stored.

## 30-day rolling display window (Issue #1168)

- Notifications created more than **30 days** before the current time are hidden
  from both member-facing display paths:
  - the page-top notification block (rendered on every page for authenticated
    members, driven by `notifications.context_processors.notifications`), and
  - the dedicated notifications page (`/notifications/`,
    `notifications.views.notifications_list`).
- The window is rolling and timezone-aware. At request time, the cutoff is
  `django.utils.timezone.now() - timedelta(days=30)`. A notification created
  exactly at the cutoff is still eligible; one older than the cutoff is hidden.
- The filter is applied in the database query —
  `NotificationQuerySet.for_display` in `notifications/models.py` — so both
  display paths share one implementation and cannot drift.
- The window never deletes or mutates records. Expired notifications remain in
  the database with their existing `read` / `dismissed` state. Viewing a page
  changes nothing.
- Dismissal of visible notifications works as before; dismissed notifications
  remain hidden.
- The existing stale overdue-SPR suppression (hiding an overdue-SPR reminder
  when the instructor no longer has overdue SPRs) applies on top of the window
  in the page-top display.

## Display vs. retention

The display window is **not** the retention policy:

| | Display window | Database retention |
|---|---|---|
| Purpose | What members can see | What stays in the database |
| Age | 30 days (rolling, evaluated per request) | 60 days by default (`--days`) |
| Effect | Hides records from member displays | Permanently deletes records (dismissed and undismissed) |
| Where | `notifications/models.py` (`for_display`) | `cleanup_old_notifications` management command (Issue #290) |

The `cleanup_old_notifications` command permanently purges notifications older
than 60 days by default. Whether and when it runs in production is a separate
deployment concern tracked with the Issue #1168 follow-ups (alongside the
corrections to `docs/cronjob-architecture.md`); the display window works
independently of whether any cleanup job is scheduled.
