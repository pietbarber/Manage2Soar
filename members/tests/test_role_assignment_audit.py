import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from members.models import (
    Member,
    MemberRoleAssignment,
    MemberRoleAssignmentEvent,
    RoleMetadata,
)
from members.role_audit import actor_scope
from members.services.role_assignments import set_manual_role


@pytest.fixture
def audit_member():
    return Member.objects.create_user(username="audit-target")


@pytest.fixture
def audit_group():
    group = Group.objects.create(name="Audit role")
    RoleMetadata.objects.create(
        group=group, key="audit_role", display_name="Audit role"
    )
    return group


@pytest.mark.django_db
def test_grant_records_target_role_source_and_actor(audit_member, audit_group):
    actor = Member.objects.create_user(username="audit-actor")

    set_manual_role(
        audit_member,
        audit_group,
        enabled=True,
        actor=actor,
        source_key="committee",
    )

    event = MemberRoleAssignmentEvent.objects.get()
    assert (
        event.action,
        event.member_id,
        event.member_id_snapshot,
        event.member_username,
        event.group_id_snapshot,
        event.group_name,
        event.role_key,
        event.actor_id,
        event.actor_id_snapshot,
        event.actor_username,
        event.source,
        event.source_key,
    ) == (
        "grant",
        audit_member.pk,
        audit_member.pk,
        "audit-target",
        audit_group.pk,
        "Audit role",
        "audit_role",
        actor.pk,
        actor.pk,
        "audit-actor",
        "manual",
        "committee",
    )
    assert event.timestamp is not None


@pytest.mark.django_db
def test_revoke_records_event_and_repeated_calls_are_idempotent(
    audit_member, audit_group
):
    set_manual_role(audit_member, audit_group, enabled=True)
    set_manual_role(audit_member, audit_group, enabled=True)
    set_manual_role(audit_member, audit_group, enabled=False)
    set_manual_role(audit_member, audit_group, enabled=False)

    assert list(MemberRoleAssignmentEvent.objects.values_list("action", flat=True)) == [
        "grant",
        "revoke",
    ]


@pytest.mark.django_db
def test_revoke_snapshots_actor_identity(audit_member, audit_group):
    actor = Member.objects.create_user(username="audit-revoker")
    actor_id = actor.pk
    set_manual_role(audit_member, audit_group, enabled=True)
    set_manual_role(audit_member, audit_group, enabled=False, actor=actor)

    event = MemberRoleAssignmentEvent.objects.get(action="revoke")
    actor.delete()
    event.refresh_from_db()

    assert event.actor_id is None
    assert event.actor_id_snapshot == actor_id
    assert event.actor_username == "audit-revoker"


@pytest.mark.django_db
def test_deleting_target_and_actor_together_records_revoke(audit_member, audit_group):
    actor = Member.objects.create_user(username="bulk-delete-actor")
    actor_id = actor.pk
    set_manual_role(audit_member, audit_group, enabled=True, actor=actor)

    with actor_scope(actor):
        Member.objects.filter(pk__in=[audit_member.pk, actor_id]).delete()

    revoke = MemberRoleAssignmentEvent.objects.get(action="revoke")
    assert revoke.member_id is None
    assert revoke.member_id_snapshot == audit_member.pk
    assert revoke.actor_id is None
    assert revoke.actor_id_snapshot == actor_id
    assert revoke.actor_username == "bulk-delete-actor"


@pytest.mark.django_db
def test_deleting_actor_keeps_live_assignment_and_audit_snapshot(
    audit_member, audit_group
):
    actor = Member.objects.create_user(username="granting-actor")
    actor_id = actor.pk
    set_manual_role(audit_member, audit_group, enabled=True, actor=actor)

    actor.delete()

    assignment = MemberRoleAssignment.objects.get(
        member=audit_member, group=audit_group
    )
    assert assignment.actor_id is None

    event = MemberRoleAssignmentEvent.objects.get(action="grant")
    assert event.actor_id is None
    assert event.actor_id_snapshot == actor_id
    assert event.actor_username == "granting-actor"


@pytest.mark.django_db
def test_event_survives_target_member_deletion(audit_member, audit_group):
    member_id = audit_member.pk
    set_manual_role(audit_member, audit_group, enabled=True)
    event = MemberRoleAssignmentEvent.objects.get()

    audit_member.delete()
    event.refresh_from_db()

    assert event.member_id is None
    assert event.member_id_snapshot == member_id
    assert event.member_username == "audit-target"


@pytest.mark.django_db
def test_each_manual_source_has_its_own_grant_and_revoke_events(
    audit_member, audit_group
):
    set_manual_role(audit_member, audit_group, enabled=True, source_key="admin")
    set_manual_role(audit_member, audit_group, enabled=True, source_key="committee")
    set_manual_role(audit_member, audit_group, enabled=False, source_key="admin")

    assert list(
        MemberRoleAssignmentEvent.objects.values_list("action", "source_key")
    ) == [("grant", "admin"), ("grant", "committee"), ("revoke", "admin")]


@pytest.mark.django_db
def test_event_survives_assignment_and_group_deletion(audit_member, audit_group):
    set_manual_role(audit_member, audit_group, enabled=True)
    event = MemberRoleAssignmentEvent.objects.get()
    group_id = audit_group.pk
    MemberRoleAssignment.objects.get(member=audit_member, group=audit_group).delete()

    event.refresh_from_db()
    assert event.group_id == group_id
    assert event.group_id_snapshot == group_id

    audit_group.delete()

    event.refresh_from_db()
    assert event.group_id is None
    assert event.group_id_snapshot == group_id
    assert event.group_name == "Audit role"
    assert event.role_key == "audit_role"


