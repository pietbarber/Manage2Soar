from importlib import import_module
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from members.models import Member, MemberRoleAssignment
from members.services.role_assignments import set_manual_role


@pytest.fixture
def stats_permission(db):
    permission = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="logsheet", model="logsheet"),
        codename="can_export_stats_dump",
    )
    group, _ = Group.objects.get_or_create(name="Stats Mongers")
    group.permissions.add(permission)
    return permission


@pytest.fixture
def stats_member(db):
    return Member.objects.create_user(username="stats-monger-provenance")


def sync_stats_flag(member, enabled):
    member.stats_monger = enabled
    member.save()
    member._sync_groups()


@pytest.mark.django_db
def test_stats_monger_flag_grants_source_aware_permission(
    stats_member, stats_permission
):
    sync_stats_flag(stats_member, True)

    group = Group.objects.get(name="Stats Mongers")
    assignment = MemberRoleAssignment.objects.get(
        member=stats_member, group=group, source="legacy", source_key="stats_monger"
    )
    assert group.permissions.filter(pk=stats_permission.pk).exists()
    assert stats_member.groups.filter(pk=group.pk).exists()
    assert assignment.group_id == group.pk


@pytest.mark.django_db
def test_clearing_stats_monger_revokes_only_its_legacy_grant(
    stats_member, stats_permission
):
    sync_stats_flag(stats_member, True)
    sync_stats_flag(stats_member, False)

    group = Group.objects.get(name="Stats Mongers")
    assert not MemberRoleAssignment.objects.filter(
        member=stats_member, group=group, source="legacy", source_key="stats_monger"
    ).exists()
    assert not stats_member.groups.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_clearing_stats_monger_preserves_independent_direct_grant(
    stats_member, stats_permission
):
    stats_member.user_permissions.add(stats_permission)
    sync_stats_flag(stats_member, True)
    sync_stats_flag(stats_member, False)

    assert stats_member.user_permissions.filter(pk=stats_permission.pk).exists()


@pytest.mark.django_db
def test_clearing_stats_monger_preserves_independent_group_grant(
    stats_member, stats_permission
):
    group = Group.objects.get_or_create(name="Stats Mongers")[0]
    group.permissions.add(stats_permission)
    set_manual_role(stats_member, group, enabled=True, source_key="committee")

    sync_stats_flag(stats_member, True)
    sync_stats_flag(stats_member, False)

    assert stats_member.groups.filter(pk=group.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=stats_member, group=group, source="manual", source_key="committee"
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_stats_monger_migration_reconciles_cleared_legacy_grant_and_keeps_role_grant(
    stats_permission,
):
    """0053 removes stale direct access without deleting owned role access."""
    apps = (
        MigrationExecutor(connection)
        .loader.project_state([("members", "0053_source_aware_stats_monger_grants")])
        .apps
    )
    OldGroup = apps.get_model("auth", "Group")
    OldMember = apps.get_model("members", "Member")
    OldAssignment = apps.get_model("members", "MemberRoleAssignment")
    old_permission = apps.get_model("auth", "Permission").objects.get(
        pk=stats_permission.pk
    )

    member = OldMember.objects.create(
        username="cleared-before-stats-provenance", stats_monger=False
    )
    independent_group = OldGroup.objects.create(name="Independent Stats Role")
    independent_group.permissions.add(old_permission)
    member.groups.add(independent_group)
    OldAssignment.objects.create(
        member_id=member.pk,
        group_id=independent_group.pk,
        source="manual",
        source_key="committee",
    )
    # This is indistinguishable from 0045's direct row and must be revoked by
    # the migration's explicit ownership policy.
    member.user_permissions.add(old_permission)

    migration = import_module(
        "members.migrations.0054_reconcile_stats_monger_direct_grants"
    )
    migration.reconcile_cleared_stats_monger_grants(
        apps, SimpleNamespace(connection=connection)
    )

    member = Member.objects.get(pk=member.pk)
    assert not member.user_permissions.filter(pk=stats_permission.pk).exists()
    assert member.groups.filter(pk=independent_group.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=member,
        group_id=independent_group.pk,
        source="manual",
        source_key="committee",
    ).exists()
