# instructors/apps.py

from django.apps import AppConfig
import sys

class InstructorsConfig(AppConfig):
    name = 'instructors'

    def ready(self):
        # Only connect signals if not running migrations, collectstatic, etc.
        if not any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'loaddata', 'test']):
            import instructors.signals  # noqa
