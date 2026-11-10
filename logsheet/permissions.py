"""Authorization boundaries for logsheet financial actions."""

FINANCE_PERMISSION = "logsheet.can_manage_logsheet_finances"
FINANCE_EXPORT_PERMISSION = "logsheet.can_export_logsheet_finances"
STATS_DUMP_EXPORT_PERMISSION = "logsheet.can_export_stats_dump"
UNFINALIZE_PERMISSION = "logsheet.can_unfinalize_logsheet"


def has_logsheet_finance_access(user, *, export=False):
    """Return whether an active account has the requested finance capability."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm(FINANCE_EXPORT_PERMISSION if export else FINANCE_PERMISSION)


def has_stats_dump_export_access(user):
    """Check the registered stats capability; views retain member/scope rules."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(STATS_DUMP_EXPORT_PERMISSION)
    )
