# Duty Roster Views

This document describes the main view functions in `duty_roster/views.py` and their purposes.

---

## Main Views

- **roster_home(request)**: Landing page for the duty roster app.
- **blackout_manage(request)**: Allows members to manage their blackout (unavailable) dates.
- **duty_calendar_view(request, year=None, month=None)**: Renders the main duty calendar for a given month/year.
- **calendar_day_detail(request, year, month, day)**: Shows details for a specific day, including assignments and signups.
- **ops_intent_toggle(request, year, month, day)**: Toggles a member's intent to operate on a given day.
- **ops_intent_form(request, year, month, day)**: Displays the form for submitting operational intent.
- **assignment_edit_form(request, year, month, day)**: Form to edit a duty assignment for a specific day.
- **assignment_save_form(request, year, month, day)**: Saves changes to a duty assignment.
- **calendar_ad_hoc_start/confirm(request, year, month, day)**: Handles ad-hoc (non-scheduled) ops day creation and confirmation.
- **calendar_tow_signup/dutyofficer_signup/instructor_signup/ado_signup(request, year, month, day)**: Signup views for various roles on a given day.
- **calendar_cancel_ops_day(request, year, month, day)**: Cancels an ops day and notifies members.
- **calendar_cancel_ops_modal(request, year, month, day)**: Modal dialog for confirming ops day cancellation.
- **propose_roster(request)**: Rostermeister-only view to propose/generate a new roster.

## Helper Functions

- **generate_calendar(year, month)**: Helper to build the calendar data structure.
- **get_adjacent_months(year, month)**: Returns previous/next month for navigation.
- **maybe_notify_surge_instructor/towpilot(day_date)**: Notifies surge instructors/towpilots if needed.
- **is_rostermeister(user)**: Checks if a user has rostermeister privileges.

---

## Notes
- All views use Django's request/response system and are decorated for permissions as needed.
- Calendar and assignment views are central to member and rostermeister workflows.
- For more details, see the function docstrings and inline comments in `views.py`.

---

## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [AppConfig](apps.md)
