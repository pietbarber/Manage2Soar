import sys

from django.apps import AppConfig


class KnowledgetestConfig(AppConfig):
    name = "knowledgetest"
    verbose_name = "Knowledge Test"

    def ready(self):
        # Only connect signals if not running migrations, collectstatic, etc.
        if not any(
            cmd in sys.argv
            for cmd in [
                "makemigrations",
                "migrate",
                "collectstatic",
                "loaddata",
                "test",
                "pytest",
            ]
        ):
            try:
                import knowledgetest.signals  # noqa
            except ImportError:
                # Signals module may not exist during migrations/test collection
                pass
