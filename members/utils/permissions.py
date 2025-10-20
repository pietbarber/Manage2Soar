from django.conf import settings


def is_privileged_viewer(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or getattr(user, "is_staff", False):
        return True
    # Role flags that should grant privileged viewing rights
    if (
        getattr(user, "webmaster", False)
        or getattr(user, "treasurer", False)
        or getattr(user, "member_manager", False)
        or getattr(user, "rostermeister", False)
    ):
        return True
    exempt_groups = getattr(settings, "MEMBERS_REDACT_EXEMPT_GROUPS", [])
    if not exempt_groups:
        return False
    try:
        return user.groups.filter(name__in=exempt_groups).exists()
    except Exception:
        return False


def can_view_personal_info(viewer, subject_member):
    if not getattr(subject_member, "redact_contact", False):
        return True
    return is_privileged_viewer(viewer)
