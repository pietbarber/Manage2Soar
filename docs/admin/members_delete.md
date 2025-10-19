Member deletions and cascading effects
=====================================

Why deleting members is dangerous
- Members are linked across the system: flights, instruction reports, payments, maintenance ownership, roster entries, and more.
- Deleting a Member (depending on model on_delete settings) often cascades and removes related rows, which can silently erase historical data.

Safer alternatives
- Deactivate the member (set `is_active=False`) using the admin bulk action `Mark inactive` instead of deleting.
- If you must remove a member record, prefer writing a short migration or script that:
  - Reassigns or nulls foreign keys where appropriate (e.g., reassign flights to an alias account or set `on_delete=SET_NULL`).
  - Exports affected records for backup before deletion.

Checklist before deletion
- Take a DB backup or export affected rows.
- Identify related models (flights, instruction reports, payments, member badges, qualifications) and decide per-model handling.
- Run the deletion in a staging environment and review downstream reports and billing.
- Notify ops and bookkeeping teams before final deletion.