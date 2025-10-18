from typing import Iterable, Optional

from django.contrib.auth.models import AnonymousUser

from ..constants import ALLOWED_MEMBERSHIP_STATUSES


def is_active_member(
    user, allow_superuser: bool = True, allowed_statuses: Optional[Iterable[str]] = None
) -> bool:
    """Return True when `user` should be treated as an active/member for permissions.

    - Returns False for anonymous or unauthenticated users.
    - If allow_superuser is True and user.is_superuser, returns True.
    - Otherwise checks membership_status against allowed_statuses or the canonical
      `ALLOWED_MEMBERSHIP_STATUSES`.
    """
    if not user or getattr(user, "is_authenticated", False) is False:
        return False

    if allow_superuser and getattr(user, "is_superuser", False):
        return True

    statuses = (
        list(allowed_statuses)
        if allowed_statuses is not None
        else ALLOWED_MEMBERSHIP_STATUSES
    )
    membership_status = getattr(user, "membership_status", None)
    if membership_status is None:
        return False
    return membership_status in statuses
