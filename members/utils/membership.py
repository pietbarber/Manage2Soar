from typing import Iterable, Optional

from ..constants import ALLOWED_MEMBERSHIP_STATUSES


def get_active_membership_statuses():
    """Get active membership statuses from database or fallback to constants."""
    try:
        from siteconfig.models import MembershipStatus

        return list(MembershipStatus.get_active_statuses())
    except (ImportError, Exception):
        # Fallback to hardcoded list during migrations or if table/app doesn't exist
        from ..constants.membership import DEFAULT_ACTIVE_STATUSES

        return DEFAULT_ACTIVE_STATUSES


def is_active_member(
    user, allow_superuser: bool = True, allowed_statuses: Optional[Iterable[str]] = None
) -> bool:
    """Return True when `user` should be treated as an active/member for permissions.

    - Returns False for anonymous or unauthenticated users.
    - If allow_superuser is True and user.is_superuser, returns True.
    - Otherwise checks membership_status against allowed_statuses or the active
      membership statuses from the database.
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
