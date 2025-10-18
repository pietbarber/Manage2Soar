"""Utility subpackage for members.

This package exposes selected helpers at the package level so callers can
import `from members.utils import is_active_member` and get a stable API.
"""

from .membership import is_active_member

__all__ = ["is_active_member"]
