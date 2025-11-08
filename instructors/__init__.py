# Ensure signals are connected in test and runtime environments
import logging

logger = logging.getLogger(__name__)

# Signal imports moved to apps.py ready() method to avoid circular imports
