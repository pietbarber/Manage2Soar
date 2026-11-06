"""Read-only snapshots for comparing authorization-related database state.

The legacy projection deliberately only uses tables and relationships that
existed before the role metadata migration.  The branch projection is kept
separate because it is not meaningful to compare it with a pre-0034 database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any

from django.db import connections, transaction
from django.db.models import Q

SNAPSHOT_VERSION = 2
SUPPORTED_SNAPSHOT_VERSIONS = frozenset({SNAPSHOT_VERSION})

_LEGACY_ROLE_FLAGS = (
    "director",
    "instructor",
    "member_manager",
    "rostermeister",
    "safety_officer",
    "secretary",
    "stats_monger",
    "treasurer",
    "webmaster",
)
_LEGACY_MAILING_LIST_FIELDS = {
    "instructor": "instructor",
    "towpilot": "towpilot",
    "duty_officer": "duty_officer",
    "assistant_duty_officer": "assistant_duty_officer",
    "director": "director",
    "secretary": "secretary",
    "treasurer": "treasurer",
    "webmaster": "webmaster",
    "member_manager": "member_manager",
    "rostermeister": "rostermeister",
    "safety_officer": "safety_officer",
}
_LEGACY_MEMBER_FIELDS = (
    "username",
    "email",
    "membership_status",
    "is_active",
    "is_superuser",
    *_LEGACY_ROLE_FLAGS,
)


def _permission_names(permissions: Iterable[Any]) -> list[str]:
    return sorted(
        f"{permission.content_type.app_label}.{permission.codename}"
        for permission in permissions
    )


def _email_fingerprint(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _legacy_member_snapshot(member: Any) -> dict[str, Any]:
    """Project only authorization fields available before migration 0034."""
    group_permissions = [
        permission
        for group in member.groups.all()
        for permission in _permission_names(
            group.permissions.select_related("content_type").all()
        )
    ]
    direct_permissions = _permission_names(
        member.user_permissions.select_related("content_type").all()
    )
    if not member.is_active:
        effective_permissions = []
    elif member.is_superuser:
        from django.contrib.auth.models import Permission

        effective_permissions = _permission_names(
            Permission.objects.all().select_related("content_type")
        )
    else:
        effective_permissions = sorted(set(group_permissions) | set(direct_permissions))
    groups = [
        {
            "name": group.name,
            "permissions": _permission_names(
                group.permissions.select_related("content_type").all()
            ),
        }
        for group in member.groups.all()
    ]
    groups.sort(key=lambda group: group["name"])
    return {
        "membership_status": member.membership_status,
        "is_active": member.is_active,
        "role_flags": {
            field: bool(getattr(member, field, False)) for field in _LEGACY_ROLE_FLAGS
        },
        "groups": groups,
        "direct_permissions": direct_permissions,
        "effective_permissions": effective_permissions,
    }


def _legacy_recipient_emails(mailing_list: Any, *, using: str) -> list[str]:
    """Resolve old mailing-list criteria without role/tag model joins.

    Selectors introduced after the legacy schema are intentionally omitted from
    this projection.  They are represented in the branch-only role snapshot,
    where the current schema can resolve them safely.
    """
    from members.models import Member
    from siteconfig.models import MembershipStatus

    active_statuses = list(
        MembershipStatus.objects.using(using)
        .filter(is_active=True)
        .values_list("name", flat=True)
    )
    base_active = (
        Q(membership_status__in=active_statuses)
        & Q(is_active=True)
        & ~Q(email="")
        & ~Q(email__isnull=True)
    )
    criteria_query = Q(pk__in=[])
    for criterion in mailing_list.criteria or []:
        field = _LEGACY_MAILING_LIST_FIELDS.get(criterion)
        if field:
            criteria_query |= Q(**{field: True})
        elif criterion == "active_member":
            criteria_query |= Q(pk__in=Member.objects.using(using).filter(base_active))
        elif criterion == "private_glider_owner":
            criteria_query |= Q(
                gliders_owned__isnull=False,
                gliders_owned__club_owned=False,
                gliders_owned__is_active=True,
            )

    return sorted(
        email.strip().lower()
        for email in Member.objects.using(using)
        .filter(base_active & criteria_query)
        .values_list("email", flat=True)
        if email and email.strip()
    )


def _legacy_projection(*, include_emails: bool, using: str) -> dict[str, Any]:
    # These imports are intentionally local: importing the module must not
    # make a legacy-only capture depend on post-0034 model tables.
    from members.models import Member
    from siteconfig.models import MailingList

    members = {
        member.username: _legacy_member_snapshot(member)
        for member in Member.objects.using(using)
        # Keep this query compatible with a database whose migration head
        # predates role metadata. Without ``only()``, the current model
        # selects newly added Member columns before this projection can ignore
        # branch-only state.
        .only(*_LEGACY_MEMBER_FIELDS)
        .prefetch_related(
            "groups__permissions__content_type",
            "user_permissions__content_type",
        )
        .order_by("username")
    }

    mailing_lists = {}
    for mailing_list in MailingList.objects.using(using).order_by("name"):
        emails = _legacy_recipient_emails(mailing_list, using=using)
        data: dict[str, Any] = {
            "criteria": sorted(mailing_list.criteria or []),
            "is_active": mailing_list.is_active,
            "recipient_count": len(emails),
            "recipient_fingerprints": [_email_fingerprint(email) for email in emails],
        }
        if include_emails:
            data["recipients"] = emails
        mailing_lists[mailing_list.name] = data

    return {"authorization": {"members": members}, "recipients": mailing_lists}


def _branch_projection(*, using: str) -> dict[str, Any]:
    """Return state that only exists on the role-permissions branch."""
    from members.models import MemberRoleAssignment, RoleMetadata

    roles = [
        {
            "key": metadata.key,
            "group_name": metadata.group.name,
            "flags": {
                "is_builtin": metadata.is_builtin,
                "is_protected": metadata.is_protected,
                "is_system_managed": metadata.is_system_managed,
                "is_assignable": metadata.is_assignable,
                "mailing_list_eligible": metadata.mailing_list_eligible,
                "admin_access": metadata.admin_access,
                "qualification_permission_bundle": metadata.qualification_permission_bundle,
            },
            "permissions": _permission_names(
                metadata.group.permissions.select_related("content_type").all()
            ),
        }
        for metadata in RoleMetadata.objects.using(using)
        .select_related("group")
        .prefetch_related("group__permissions__content_type")
        .order_by("key")
    ]
    assignments = [
        {
            "member": assignment.member.username,
            "group": assignment.group.name,
            "source": assignment.source,
            "source_key": assignment.source_key,
            "actor": assignment.actor.username if assignment.actor_id else None,
        }
        for assignment in MemberRoleAssignment.objects.using(using)
        .select_related("member", "group", "actor")
        .order_by("member__username", "group__name", "source", "source_key")
    ]
    return {"roles": roles, "assignments": assignments}


def _migration_metadata(*, using: str) -> dict[str, Any]:
    """Describe the database without including host/database identifiers."""
    from django.db.migrations.loader import MigrationLoader

    connection = connections[using]
    metadata: dict[str, Any] = {
        "database_vendor": connection.vendor,
        "migration_heads": {},
    }
    try:
        loader = MigrationLoader(connection, ignore_no_migrations=True)
    except Exception as exc:  # An early/partly-created DB can lack django_migrations.
        metadata["migration_metadata_available"] = False
        metadata["migration_metadata_error"] = type(exc).__name__
        return metadata

    applied = set(loader.applied_migrations)
    heads: dict[str, list[str]] = {}
    for node in sorted(applied):
        app_label, migration_name = node
        graph_node = loader.graph.node_map.get(node)
        if graph_node is None:
            # A squashed migration may remain recorded after its replacement
            # is loaded from disk.  It is metadata, not a reason to fail a
            # read-only parity capture.
            heads.setdefault(app_label, []).append(migration_name)
            continue
        children = graph_node.children
        applied_children = {
            child[1] for child in children if child in applied and child[0] == app_label
        }
        if not applied_children:
            heads.setdefault(app_label, []).append(migration_name)
    metadata["migration_heads"] = {
        app_label: sorted(names) for app_label, names in sorted(heads.items())
    }
    metadata["migration_metadata_available"] = True
    return metadata


@contextmanager
def _read_transaction(*, using: str):
    """Capture a consistent read and request read-only mode where supported."""
    connection = connections[using]
    outer_atomic = connection.in_atomic_block
    with transaction.atomic(using=using):
        if connection.vendor == "postgresql" and not outer_atomic:
            # SET TRANSACTION must be the first statement in the outer
            # transaction.  Do not attempt it inside a caller's transaction.
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
        yield


def build_authorization_snapshot(
    *,
    include_emails: bool = False,
    legacy_compatible: bool = False,
    projection: str | None = None,
    using: str = "default",
) -> dict[str, Any]:
    """Return a deterministic snapshot.

    ``legacy_compatible=True`` (or ``projection="legacy"``) avoids all
    post-0034 model queries and is the projection to use for before/after
    parity against a pre-role-metadata database.
    """
    if projection is None:
        projection = "legacy" if legacy_compatible else "full"
    if projection not in {"legacy", "full"}:
        raise ValueError(f"Unknown authorization snapshot projection: {projection}")

    with _read_transaction(using=using):
        snapshot: dict[str, Any] = {
            "snapshot_version": SNAPSHOT_VERSION,
            "projection": projection,
            "schema": _migration_metadata(using=using),
            "legacy": _legacy_projection(include_emails=include_emails, using=using),
        }
        if projection == "full":
            snapshot["branch"] = _branch_projection(using=using)
        return snapshot


def build_legacy_authorization_snapshot(
    *, include_emails: bool = False, using: str = "default"
) -> dict[str, Any]:
    """Explicit alias for captures that must work before migration 0034."""
    return build_authorization_snapshot(
        include_emails=include_emails,
        legacy_compatible=True,
        using=using,
    )


def _validate_snapshot(snapshot: dict[str, Any], label: str) -> None:
    version = snapshot.get("snapshot_version")
    if type(version) is not int or version not in SUPPORTED_SNAPSHOT_VERSIONS:
        raise ValueError(
            f"{label} uses unsupported snapshot version {version!r}; "
            f"supported versions: {sorted(SUPPORTED_SNAPSHOT_VERSIONS)}"
        )
    if snapshot.get("projection") not in {"legacy", "full"}:
        raise ValueError(f"{label} has an unknown snapshot projection")
    if not isinstance(snapshot.get("legacy"), dict):
        raise ValueError(f"{label} has no compatible legacy projection")


def _diff_values(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, list) and isinstance(after, list):
        if all(isinstance(item, dict) for item in before + after):
            key_fields = (
                ("key",),
                ("name",),
                ("member", "group", "source", "source_key"),
            )
            key_field = next(
                (
                    fields
                    for fields in key_fields
                    if all(field in item for item in before + after for field in fields)
                ),
                None,
            )
            if key_field:

                def keyed(items):
                    return {
                        tuple(item[field] for field in key_field): item
                        for item in items
                    }

                before_by_key = keyed(before)
                after_by_key = keyed(after)
                differences = []
                for key in sorted(set(before_by_key) | set(after_by_key)):
                    child = f"{path}[{','.join(map(str, key))}]"
                    if key not in before_by_key:
                        differences.append(
                            {"path": child, "kind": "added", "after": after_by_key[key]}
                        )
                    elif key not in after_by_key:
                        differences.append(
                            {
                                "path": child,
                                "kind": "removed",
                                "before": before_by_key[key],
                            }
                        )
                    else:
                        differences.extend(
                            _diff_values(before_by_key[key], after_by_key[key], child)
                        )
                return differences
        if before != after:
            return [{"path": path, "kind": "changed", "before": before, "after": after}]
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        differences = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            if key not in before:
                differences.append(
                    {"path": child, "kind": "added", "after": after[key]}
                )
            elif key not in after:
                differences.append(
                    {"path": child, "kind": "removed", "before": before[key]}
                )
            else:
                differences.extend(_diff_values(before[key], after[key], child))
        return differences
    if before != after:
        return [{"path": path, "kind": "changed", "before": before, "after": after}]
    return []


def compare_authorization_snapshot_details(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    """Compare stable parity and report branch state without equating it.

    Schema metadata and branch-only roles/assignments are deliberately not
    part of the stable parity result.  A legacy-only capture therefore compares
    safely with a full capture taken after the role metadata migration.
    """
    _validate_snapshot(before, "Before snapshot")
    _validate_snapshot(after, "After snapshot")
    legacy_differences = _diff_values(before["legacy"], after["legacy"], "legacy")
    details: dict[str, Any] = {
        "legacy_differences": legacy_differences,
        "branch_comparable": "branch" in before and "branch" in after,
        "branch_differences": [],
        "schema_changed": before.get("schema") != after.get("schema"),
    }
    if details["branch_comparable"]:
        details["branch_differences"] = _diff_values(
            before["branch"], after["branch"], "branch"
        )
    return details


def compare_authorization_snapshots(
    before: dict[str, Any], after: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return stable legacy field-level differences.

    Branch-only metadata/assignment additions are intentionally excluded from
    this list because they cannot be directly equal to a pre-0034 snapshot.
    Use :func:`compare_authorization_snapshot_details` for those diagnostics.
    """
    return compare_authorization_snapshot_details(before, after)["legacy_differences"]


def snapshot_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
