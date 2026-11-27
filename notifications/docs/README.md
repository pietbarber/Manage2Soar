# Notifications App Documentation

Welcome to the documentation for the **notifications** Django app. This app
stores per-member notifications (reminders, status changes, digests) created by
other parts of Manage2Soar, and controls what members see.

---

## Key Features

- Per-user `Notification` records with `read` / `dismissed` state
- Page-top notification block (context processor) on every page for
  authenticated members
- Dedicated member-facing notifications page (`/notifications/`)
- **30-day member-facing display window** (Issue #1168) — stale notifications
  are hidden from member displays without being deleted
- `cleanup_old_notifications` management command for database retention
  (Issue #290)

---

## Contents

- [Display Policy](display-policy.md): the member-facing 30-day display window
  and how it differs from database retention
