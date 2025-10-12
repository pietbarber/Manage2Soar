# Duty Roster Management Commands

This page documents the management commands available in the `duty_roster` app. These commands are run via `python manage.py <command>` and are intended for club administrators, rostermeisters, or site maintainers.

---

## Commands

### 1. `generate_duty_roster`
Generates a new duty roster for a specified date range, using member preferences and blackout dates.

**Usage:**
```bash
python manage.py generate_duty_roster --start YYYY-MM-DD --end YYYY-MM-DD
```
- `--start`: Start date for the roster (required)
- `--end`: End date for the roster (required)

---

### 2. `import_duty_constraints`
Imports duty constraints (e.g., blackout dates, preferences) from a CSV or JSON file.

**Usage:**
```bash
python manage.py import_duty_constraints <file.csv>
```
- `<file.csv>`: Path to the constraints file

---

### 3. `backfill_duty_preferences`
Backfills or updates member duty preferences based on historical assignments or other logic.

**Usage:**
```bash
python manage.py backfill_duty_preferences
```

---

### 4. `expire_ad_hoc_days`
Expires or removes ad-hoc duty days that are no longer valid (e.g., past dates).

**Usage:**
```bash
python manage.py expire_ad_hoc_days
```

---

### 5. `send_duty_preop_emails`
Sends pre-operation reminder emails to members assigned to upcoming duty days.

**Usage:**
```bash
python manage.py send_duty_preop_emails
```

---

### 6. `send_maintenance_digest`
Sends a digest email summarizing recent or upcoming maintenance issues to relevant members.

**Usage:**
```bash
python manage.py send_maintenance_digest
```

---

## Notes
- All commands must be run from an activated virtual environment with Django installed.
- Some commands may require additional arguments or environment variables (see command help with `--help`).
- Output and errors are printed to the console.

---


## Changelog
- **2025-10** Initial management command documentation for duty_roster.

## See Also
- [README (App Overview)](README.md)
- [AppConfig](apps.md)
- [Views](views.md)
