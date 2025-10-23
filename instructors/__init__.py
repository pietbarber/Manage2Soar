# Ensure signals are connected in test and runtime environments
try:
    from . import signals  # noqa: F401
except Exception:
    # Avoid breaking imports if signals have issues during migrations or test collection
    pass
