"""
Logsheet permissions utilities

This module provides permission checking functions for logsheet operations,
particularly for determining who can unfinalize a logsheet.
"""

from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    from logsheet.models import Logsheet


def can_unfinalize_logsheet(
    user: Optional[Union["AbstractUser", object]], logsheet: "Logsheet"
) -> bool:
    """
    Determine if a user has permission to unfinalize a logsheet.

    Users who can unfinalize a logsheet:
    1. Superusers (always have permission)
    2. Treasurers (have treasurer=True role)
    3. Webmasters (have webmaster=True role)
    4. The duty officer who originally finalized the logsheet

    Args:
        user: The user requesting to unfinalize the logsheet
        logsheet: The logsheet to check permissions for

    Returns:
        bool: True if user can unfinalize the logsheet, False otherwise
    """
    # Must be authenticated
    if not user or not getattr(user, "is_authenticated", False):
        return False

    # Superusers can always unfinalize
    if user.is_superuser:
        return True

    # Treasurers can unfinalize any logsheet to correct errors
    if getattr(user, "treasurer", False):
        return True

    # Webmasters can unfinalize any logsheet for administrative purposes
    if getattr(user, "webmaster", False):
        return True

    # The duty officer who finalized the logsheet can unfinalize it
    # Check RevisionLog to see who finalized it
    from logsheet.models import RevisionLog

    finalization_revision = (
        RevisionLog.objects.filter(logsheet=logsheet, note="Logsheet finalized")
        .order_by("-revised_at")
        .first()
    )

    if finalization_revision and finalization_revision.revised_by == user:
        return True

    # No permission to unfinalize
    return False


def can_edit_logsheet(
    user: Optional[Union["AbstractUser", object]], logsheet: "Logsheet"
) -> bool:
    """
    Determine if a user can edit a logsheet.

    Users can edit if:
    1. The logsheet is not finalized (any active member can edit)
    2. The logsheet is finalized but the user can unfinalize it

    Args:
        user: The user requesting to edit the logsheet
        logsheet: The logsheet to check permissions for

    Returns:
        bool: True if user can edit the logsheet, False otherwise
    """
    # Must be authenticated
    if not user or not getattr(user, "is_authenticated", False):
        return False

    # If not finalized, anyone can edit (subject to active member decorator)
    if not logsheet.finalized:
        return True

    # If finalized, check if user can unfinalize
    return can_unfinalize_logsheet(user, logsheet)
