"""Authorization helpers for CMS page capabilities."""

from members.authorization import has_webmaster_compatibility_access
from members.utils.membership import is_active_member

CMS_VIEW_PERMISSION = "cms.view_page"
CMS_EDIT_PERMISSION = "cms.change_page"


def has_cms_view_access(user):
    """Return whether *user* has the global CMS page view capability."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False) or not is_active_member(user):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(CMS_VIEW_PERMISSION)
        or has_webmaster_compatibility_access(user)
    )


def has_cms_edit_access(user):
    """Return whether *user* has global CMS page edit capability."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False) or not is_active_member(user):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(CMS_EDIT_PERMISSION)
        or has_webmaster_compatibility_access(user)
    )


def has_legacy_cms_officer_access(user):
    """Return CMS editing capability with the legacy officer transition path.

    Stored page-role restrictions and per-member editor grants remain separate
    contextual checks in ``Page.can_user_access`` and ``Page.can_user_edit``.
    """
    if has_cms_edit_access(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False) or not is_active_member(user):
        return False
    return bool(getattr(user, "director", False) or getattr(user, "secretary", False))
