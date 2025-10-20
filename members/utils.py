from django.conf import settings



def is_privileged_viewer(user):
    """Return True if the user should bypass member redaction rules.

    Privileged viewers include superusers, staff, and optionally users with
    explicit flags like `webmaster` or users in configured groups.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or getattr(user, "is_staff", False):
        return True
    # project has boolean flags like user.webmaster, user.treasurer in members
    if getattr(user, "webmaster", False) or getattr(user, "treasurer", False):
        return True
    exempt_groups = getattr(settings, "MEMBERS_REDACT_EXEMPT_GROUPS", [])
    if not exempt_groups:
        return False
    try:
        return user.groups.filter(name__in=exempt_groups).exists()
    except Exception:
        return False


def can_view_personal_info(viewer, subject_member):
    """Return True if `viewer` may see `subject_member`'s personal contact info.

    If the subject has not redacted, allow. If redacted, allow only for
    privileged viewers.
    """
    if not getattr(subject_member, "redact_contact", False):
        return True
    return is_privileged_viewer(viewer)
