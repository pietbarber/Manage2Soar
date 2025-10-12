# Views in logsheet/views.py

This document summarizes all classes and functions in `logsheet/views.py`.

---

## Main View Functions
- **index(request)**: Main logsheet dashboard.
- **create_logsheet(request)**: Create a new logsheet for a day.
- **manage_logsheet(request, pk)**: Manage a specific logsheet and its flights.
- **view_flight(request, pk)**: View details of a specific flight.
- **list_logsheets(request)**: List all logsheets.
- **edit_flight(request, logsheet_pk, flight_pk)**: Edit a specific flight entry.
- **add_flight(request, logsheet_pk)**: Add a new flight to a logsheet.
- **delete_flight(request, logsheet_pk, flight_pk)**: Delete a flight from a logsheet.
- **manage_logsheet_finances(request, pk)**: Manage finances for a logsheet.
- **edit_logsheet_closeout(request, pk)**: Edit the closeout for a logsheet.
- **view_logsheet_closeout(request, pk)**: View the closeout for a logsheet.
- **add_maintenance_issue(request, logsheet_id)**: Report a new maintenance issue.
- **equipment_list(request)**: List all equipment (gliders, towplanes).
- **maintenance_issues(request)**: List all open maintenance issues.
- **mark_issue_resolved(request, issue_id)**: Mark a maintenance issue as resolved.
- **resolve_maintenance_modal(request, issue_id)**: Modal for resolving maintenance issues.
- **resolve_maintenance_issue(request, issue_id)**: Resolve a maintenance issue.
- **maintenance_resolve_modal(request, issue_id)**: Modal for maintenance resolution.
- **maintenance_mark_resolved(request, issue_id)**: Mark maintenance as resolved.
- **maintenance_deadlines(request)**: List all maintenance deadlines.
- **glider_logbook(request, pk)**: View the logbook for a glider.
- **towplane_logbook(request, pk)**: View the logbook for a towplane.

---

## Also See
- [README (App Overview)](README.md)
- [Models](models.md)
- [Forms](forms.md)
- [Signals](signals.md)
- [Management Commands](management.md)
