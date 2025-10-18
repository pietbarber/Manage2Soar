"""Compatibility shim for `members.utils`.

Historically this project allowed importing from either `members.utils` (module)
or `members.utils` (package). To be robust during refactors we expose the
helper here by delegating to the package submodule `members.utils.membership`.
"""

from .utils.membership import is_active_member  # noqa: F401

__all__ = ["is_active_member"]
