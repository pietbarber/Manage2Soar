"""Compatibility shim: re-export permission helpers from
`members.utils.permissions` so callers can keep importing from
``members.utils`` while the canonical implementation lives in
``members.utils.permissions``.

Keep this file minimal to avoid duplication of logic.
"""

from .utils.permissions import can_view_personal_info, is_privileged_viewer

__all__ = ["is_privileged_viewer", "can_view_personal_info"]
