"""Authorization helpers for duty-roster workflows."""

from members.utils.membership import is_active_member

VIEW_DUTY_DELINQUENTS_PERMISSION = "duty_roster.view_duty_delinquents"
VIEW_ALL_SWAP_REQUESTS_PERMISSION = "duty_roster.view_all_swap_requests"
GENERATE_ROSTER_PERMISSION = "duty_roster.can_generate_roster"
EDIT_ROSTER_PERMISSION = "duty_roster.can_edit_roster"
EDIT_ROSTER_MESSAGE_PERMISSION = "duty_roster.can_edit_roster_message"
VOLUNTEER_FOR_DUTY_PERMISSION = "duty_roster.can_volunteer_for_duty"
RESCIND_OWN_DUTY_PERMISSION = "duty_roster.can_rescind_own_duty"
MANAGE_OWN_SWAP_PERMISSION = "duty_roster.can_manage_own_swap"
MANAGE_ANY_SWAP_PERMISSION = "duty_roster.can_manage_any_swap"


def has_rostermeister_access(user):
    """Return whether an active account may use rostermeister workflows."""
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not is_active_member(user)
    ):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(GENERATE_ROSTER_PERMISSION)
        or user.has_perm(EDIT_ROSTER_PERMISSION)
        or getattr(user, "rostermeister", False)
    )


def has_duty_delinquents_access(user):
    """Return whether *user* may view the duty-delinquents report."""
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not is_active_member(user)
    ):
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
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not is_active_member(user)
    ):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(VIEW_ALL_SWAP_REQUESTS_PERMISSION)
        or user.has_perm(MANAGE_ANY_SWAP_PERMISSION)
    )
