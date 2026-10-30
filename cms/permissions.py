"""Authorization helpers for CMS page capabilities."""

from members.authorization import has_webmaster_compatibility_access

CMS_VIEW_PERMISSION = "cms.view_page"
CMS_EDIT_PERMISSION = "cms.change_page"


def has_cms_view_access(user):
    """Return whether *user* has the global CMS page view capability."""
    if not user or not getattr(user, "is_authenticated", False):
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
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm(CMS_EDIT_PERMISSION)
        or has_webmaster_compatibility_access(user)
    )


def has_legacy_cms_officer_access(user):
    """Temporary compatibility for officer flags during role backfill."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "webmaster", False):
        return True
    return bool(getattr(user, "director", False) or getattr(user, "secretary", False))
