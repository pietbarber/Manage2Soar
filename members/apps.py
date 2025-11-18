from django.apps import AppConfig

#########################
# MembersConfig Class

# This class defines the application configuration for the "members" app.
# It is automatically detected and used by Django when the app is loaded.

# Fields:
# - name: the full Python path to the app (used internally by Django)
# - default_auto_field: sets the default primary key type for models in this app
#   ("BigAutoField" = 64-bit integer autoincrement field)

# This config can be extended with a ready() method to connect signals or
# perform initialization logic when Django starts up.


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "members"

    def ready(self):
        """Import signal handlers when Django starts up."""
        try:
            import members.signals  # noqa
        except ImportError:
            # Signals module may not be present in some environments (e.g., during migrations or testing).
            # Safe to ignore if signals are not required.
            pass
