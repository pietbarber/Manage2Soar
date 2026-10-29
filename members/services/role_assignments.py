"""Provenance-aware manual role grants.

Direct writes to ``member.groups`` are unsupported: they do not record why a
role was granted. Existing memberships without provenance remain unresolved;
this service will not remove them when a manual source is absent.
"""

from django.core.exceptions import PermissionDenied
from django.db import router, transaction

from members.models import Member, MemberRoleAssignment, RoleMetadata


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
        assignments = MemberRoleAssignment.objects.using(using).filter(
            member_id=locked_member.pk,
            group_id=group.pk,
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
                    RoleMetadata.objects.using(using).filter(group_id=group.pk).first()
                )
                if metadata is not None and not metadata.is_assignable:
                    raise PermissionDenied(
                        f"The role {group.name!r} is not assignable."
                    )
            MemberRoleAssignment.objects.using(using).get_or_create(
                member_id=locked_member.pk,
                group_id=group.pk,
                source="manual",
                source_key=source_key,
                defaults={"actor_id": actor.pk if actor else None},
            )
            locked_member.groups.db_manager(using).add(group.pk)
        else:
            deleted, _ = assignments.delete()
            remaining = (
                MemberRoleAssignment.objects.using(using)
                .filter(member_id=locked_member.pk, group_id=group.pk)
                .exists()
            )
            if remaining:
                locked_member.groups.db_manager(using).add(group.pk)
            elif deleted:
                locked_member.groups.db_manager(using).remove(group.pk)
