"""Read-only provenance for global member permissions.

``get_permission_sources(member, permission=None)`` returns JSON-serializable
data keyed by full ``app_label.codename``. Passing a permission includes that
key even if it has no configured sources; omitting it lists configured grants
only (superuser overrides are not expanded into every permission).

``effective`` is the result of ``member.has_perm`` at evaluation time. Django's
ModelBackend may cache direct/group permissions on the supplied member object;
use a freshly loaded member after modifying those grants. Qualification grants
are checked afresh by QualificationPermissionBackend.
"""

from collections import defaultdict

from django.utils import timezone

from instructors.models import (
    QUALIFICATION_ALLOWED_PERMISSIONS,
    MemberQualification,
    QualificationPermissionGrant,
)
from members.auth_backends import QualificationPermissionBackend
from members.models import MemberRoleAssignment


def _permission_name(permission):
    return f"{permission.content_type.app_label}.{permission.codename}"


def _is_unsafe_permission(permission):
    """Return whether a permission is outside the qualification allowlist."""
    return _permission_name(permission) not in QUALIFICATION_ALLOWED_PERMISSIONS


def get_permission_sources(member, permission=None):
    """Describe every configured source for one or all global permissions.

    Group assignment rows are provenance for actual group membership, not
    grants in their own right. An untracked group has one explicit unknown row.
    The row's ``effective`` indicates whether *this source* is usable; the
    permission's ``effective`` is the active-user-gated ``has_perm`` answer.
    """
    if permission is not None and (
        not isinstance(permission, str) or permission.count(".") != 1
    ):
        raise ValueError("permission must be a full app_label.codename")

    sources = defaultdict(list)
    user_active = bool(member.is_active)
    active_member = bool(member.is_active_member())

    direct = member.user_permissions.select_related("content_type").order_by(
        "content_type__app_label", "codename", "pk"
    )
    for grant in direct:
        sources[_permission_name(grant)].append(
            {"type": "direct", "permission_id": grant.pk, "effective": user_active}
        )

    assignments = defaultdict(list)
    for assignment in MemberRoleAssignment.objects.filter(member=member).order_by("pk"):
        assignments[assignment.group_id].append(assignment)

    groups = (
        member.groups.prefetch_related("permissions__content_type")
        .select_related("role_metadata")
        .order_by("pk")
    )
    for group in groups:
        try:
            metadata = group.role_metadata
        except group.__class__.role_metadata.RelatedObjectDoesNotExist:
            metadata = None
        group_info = {
            "group_id": group.pk,
            "group_name": group.name,
            "role_key": metadata.key if metadata else None,
            "role_label": metadata.display_name if metadata else None,
        }
        provenance = assignments[group.pk]
        for grant in sorted(
            group.permissions.all(),
            key=lambda p: (p.content_type.app_label, p.codename, p.pk),
        ):
            name = _permission_name(grant)
            for assignment in provenance:
                sources[name].append(
                    {
                        "type": "group",
                        "permission_id": grant.pk,
                        **group_info,
                        "source": assignment.source,
                        "source_key": assignment.source_key,
                        "actor_id": assignment.actor_id,
                        "assignment_id": assignment.pk,
                        "effective": user_active,
                    }
                )
            if not provenance:
                sources[name].append(
                    {
                        "type": "group",
                        "permission_id": grant.pk,
                        **group_info,
                        "source": "untracked",
                        "source_key": None,
                        "actor_id": None,
                        "assignment_id": None,
                        "effective": user_active,
                    }
                )

    today = timezone.localdate()
    # Do not filter these records by current backend eligibility.  A configured
    # grant is useful provenance even after its bundle or permission changes.
    qualification_records = MemberQualification.objects.filter(
        member=member, qualification__permission_group__isnull=False
    ).select_related("qualification__permission_group__role_metadata")

    # Restrict to approved (group, permission) pairs AND actual group grants.
    # The backend is also consulted so no row claims a grant it would reject.
    backend_grants = QualificationPermissionBackend().get_group_permissions(member)
    for record in qualification_records.select_related("qualification").order_by("pk"):
        group_id = record.qualification.permission_group_id
        is_current = (
            record.is_qualified
            and not record.qualification.is_obsolete
            and (record.expiration_date is None or record.expiration_date >= today)
        )
        for grant in (
            QualificationPermissionGrant.objects.filter(
                group_id=group_id,
            )
            .select_related("permission__content_type")
            .order_by("permission_id")
        ):
            name = _permission_name(grant.permission)
            try:
                metadata = record.qualification.permission_group.role_metadata
            except (
                record.qualification.permission_group.__class__.role_metadata.RelatedObjectDoesNotExist
            ):
                metadata = None
            bundle_enabled = bool(
                metadata
                and metadata.qualification_permission_bundle
                and not metadata.is_builtin
                and not metadata.is_protected
                and not metadata.is_system_managed
            )
            permission_in_group = (
                record.qualification.permission_group.permissions.filter(
                    pk=grant.permission_id
                ).exists()
            )
            unsafe = _is_unsafe_permission(grant.permission)
            effective = (
                user_active
                and active_member
                and is_current
                and bundle_enabled
                and permission_in_group
                and not unsafe
                and name in backend_grants
            )
            ineffective_reason = None
            if not record.is_qualified:
                ineffective_reason = "revoked"
            elif record.qualification.is_obsolete:
                ineffective_reason = "obsolete_qualification"
            elif record.expiration_date is not None and record.expiration_date < today:
                ineffective_reason = "expired"
            elif not user_active:
                ineffective_reason = "inactive_account"
            elif not active_member:
                ineffective_reason = "inactive_membership"
            elif not bundle_enabled:
                ineffective_reason = "bundle_disabled"
            elif not permission_in_group:
                ineffective_reason = "permission_removed"
            elif unsafe:
                ineffective_reason = "unsafe_permission"
            elif name not in backend_grants:
                ineffective_reason = "backend_rejected"
            sources[name].append(
                {
                    "type": "qualification",
                    "permission_id": grant.permission_id,
                    "qualification_id": record.qualification_id,
                    "qualification_code": record.qualification.code,
                    "member_qualification_id": record.pk,
                    "group_id": group_id,
                    "expiration_date": (
                        record.expiration_date.isoformat()
                        if record.expiration_date
                        else None
                    ),
                    "effective": effective,
                    "ineffective_reason": ineffective_reason,
                }
            )

    if permission is not None:
        sources.setdefault(permission, [])
    permissions = {}
    for name in sorted(sources):
        rows = sources[name]
        if permission is not None and name != permission:
            continue
        if member.is_superuser:
            rows.append({"type": "superuser", "effective": user_active})
        permissions[name] = {
            "effective": bool(user_active and member.has_perm(name)),
            "sources": rows,
        }

    return {
        "member_id": member.pk,
        "is_active": user_active,
        "is_active_member": active_member,
        "superuser_override": bool(member.is_superuser and user_active),
        "cache_warning": "Django may cache direct and group permissions on this member object; reload it after grant changes.",
        "permissions": permissions,
    }
