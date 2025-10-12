# duty_roster/apps.py

This file defines the Django application configuration for the Duty Roster app.

---

## DutyRosterConfig

```python
class DutyRosterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "duty_roster"
```

### Methods & Attributes
- **default_auto_field**: Sets the default type for auto-incrementing primary keys to `BigAutoField`.
- **name**: The full Python path to the app (used by Django for app registry).

### Purpose
- Registers the Duty Roster app with Django’s app registry.
- Ensures all models and signals in the app are properly discovered and initialized.

### Usage
- This config is referenced in `INSTALLED_APPS` in `settings.py` as `"duty_roster.apps.DutyRosterConfig"` (or simply `"duty_roster"`).
- No custom methods or signals are defined in this config by default, but you can extend it to add app-specific startup logic.

---


## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Views](views.md)
