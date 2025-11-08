# Ensure signals are connected in test and runtime environments
import logging

logger = logging.getLogger(__name__)

try:
    from . import signals  # noqa: F401
except ImportError:
    # Signals module may not exist in some test/migration contexts; skip safely
    logger.debug("instructors.signals not available, skipping import")
