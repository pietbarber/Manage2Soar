from django.conf import settings
from django.db import transaction

CONTACT_FIELDS = ("email", "phone", "address")
PRIVILEGED_CONTACT_PERMISSION = "members.view_privileged_contact"
SAFETY_REPORT_PERMISSION = "members.access_safety_reports"


def _reconcile_legacy_contact_redaction(subject_member):
    if not getattr(subject_member, "redact_contact", False):
        return

    def migrate_preferences(member):
        visibility = getattr(member, "contact_visibility", None)
        visibility = dict(visibility) if isinstance(visibility, dict) else {}
        visibility.update({field: "hide" for field in CONTACT_FIELDS})
        member.contact_visibility = visibility
        member.redact_contact = False

    state = getattr(subject_member, "_state", None)
    if state is None or not getattr(subject_member, "pk", None):
        migrate_preferences(subject_member)
        return

    manager = subject_member.__class__._default_manager
    with transaction.atomic(using=state.db):
        member = manager.using(state.db).select_for_update().get(pk=subject_member.pk)
        if member.redact_contact:
            migrate_preferences(member)
            member.save(update_fields=["contact_visibility", "redact_contact"])

        subject_member.contact_visibility = member.contact_visibility
        subject_member.redact_contact = member.redact_contact


def is_privileged_viewer(user):
    """Return whether ``user`` may bypass member contact visibility choices.

    ``is_staff`` is deliberately not used here.  Staff is an admin entry-gate
    flag and is also derived for roles such as Instructor and Secretary; it is
    not, by itself, a contact-privacy capability.  The dedicated permission
    is seeded for the four roles that historically had this explicit policy.
    Manually-created staff users therefore need an explicit grant, which is
    the intentional privacy transition rather than an unresolved fallback.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if getattr(user, "_role_preview_group_name", None) is not None:
        return user.has_perm(PRIVILEGED_CONTACT_PERMISSION)
    try:
        if user.has_perm(PRIVILEGED_CONTACT_PERMISSION):
            return True
    except Exception:
        # Keep privacy checks fail-closed for lightweight/auth-less user
        # doubles and partially configured authentication backends.
        pass
    if getattr(settings, "MEMBERS_REDACT_EXEMPT_GROUPS", []):
        try:
            return user.groups.filter(
                name__in=settings.MEMBERS_REDACT_EXEMPT_GROUPS
            ).exists()
        except Exception:
            pass
    return False


def can_view_personal_info(viewer, subject_member):
    _reconcile_legacy_contact_redaction(subject_member)
    if viewer == subject_member or is_privileged_viewer(viewer):
        return True
    return any(
        contact_field_visibility(subject_member, field)["shared"]
        for field in CONTACT_FIELDS
    )


def can_view_contact_field(viewer, subject_member, field, site_config=None):
    """Return whether a viewer may see one contact field on a member profile."""
    if field not in {"email", "phone", "address"}:
        raise ValueError(f"Unsupported contact field: {field}")
    _reconcile_legacy_contact_redaction(subject_member)
    if viewer == subject_member or is_privileged_viewer(viewer):
        return True
    if getattr(subject_member, "redact_contact", False):
        return False

    return contact_field_visibility(subject_member, field, site_config)["shared"]


def contact_field_visibility(subject_member, field, site_config=None):
    """Return effective regular-member visibility and its source."""
    if field not in {"email", "phone", "address"}:
        raise ValueError(f"Unsupported contact field: {field}")
    _reconcile_legacy_contact_redaction(subject_member)
    if getattr(subject_member, "redact_contact", False):
        return {"shared": False, "source": "legacy full redaction"}

    preference = (getattr(subject_member, "contact_visibility", None) or {}).get(field)
    if preference == "share":
        return {"shared": True, "source": "member choice: Share"}
    if preference == "hide":
        return {"shared": False, "source": "member choice: Hide"}

    if site_config is None:
        from siteconfig.models import SiteConfiguration

        site_config = SiteConfiguration.objects.first()
    shared = bool(getattr(site_config, f"share_member_{field}_by_default", True))
    return {
        "shared": shared,
        "source": f"club default: {'Share' if shared else 'Hide'}",
    }
