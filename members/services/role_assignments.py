"""Provenance-aware manual role grants.

Direct writes to ``member.groups`` are unsupported: they do not record why a
role was granted. Existing memberships without provenance remain unresolved;
this service will not remove them when a manual source is absent.
"""

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import router, transaction

from members.models import (
    Member,
    MemberRoleAssignment,
    RoleMetadata,
)
from members.role_audit import actor_scope


def delete_role_assignments(assignments, *, actor):
    """Delete provenance rows through the audited revocation path.

    Direct assignment deletion is reserved for system cleanup and cascades.
    Callers that know the acting user pass it here so the delete signal records
    an attributed revoke instead of a blank system actor.
    """
    with actor_scope(actor):
        return assignments.delete()


def set_manual_role(member, group, *, enabled: bool, actor=None, source_key="admin"):
    """Grant or revoke exactly one manual source and reconcile its effective role.

    Repeated grants leave the original actor and timestamps unchanged. A
    revocation without this source does not claim ownership of a direct M2M
    membership, so it cannot remove one.
    """
    using = member._state.db or router.db_for_write(Member, instance=member)
    with transaction.atomic(using=using):
        # Serialize all writers using this service for a member, including
        # grants with different source keys to the same Group.
        locked_member = (
            Member.objects.using(using).select_for_update().get(pk=member.pk)
        )
        # Audit snapshots must never trust caller-supplied model state. Reload
        # the role and actor from the selected database for canonical identity.
        locked_group = Group.objects.using(using).get(pk=group.pk)
        locked_actor = None
        if actor is not None:
            locked_actor = Member.objects.using(using).get(pk=actor.pk)

        assignments = MemberRoleAssignment.objects.using(using).filter(
            member_id=locked_member.pk,
            group_id=locked_group.pk,
            source="manual",
            source_key=source_key,
        )
        if enabled:
            # A role which has explicitly been made non-assignable may still
            # have historical/manual provenance.  Do not strand those rows,
            # but do prevent creating a new manual grant.  Groups without
            # metadata are legacy data and remain assignable.
            if not assignments.exists():
                metadata = (
                    RoleMetadata.objects.using(using)
                    .filter(group_id=locked_group.pk)
                    .first()
                )
                if metadata is not None and not metadata.is_assignable:
                    raise PermissionDenied(
                        f"The role {locked_group.name!r} is not assignable."
                    )
            # The creation signal appends the grant event inside this scope, so
            # the administrator is recorded consistently with the revoke path.
            with actor_scope(locked_actor):
                MemberRoleAssignment.objects.using(using).get_or_create(
                    member_id=locked_member.pk,
                    group_id=locked_group.pk,
                    source="manual",
                    source_key=source_key,
                    defaults={"actor_id": locked_actor.pk if locked_actor else None},
                )
            locked_member.groups.db_manager(using).add(locked_group.pk)
        else:
            # The deletion signal appends the revoke event so that direct and
            # cascade assignment deletion is audited consistently.
            deleted, _ = delete_role_assignments(assignments, actor=locked_actor)
            remaining = (
                MemberRoleAssignment.objects.using(using)
                .filter(member_id=locked_member.pk, group_id=locked_group.pk)
                .exists()
            )
            if remaining:
                locked_member.groups.db_manager(using).add(locked_group.pk)
            elif deleted:
                locked_member.groups.db_manager(using).remove(locked_group.pk)
