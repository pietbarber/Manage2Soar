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


def can_view_contact_field(viewer, subject_member, field, site_config=None):
    """Return whether a viewer may see one contact field on a member profile."""
    if field not in {"email", "phone", "address"}:
        raise ValueError(f"Unsupported contact field: {field}")
    if viewer == subject_member or is_privileged_viewer(viewer):
        return True
    if getattr(subject_member, "redact_contact", False):
        return False

    preference = (getattr(subject_member, "contact_visibility", None) or {}).get(field)
    if preference == "share":
        return True
    if preference == "hide":
        return False

    if site_config is None:
        from siteconfig.models import SiteConfiguration

        site_config = SiteConfiguration.objects.first()
    return bool(getattr(site_config, f"share_member_{field}_by_default", True))
