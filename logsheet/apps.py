from django.apps import AppConfig


class LogsheetConfig(AppConfig):
    name = "logsheet"

    def ready(self):
        # Ensure signal handlers are imported when app is ready
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Avoid crashing during migrations or test collection
            pass
