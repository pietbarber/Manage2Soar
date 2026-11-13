"""Provenance-safe reconciliation of membership status roles.

This service deliberately has no default status-to-role mappings.  Mappings are
explicit configuration, and only ``status`` assignment rows are managed here.
"""

from dataclasses import dataclass

from django.db import router, transaction

from members.models import Member, MemberRoleAssignment, RoleMetadata
from members.role_audit import internal_group_write_scope
from members.services.role_assignments import delete_role_assignments
from siteconfig.models import MembershipStatus, MembershipStatusRoleMapping


@dataclass(frozen=True)
class StatusRoleIssue:
    code: str
    detail: str


@dataclass(frozen=True)
class StatusRoleTarget:
    group_id: int
    role_key: str
    source_key: str


@dataclass(frozen=True)
class StatusRolePlan:
    member_id: int
    status_key: str | None
    inactive: bool
    desired: tuple[StatusRoleTarget, ...]
    grants: tuple[StatusRoleTarget, ...]
    revokes: tuple[StatusRoleTarget, ...]
    issues: tuple[StatusRoleIssue, ...]
    unexplained_group_ids: tuple[int, ...]

    @property
    def can_apply(self):
        return not self.issues

    @property
    def changed(self):
        return bool(self.grants or self.revokes)


@dataclass(frozen=True)
class StatusRoleResult:
    plan: StatusRolePlan
    applied: bool
    grants: int = 0
    revokes: int = 0

    @property
    def changed(self):
        return bool(self.grants or self.revokes)


@dataclass(frozen=True)
class StatusRoleBatchResult:
    results: tuple[StatusRoleResult, ...]

    @property
    def members(self):
        return len(self.results)

    @property
    def grants(self):
        return sum(len(result.plan.grants) for result in self.results)

    @property
    def revokes(self):
        return sum(len(result.plan.revokes) for result in self.results)

    @property
    def ambiguous(self):
        return sum(bool(result.plan.issues) for result in self.results)

    @property
    def unexplained(self):
        return sum(bool(result.plan.unexplained_group_ids) for result in self.results)


def status_source_key(status_key: str, role_key: str) -> str:
    """Build the stable provenance key required for a status-owned grant."""
    if not status_key or not role_key or ":" in status_key or ":" in role_key:
        raise ValueError(
            "Status and role keys must be non-empty and may not contain ':'."
        )
    return f"{status_key}:{role_key}"


def _parse_status_source_key(source_key: str):
    parts = source_key.split(":")
    if len(parts) != 2 or not all(parts):
        return None
    return tuple(parts)


def _database_alias(member, using=None):
    return using or member._state.db or router.db_for_write(Member, instance=member)


def _build_plan(member, *, using, lock=False) -> StatusRolePlan:
    status_query = MembershipStatus.objects.using(using)
    if lock:
        status_query = status_query.select_for_update()
    status = status_query.filter(name=member.membership_status).first()

    assignment_query = MemberRoleAssignment.objects.using(using).filter(
        member_id=member.pk, source="status"
    )
    existing = list(assignment_query)
    group_ids = set(member.groups.db_manager(using).values_list("pk", flat=True))
    explained_group_ids = set(
        MemberRoleAssignment.objects.using(using)
        .filter(member_id=member.pk)
        .values_list("group_id", flat=True)
    )
    unexplained_group_ids = tuple(sorted(group_ids - explained_group_ids))

    if status is None:
        return StatusRolePlan(
            member_id=member.pk,
            status_key=None,
            inactive=False,
            desired=(),
            grants=(),
            revokes=(),
            issues=(
                StatusRoleIssue(
                    "unknown_status_identity",
                    f"No MembershipStatus matches stored name {member.membership_status!r}.",
                ),
            ),
            unexplained_group_ids=unexplained_group_ids,
        )

    desired = []
    issues = []
    mappings_query = MembershipStatusRoleMapping.objects.using(using).filter(
        membership_status_id=status.pk, enabled=True
    )
    if lock:
        mappings_query = mappings_query.select_for_update()

    # Inactive statuses intentionally have no desired status-owned roles.  The
    # mappings remain intact and become effective again if the status reactivates.
    if status.is_active:
        for mapping in mappings_query.order_by("pk"):
            role_key = (
                RoleMetadata.objects.using(using)
                .filter(group_id=mapping.role_id)
                .values_list("key", flat=True)
                .first()
            )
            if not role_key:
                issues.append(
                    StatusRoleIssue(
                        "mapping_missing_role_metadata",
                        f"Mapping {mapping.pk} targets Group {mapping.role_id} without RoleMetadata.",
                    )
                )
                continue
            try:
                source_key = status_source_key(status.key, role_key)
            except ValueError as exc:
                issues.append(StatusRoleIssue("invalid_stable_key", str(exc)))
                continue
            desired.append(StatusRoleTarget(mapping.role_id, role_key, source_key))

    desired_by_key = {target.source_key: target for target in desired}
    existing_by_key = {}
    for assignment in existing:
        existing_by_key.setdefault(assignment.source_key, []).append(assignment)

    # A source key on the expected role is a match.  A duplicate or mismatched
    # row is ambiguous and is preserved rather than guessed at.
    grants = []
    matched_ids = set()
    for source_key, target in desired_by_key.items():
        rows = existing_by_key.get(source_key, [])
        if len(rows) > 1 or (rows and rows[0].group_id != target.group_id):
            issues.append(
                StatusRoleIssue(
                    "status_assignment_group_mismatch",
                    f"Status assignment {source_key!r} does not uniquely target Group {target.group_id}.",
                )
            )
        elif not rows:
            grants.append(target)
        else:
            matched_ids.add(rows[0].pk)

    known_status_keys = set(
        MembershipStatus.objects.using(using).values_list("key", flat=True)
    )
    known_role_keys = set(
        RoleMetadata.objects.using(using).values_list("key", flat=True)
    )
    revokes = []
    for assignment in existing:
        if assignment.pk in matched_ids or assignment.source_key in desired_by_key:
            continue
        parsed = _parse_status_source_key(assignment.source_key)
        if (
            not parsed
            or parsed[0] not in known_status_keys
            or parsed[1] not in known_role_keys
        ):
            issues.append(
                StatusRoleIssue(
                    "unknown_status_source_key",
                    f"Cannot validate status provenance {assignment.source_key!r}; preserving it.",
                )
            )
            continue
        role_key = (
            RoleMetadata.objects.using(using)
            .filter(group_id=assignment.group_id)
            .values_list("key", flat=True)
            .first()
            or parsed[1]
        )
        revokes.append(
            StatusRoleTarget(assignment.group_id, role_key, assignment.source_key)
        )

    return StatusRolePlan(
        member_id=member.pk,
        status_key=status.key,
        inactive=not status.is_active,
        desired=tuple(desired),
        grants=tuple(grants),
        revokes=tuple(revokes),
        issues=tuple(issues),
        unexplained_group_ids=unexplained_group_ids,
    )


