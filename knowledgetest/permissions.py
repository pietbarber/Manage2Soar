"""Authorization helpers for written-test administration."""

from members.authorization import has_webmaster_compatibility_access
from members.role_preview import has_preview_group
from members.utils.membership import is_active_member


def has_written_test_admin_access(user, *, allow_cfi=True):
    """Return whether *user* may administer written-test presets."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False) or not is_active_member(user):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or has_webmaster_compatibility_access(user)
        or (allow_cfi and has_preview_group(user, "Chief Flight Instructor"))
    )
