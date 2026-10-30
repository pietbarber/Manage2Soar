"""Authorization helpers for duty-roster workflows."""

VIEW_DUTY_DELINQUENTS_PERMISSION = "duty_roster.view_duty_delinquents"
VIEW_ALL_SWAP_REQUESTS_PERMISSION = "duty_roster.view_all_swap_requests"


def has_rostermeister_access(user):
    """Return whether *user* has the legacy rostermeister role."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "rostermeister", False)
    )


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


def has_all_swap_requests_access(user):
    """Return whether *user* may inspect swaps outside their own context."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(VIEW_ALL_SWAP_REQUESTS_PERMISSION)
        # Compatibility for manually staff-marked accounts during rollout.
        or getattr(user, "is_staff", False)
    )
