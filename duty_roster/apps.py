import sys

from django.apps import AppConfig


class DutyRosterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "duty_roster"

    def ready(self):
        # Only connect signals if not running migrations, collectstatic, etc.
        if not any(
            cmd in sys.argv
            for cmd in [
                "makemigrations",
                "migrate",
                "collectstatic",
                "loaddata",
            ]
        ):
            import duty_roster.signals  # noqa
