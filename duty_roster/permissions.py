"""Authorization helpers for duty-roster workflows."""

VIEW_DUTY_DELINQUENTS_PERMISSION = "duty_roster.view_duty_delinquents"


def has_duty_delinquents_access(user):
    """Return whether *user* may view the duty-delinquents report."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(VIEW_DUTY_DELINQUENTS_PERMISSION)
        or getattr(user, "rostermeister", False)
        or getattr(user, "member_manager", False)
        or getattr(user, "director", False)
    )
