import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class LogsheetConfig(AppConfig):
    name = "logsheet"

    def ready(self):
        # Ensure signal handlers are imported when app is ready
        try:
            from . import signals  # noqa: F401
        except ImportError:
            # Signals module may not exist during migrations/test collection
            logger.debug(
                "logsheet.signals not available during migrations/test collection")
