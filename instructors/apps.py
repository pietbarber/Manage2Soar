# instructors/apps.py

from django.apps import AppConfig

class InstructorsConfig(AppConfig):
    name = 'instructors'

    def ready(self):
        # import the signals module to register handlers
        import instructors.signals  # noqa