def plan(member, *, using=None) -> StatusRolePlan:
    """Calculate status-owned changes without writing anything."""
    return _build_plan(member, using=_database_alias(member, using))


def apply(member, *, using=None, dry_run=False) -> StatusRoleResult:
    """Apply a plan while serializing with manual and legacy role writers.

    Ambiguous plans are deliberate no-ops.  ``dry_run`` returns the same plan
    without opening a write transaction.
    """
    db_alias = _database_alias(member, using)
    if dry_run:
        current_plan = plan(member, using=db_alias)
        return StatusRoleResult(current_plan, applied=False)

    with transaction.atomic(using=db_alias):
        locked_member = (
            Member.objects.using(db_alias).select_for_update().get(pk=member.pk)
        )
        current_plan = _build_plan(locked_member, using=db_alias, lock=True)
        if not current_plan.can_apply:
            return StatusRoleResult(current_plan, applied=False)

        revoked = 0
        for target in current_plan.revokes:
            assignments = MemberRoleAssignment.objects.using(db_alias).filter(
                member_id=locked_member.pk,
                group_id=target.group_id,
                source="status",
                source_key=target.source_key,
            )
            deleted, _ = delete_role_assignments(assignments, actor=None)
            revoked += deleted
            if (
                deleted
                and not MemberRoleAssignment.objects.using(db_alias)
                .filter(member_id=locked_member.pk, group_id=target.group_id)
                .exists()
            ):
                with internal_group_write_scope():
                    locked_member.groups.db_manager(db_alias).remove(target.group_id)

        granted = 0
        for target in current_plan.grants:
            _, created = MemberRoleAssignment.objects.using(db_alias).get_or_create(
                member_id=locked_member.pk,
                group_id=target.group_id,
                source="status",
                source_key=target.source_key,
            )
            with internal_group_write_scope():
                locked_member.groups.db_manager(db_alias).add(target.group_id)
            granted += int(created)

    return StatusRoleResult(current_plan, applied=True, grants=granted, revokes=revoked)


def reconcile_member(member, *, using=None, dry_run=False) -> StatusRoleResult:
    """Descriptive alias for callers that prefer the domain operation name."""
    return apply(member, using=using, dry_run=dry_run)


def reconcile_status_members(
    status_id, *, using=None, dry_run=False, member_ids=None, limit=None
) -> StatusRoleBatchResult:
    """Reconcile members for one status in primary-key order.

    Each member is processed through :func:`apply`, which gives every write its
    own transaction and re-checks the current status and mapping configuration.
    """
    db_alias = using or "default"
    status = MembershipStatus.objects.using(db_alias).filter(pk=status_id).first()
    if status is None:
        return StatusRoleBatchResult(())

    members = Member.objects.using(db_alias).filter(membership_status=status.name)
    if member_ids is not None:
        members = members.filter(pk__in=member_ids)
    member_queryset = members.order_by("pk")
    if limit is not None:
        member_queryset = member_queryset[:limit]

    results = tuple(
        apply(member, using=db_alias, dry_run=dry_run) for member in member_queryset
    )
    return StatusRoleBatchResult(results)
