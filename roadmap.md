# Skyline Soaring Club Member Portal – Roadmap

This roadmap outlines current and future development goals for the Skyline Soaring Club Member Portal. Items marked as ✅ are complete.

## Completed Tasks ✅
- Move Django SECRET_KEY to `.env` file and rotate it.
- Replace `@login_required` with `@active_member_required` for superuser access.
- Set up Google OAuth2 login (secure creds, first-login handling, photo import).
- Enforce profile photo uploads to be resized and aspect-ratio checked.
- Support rich biography field with TinyMCE and image upload.
- Allow members to upload and edit profile photos.
- Add vCard QR code to member view.
- Badge management system (admin‐editable badges, member awards, board display).
- Member name formatting helper (`get_display_name`).
- Improve navigation UI (responsive hamburger menu).
- Flatpickr calendar popup for ISO date input.
- Pydenticon–based default profile avatars.
- Pull-down state selector (handles non-US members).
- Hyphenate phone numbers; differentiate home vs cell on members list; sort by last name.
- Restricted Instructors site, with its own dashboard.
- Passenger logging support (member or free-text; only when no instructor).
- Logsheet-level finances workflow & enforcement before finalization.
- Tow altitude rate model and integration with glider rental rates.
- “On account” / check payment methods; split costs.
- Duty officer essay requirement; block finalization until all gliders landed.
- Migration tool for legacy flight logs (2005+ import).
- Paginated/filtered logsheet list.
- Legacy badge import support.
- Legacy username integration for historical log linking.
- Admin UI for non-admin badge management.
- **Instructor dashboard performance**: precompute progress in `StudentProgressSnapshot` via `utils.py` + signals.  
- **Backfill command**: `backfill_student_progress_snapshot` to seed or refresh all snapshots.  
- **Instructors app docs**: created `instructors/docs/` with models.md, signals.md, utils.md, management.md, index.md.  

---

## 🚧 In Progress
- **Scheduled backfill** of snapshots (cron / django-crontab / Celery Beat).
- Logging & metrics around snapshot thresholds and dashboard load times.

---

## 📝 Upcoming To-Dos
- UI verification & automated tests (smoke tests, unit tests for snapshot helper).
- Advanced charting or export options on dashboard.
- Per-user notification rules (e.g. “alert me when a student reaches 100% ready for solo”).
- QuickBooks Online CSV export for finalized logsheets.
- Student Written Tests for pre-solo, and new solos. 
- Super Fancy Charts and plots for all club activity
- **Future-Piet**: Investigate D3.js (or similar) for interactive dashboards and ERD diagrams.  


---

## 🪦 Abandoned or Deferred
