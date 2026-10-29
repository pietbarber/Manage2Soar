import pytest
from django.contrib.auth.models import Group

from members.models import Member, MemberRoleAssignment
from members.services.role_assignments import set_manual_role


@pytest.fixture
def member():
    # Member.save defers its legacy-role sync until commit. These tests create
    # sources explicitly (or call _sync_groups) rather than relying on a
    # callback which pytest-django's enclosing test transaction won't run.
    return Member.objects.create_user(username="role-service-member")


@pytest.fixture
def group():
    return Group.objects.create(name="Service-managed group")


@pytest.mark.django_db
def test_multiple_manual_sources_keep_group_until_last_source_is_revoked(member, group):
    set_manual_role(member, group, enabled=True, source_key="admin")
    set_manual_role(member, group, enabled=True, source_key="committee")

    set_manual_role(member, group, enabled=False, source_key="admin")
    assert member.groups.filter(pk=group.pk).exists()
    assert list(
        MemberRoleAssignment.objects.filter(member=member, group=group).values_list(
            "source", "source_key"
        )
    ) == [("manual", "committee")]

    set_manual_role(member, group, enabled=False, source_key="committee")
    assert not member.groups.filter(pk=group.pk).exists()
    assert not MemberRoleAssignment.objects.filter(member=member, group=group).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "source,source_key", [("legacy", "instructor"), ("status", "active")]
)
def test_revocation_preserves_other_provenance(member, group, source, source_key):
    other = MemberRoleAssignment.objects.create(
        member=member, group=group, source=source, source_key=source_key
    )
    set_manual_role(member, group, enabled=True)
    member.groups.remove(group)

    set_manual_role(member, group, enabled=False)

    assert MemberRoleAssignment.objects.filter(pk=other.pk).exists()
    assert member.groups.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_repeated_grant_is_idempotent_and_keeps_original_actor(member, group):
    first_actor = Member.objects.create_user(username="first-role-actor")
    second_actor = Member.objects.create_user(username="second-role-actor")

    set_manual_role(member, group, enabled=True, actor=first_actor)
    assignment = MemberRoleAssignment.objects.get(member=member, group=group)
    original = (assignment.pk, assignment.created_at, assignment.updated_at)
    set_manual_role(member, group, enabled=True, actor=second_actor)

    assignment.refresh_from_db()
    assert (assignment.pk, assignment.created_at, assignment.updated_at) == original
    assert assignment.actor_id == first_actor.pk
    assert MemberRoleAssignment.objects.filter(member=member, group=group).count() == 1
    assert member.groups.filter(pk=group.pk).count() == 1


@pytest.mark.django_db
def test_repeated_revocation_does_not_remove_unexplained_direct_membership(
    member, group
):
    member.groups.add(group)
    for _ in range(2):
        set_manual_role(member, group, enabled=False)
        assert member.groups.filter(pk=group.pk).exists()
    assert not MemberRoleAssignment.objects.filter(member=member, group=group).exists()


@pytest.mark.django_db
def test_wrong_source_revocation_does_not_remove_group_or_assignment(member, group):
    set_manual_role(member, group, enabled=True, source_key="committee")
    set_manual_role(member, group, enabled=False, source_key="admin")

    assert member.groups.filter(pk=group.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=member, group=group, source="manual", source_key="committee"
    ).exists()


@pytest.mark.django_db
def test_revoking_a_real_source_leaves_unrelated_groups_untouched(member, group):
    unrelated = Group.objects.create(name="Unrelated direct membership")
    member.groups.add(unrelated)
    set_manual_role(member, group, enabled=True)

    set_manual_role(member, group, enabled=False)

    assert not member.groups.filter(pk=group.pk).exists()
    assert member.groups.filter(pk=unrelated.pk).exists()


@pytest.mark.django_db
def test_legacy_flag_sync_survives_manual_revocation(member):
    member.instructor = True
    member.save()
    member._sync_groups()
    group = Group.objects.get(name="Instructor Admins")

    set_manual_role(member, group, enabled=True, source_key="committee")
    set_manual_role(member, group, enabled=False, source_key="committee")

    assert member.groups.filter(pk=group.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=member, group=group, source="legacy", source_key="instructor"
    ).exists()
