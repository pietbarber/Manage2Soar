"""Utility subpackage for members.

This package exposes selected helpers at the package level so callers can
import `from members.utils import is_active_member` and get a stable API.
"""

from .kiosk import is_kiosk_session
from .membership import is_active_member
from .permissions import (
    can_view_contact_field,
    can_view_personal_info,
    contact_field_visibility,
    is_privileged_viewer,
)
from .username import generate_username

__all__ = [
    "is_active_member",
    "can_view_personal_info",
    "can_view_contact_field",
    "contact_field_visibility",
    "is_privileged_viewer",
    "is_kiosk_session",
    "generate_username",
]