@pytest.mark.django_db
def test_direct_assignment_deletion_records_system_revoke(audit_member, audit_group):
    set_manual_role(audit_member, audit_group, enabled=True)

    MemberRoleAssignment.objects.get(member=audit_member, group=audit_group).delete()

    revoke = MemberRoleAssignmentEvent.objects.get(action="revoke")
    assert revoke.member_id == audit_member.pk
    assert revoke.group_id == audit_group.pk
    assert revoke.member_id_snapshot == audit_member.pk
    assert revoke.group_id_snapshot == audit_group.pk
    assert revoke.actor_id is None
    assert revoke.actor_username == ""


@pytest.mark.django_db
def test_group_cascade_records_revoke_with_snapshot_identity(audit_member, audit_group):
    set_manual_role(audit_member, audit_group, enabled=True)
    group_id = audit_group.pk

    audit_group.delete()

    revoke = MemberRoleAssignmentEvent.objects.get(action="revoke")
    assert revoke.group_id is None
    assert revoke.group_id_snapshot == group_id
    assert revoke.group_name == "Audit role"
    # pre_delete captures RoleMetadata before the cascade removes it, so the
    # stable role key survives even though RoleMetadata is gone afterwards.
    assert revoke.role_key == "audit_role"
    assert revoke.member_id_snapshot == audit_member.pk
    assert revoke.member_username == "audit-target"


@pytest.mark.django_db
def test_direct_assignment_creation_records_system_grant(audit_member, audit_group):
    MemberRoleAssignment.objects.create(
        member=audit_member,
        group=audit_group,
        source="manual",
        source_key="direct-write",
    )

    event = MemberRoleAssignmentEvent.objects.get()
    assert event.action == "grant"
    assert event.member_id == audit_member.pk
    assert event.member_id_snapshot == audit_member.pk
    assert event.member_username == "audit-target"
    assert event.group_id == audit_group.pk
    assert event.group_id_snapshot == audit_group.pk
    assert event.group_name == "Audit role"
    assert event.role_key == "audit_role"
    assert event.actor_id is None
    assert event.actor_username == ""
    assert event.source == "manual"
    assert event.source_key == "direct-write"


@pytest.mark.django_db
def test_direct_assignment_creation_uses_named_actor(audit_member, audit_group):
    actor = Member.objects.create_user(username="direct-actor")

    MemberRoleAssignment.objects.create(
        member=audit_member,
        group=audit_group,
        source="manual",
        source_key="direct-actor-write",
        actor=actor,
    )

    event = MemberRoleAssignmentEvent.objects.get()
    assert event.actor_id == actor.pk
    assert event.actor_id_snapshot == actor.pk
    assert event.actor_username == "direct-actor"


@pytest.mark.django_db
def test_direct_assignment_creation_uses_actor_scope(audit_member, audit_group):
    actor = Member.objects.create_user(username="scoped-actor")

    with actor_scope(actor):
        MemberRoleAssignment.objects.create(
            member=audit_member,
            group=audit_group,
            source="manual",
            source_key="scoped-write",
        )

    event = MemberRoleAssignmentEvent.objects.get()
    assert event.actor_id == actor.pk
    assert event.actor_username == "scoped-actor"


@pytest.mark.django_db
def test_assignment_provenance_rejects_update_and_bulk_creation(
    audit_member, audit_group
):
    assignment = MemberRoleAssignment.objects.create(
        member=audit_member,
        group=audit_group,
        source="manual",
        source_key="immutable-check",
    )

    with pytest.raises(ValidationError, match="immutable"):
        assignment.source_key = "changed"
        assignment.save()

    with pytest.raises(ValidationError, match="immutable"):
        MemberRoleAssignment.objects.filter(pk=assignment.pk).update(
            source_key="changed"
        )

    with pytest.raises(ValidationError, match="service"):
        MemberRoleAssignment.objects.bulk_create(
            [
                MemberRoleAssignment(
                    member=audit_member,
                    group=audit_group,
                    source="manual",
                    source_key="bulk",
                )
            ]
        )


@pytest.mark.django_db
def test_audit_snapshots_ignore_stale_caller_objects(audit_member, audit_group):
    actor = Member.objects.create_user(username="audit-real-actor")
    audit_group.name = "Spoofed role"
    actor.username = "spoofed-actor"

    set_manual_role(audit_member, audit_group, enabled=True, actor=actor)

    event = MemberRoleAssignmentEvent.objects.get()
    assert event.group_name == "Audit role"
    assert event.actor_username == "audit-real-actor"


@pytest.mark.django_db
def test_event_model_rejects_mutation_and_deletion(audit_member, audit_group):
    set_manual_role(audit_member, audit_group, enabled=True)
    event = MemberRoleAssignmentEvent.objects.get()

    event.group_name = "changed"
    with pytest.raises(ValidationError, match="immutable"):
        event.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        event.delete()

    with pytest.raises(ValidationError, match="immutable"):
        MemberRoleAssignmentEvent.objects.all().update(group_name="changed")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        MemberRoleAssignmentEvent.objects.all().delete()
    with pytest.raises(ValidationError, match="immutable"):
        MemberRoleAssignmentEvent._base_manager.all().update(group_name="changed")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        MemberRoleAssignmentEvent._base_manager.all().delete()

    event.pk = None
    with pytest.raises(ValidationError, match="appended individually"):
        MemberRoleAssignmentEvent.objects.bulk_create([event])
