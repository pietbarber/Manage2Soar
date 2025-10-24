# instructors/apps.py

import sys

from django.apps import AppConfig


class InstructorsConfig(AppConfig):
    name = "instructors"

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
            import instructors.signals  # noqa
