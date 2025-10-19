Flights admin — internal guidance
================================

The `Flight` admin is a low-level data editing surface used by club staff to fix or correct individual flight rows that were imported or entered incorrectly. Because flights feed billing, analytics, and maintenance automations, please follow these rules:

- Only superusers should edit flight rows directly. Other staff should use the operations UI or open an issue for ops to make changes.
- Avoid bulk edits unless you have a migration script and a backup. Bulk edits in the admin can silently affect many downstream systems.
- When updating times or release altitude, double-check cost and maintenance implications (tow cost, glider rental caps, and maintenance triggers).
- If you're unsure, add a comment to the issue tracker or ask a senior ops person before making changes.

Quick checklist before editing a flight
- Ensure you have a recent DB backup or are working on a staging environment.
- Confirm the `logsheet` date and `pilot` are correct; these are used by many automations.
- Recompute or review affected billing entries if changing `towplane`, `release_altitude`, or `duration`.

Where to edit instead
- For day-level fixes, consider editing the `Logsheet` closeout or using the operations UI where available. Those higher-level interfaces run the same business logic and are safer for non-superuser staff.

