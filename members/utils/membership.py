import logging
import warnings
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


def get_active_membership_statuses() -> List[str]:
    """
    Get the list of membership statuses that are considered 'active'.

    This is the single source of truth for determining which membership statuses
    grant members access to member-only features. The statuses are configured via
    the siteconfig.MembershipStatus model in Django admin.

    Returns:
        List[str]: List of active membership status names.

    Note:
        Falls back to legacy constants only during migrations or if the
        siteconfig table doesn't exist. A deprecation warning is logged
        when fallback is used.
    """
    try:
        from siteconfig.models import MembershipStatus

        return list(MembershipStatus.get_active_statuses())
    except Exception as e:
        # Fallback to hardcoded list during migrations or if table/app doesn't exist
        from ..constants.membership import DEFAULT_ACTIVE_STATUSES

        logger.warning(
            "Using legacy DEFAULT_ACTIVE_STATUSES fallback. "
            f"Reason: {type(e).__name__}: {e}"
        )
        warnings.warn(
            "DEFAULT_ACTIVE_STATUSES is deprecated. Configure membership statuses "
            "via siteconfig.MembershipStatus in Django admin.",
            DeprecationWarning,
            stacklevel=2,
        )
        return list(DEFAULT_ACTIVE_STATUSES)


def get_all_membership_statuses() -> List[str]:
    """
    Get all available membership statuses (both active and inactive).

    This is the single source of truth for all valid membership status values.
    The statuses are configured via the siteconfig.MembershipStatus model.

    Returns:
        List[str]: List of all membership status names.

    Note:
        Falls back to legacy constants only during migrations or if the
        siteconfig table doesn't exist.
    """
    try:
        from siteconfig.models import MembershipStatus

        return list(
            MembershipStatus.objects.values_list("name", flat=True).order_by(
                "sort_order", "name"
            )
        )
    except Exception as e:
        # Fallback to hardcoded list during migrations or if table/app doesn't exist
        from ..constants.membership import ALLOWED_MEMBERSHIP_STATUSES

        logger.warning(
            "Using legacy ALLOWED_MEMBERSHIP_STATUSES fallback. "
            f"Reason: {type(e).__name__}: {e}"
        )
        warnings.warn(
            "ALLOWED_MEMBERSHIP_STATUSES is deprecated. Configure membership statuses "
            "via siteconfig.MembershipStatus in Django admin.",
            DeprecationWarning,
            stacklevel=2,
        )
        return list(ALLOWED_MEMBERSHIP_STATUSES)


def is_active_member(
    user, allow_superuser: bool = True, allowed_statuses: Optional[Iterable[str]] = None
) -> bool:
    """
    Return True when `user` should be treated as an active member for permissions.

    This function is the canonical way to check if a user has active membership.
    It uses the siteconfig.MembershipStatus model to determine active statuses.

    Args:
        user: The user to check. Can be a Member instance or any user-like object.
        allow_superuser: If True, superusers are always considered active.
        allowed_statuses: Optional override list of statuses. If None, uses
            the active statuses from siteconfig.MembershipStatus.

    Returns:
        bool: True if the user is an active member, False otherwise.

    Examples:
        >>> is_active_member(request.user)  # Check if current user is active
        >>> is_active_member(member, allow_superuser=False)  # Strict check
    """
    if not user or getattr(user, "is_authenticated", False) is False:
        return False

    if allow_superuser and getattr(user, "is_superuser", False):
        return True

    if allowed_statuses is not None:
        statuses = list(allowed_statuses)
    else:
        # Use dynamic active statuses from database
        statuses = get_active_membership_statuses()

    membership_status = getattr(user, "membership_status", None)
    if membership_status is None:
        return False
    return membership_status in statuses
