# Logsheet App

The **Logsheet** app manages all flight operations, aircraft, maintenance, and financial records for the club. It is the operational backbone for daily flying, integrating with members, analytics, and notification systems.

- **Audience:** authenticated members (view), duty officers/rostermeisters (edit), admins (full access)
- **Route:** `/logsheet/`
- **Nav:** included via the main navbar and dashboard.

---

## Quick Start

1. Log in as a member, duty officer, or admin.
2. Visit `/logsheet/` to view or manage logsheets, flights, and maintenance.
3. Use the admin interface for advanced operations (aircraft, rates, closeouts).

---

## Pages & Permissions

- `logsheet.views.index` (dashboard, all members)
- `logsheet.views.create_logsheet` (DO/ADO, create new logsheet)
- `logsheet.views.manage_logsheet` (DO/ADO, manage daily logsheet)
- `logsheet.views.edit_flight` (DO/ADO, edit flight entries)
- `logsheet.views.maintenance_issues` (all members, view issues)
- `logsheet.views.add_maintenance_issue` (all members, report issue)
- `logsheet.views.manage_logsheet_finances` (DO/ADO, manage finances)
- `logsheet.views.edit_logsheet_closeout` (DO/ADO, closeout logsheet)

---

## URL Patterns & Parameters

- `/logsheet/` – dashboard
- `/logsheet/create/` – create new logsheet
- `/logsheet/<pk>/` – manage/view a specific logsheet
- `/logsheet/<logsheet_pk>/flight/<flight_pk>/edit/` – edit a flight
- `/logsheet/maintenance/` – list maintenance issues
- `/logsheet/maintenance/add/` – report new issue
- `/logsheet/closeout/<pk>/` – logsheet closeout

> Most views require login; edit actions require DO/ADO or admin permissions.

---

## Core Models

See [models.md](models.md) for full details and database schema.

- **Flight:** single flight log entry (pilots, aircraft, times, costs)
- **Logsheet:** daily logsheet (flights, crew, closeout)
- **Glider/Towplane:** aircraft, status, maintenance
- **MaintenanceIssue/Deadline:** tracks issues and deadlines
- **RevisionLog:** audit trail for changes
- **TowRate, LogsheetPayment, Closeouts:** financials

---

## Implementation Notes

- **Templates:** `templates/logsheet/` (dashboard, forms, closeout, maintenance)
- **Models:** `logsheet/models.py` (see database schema in models.md)
- **Forms:** `logsheet/forms.py` (flight, logsheet, closeout, maintenance)
- **Signals:** `logsheet/signals.py` (notifies rostermeisters on new issues)
- **Admin:** all core models are editable via Django admin
- **Permissions:** edit actions require DO/ADO or admin; all can view
- **Data Flows:** tightly integrated with analytics, members, and notifications

---

## Styling & Performance

- Uses Bootstrap 5 for layout and forms
- Custom styles in `static/css/baseline.css`
- Suggested DB indexes: `Flight(logsheet_id)`, `Flight(glider_id)`, `Logsheet(log_date)`

---

## Troubleshooting

- **Missing flights:** check logsheet status and permissions
- **Maintenance not saving:** ensure required fields and permissions
- **Cost not updating:** run `update_flight_costs` management command
- **Permission denied:** only DO/ADO/admin can edit

---

## Development Tips

- To add a new model: update `models.py`, run migrations, update admin/forms
- To add a new view: update `views.py`, add template, update URLs
- To import legacy data: see [management.md](management.md)

---

## Also See
- [Models](models.md)
- [Forms](forms.md)
- [Views](views.md)
- [Signals](signals.md)
- [Management Commands](management.md)

---

## Changelog

- **2025-10** Major documentation update for logsheet app
- **2025-08** Initial release: daily logsheets, flights, maintenance, closeouts
 - **2025-10-21** Updated `logsheet.signals` to notify instructors when an instruction
	 flight is created or transitions to 'landed' (post-flight report). See [Signals](signals.md).
