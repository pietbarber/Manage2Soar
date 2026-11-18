import threading

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection

from members.models import Member, MemberRoleAssignment, RoleMetadata
from members.services.status_role_reconciliation import (
    apply,
    plan,
    status_source_key,
)
from siteconfig.models import MembershipStatus, MembershipStatusRoleMapping


@pytest.fixture
def status():
    return MembershipStatus.objects.create(name="Reconciliation Member")


@pytest.fixture
def member(status):
    return Member.objects.create_user(
        username="status-reconciliation-member",
        membership_status=status.name,
    )


@pytest.fixture
def role():
    group = Group.objects.create(name="Reconciliation Role")
    RoleMetadata.objects.create(
        group=group,
        key="reconciliation_role",
        display_name="Reconciliation Role",
    )
    return group


@pytest.mark.django_db
def test_status_key_is_immutable_and_mapping_is_explicit(status, role):
    original_key = status.key
    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )

    status.name = "Renamed Reconciliation Member"
    status.save()
    status.refresh_from_db()

    assert status.key == original_key
    assert mapping.membership_status_id == status.pk
    assert status_source_key(status.key, "reconciliation_role") == (
        f"{original_key}:reconciliation_role"
    )

    status.key = "different-key"
    with pytest.raises(ValidationError, match="cannot be changed"):
        status.save()


@pytest.mark.django_db
def test_no_mapping_grants_no_role(member):
    result = apply(member)

    assert result.applied is True
    assert result.grants == 0
    assert result.revokes == 0
    assert not MemberRoleAssignment.objects.filter(
        member=member, source="status"
    ).exists()


@pytest.mark.django_db
def test_status_grant_is_idempotent_and_mapping_revoke_preserves_manual(
    member, status, role
):
    MembershipStatusRoleMapping.objects.create(membership_status=status, role=role)

    first = apply(member)
    second = apply(member)
    assert (first.grants, first.revokes) == (1, 0)
    assert (second.grants, second.revokes) == (0, 0)
    assert member.groups.filter(pk=role.pk).exists()

    MemberRoleAssignment.objects.create(
        member=member, group=role, source="manual", source_key="committee"
    )
    mapping = MembershipStatusRoleMapping.objects.get(
        membership_status=status, role=role
    )
    mapping.enabled = False
    mapping.save(update_fields=["enabled"])

    revoked = apply(member)
    assert revoked.revokes == 1
    assert member.groups.filter(pk=role.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=member, group=role, source="manual", source_key="committee"
    ).exists()


@pytest.mark.django_db
def test_inactive_status_removes_only_status_provenance(member, status, role):
    MembershipStatusRoleMapping.objects.create(membership_status=status, role=role)
    apply(member)
    status.is_active = False
    status.save(update_fields=["is_active"])

    result = apply(member)

    assert result.revokes == 1
    assert not MemberRoleAssignment.objects.filter(
        member=member, group=role, source="status"
    ).exists()


@pytest.mark.django_db
def test_unexplained_membership_is_reported_and_preserved(member, role):
    member.groups.add(role)

    current_plan = plan(member)
    result = apply(member)

    assert role.pk in current_plan.unexplained_group_ids
    assert result.revokes == 0
    assert member.groups.filter(pk=role.pk).exists()


@pytest.mark.django_db
def test_invalid_mapping_is_a_noop(member, status):
    group = Group.objects.create(name="Untracked reconciliation role")
    MembershipStatusRoleMapping.objects.bulk_create(
        [MembershipStatusRoleMapping(membership_status=status, role=group)]
    )

    result = apply(member)

    assert result.applied is False
    assert any(
        issue.code == "mapping_missing_role_metadata" for issue in result.plan.issues
    )
    assert not MemberRoleAssignment.objects.filter(
        member=member, source="status"
    ).exists()


@pytest.mark.django_db
def test_command_defaults_to_dry_run_and_apply_is_explicit(
    member, status, role, capsys, tmp_path
):
    MembershipStatusRoleMapping.objects.create(membership_status=status, role=role)

    checkpoint = tmp_path / "status-role-checkpoint.json"
    call_command(
        "reconcile_status_roles",
        "--json",
        "--checkpoint-file",
        str(checkpoint),
    )
    dry_run_report = capsys.readouterr().out
    assert '"mode": "dry-run"' in dry_run_report
    assert '"complete": true' in checkpoint.read_text()
    assert not MemberRoleAssignment.objects.filter(
        member=member, source="status"
    ).exists()

    call_command("reconcile_status_roles", "--apply", "--status-key", status.key)
    assert MemberRoleAssignment.objects.filter(
        member=member, source="status", source_key=f"{status.key}:reconciliation_role"
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_mapping_and_activity_changes_reconcile_after_commit(member, status, role):
    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    assert MemberRoleAssignment.objects.filter(member=member, source="status").exists()

    mapping.enabled = False
    mapping.save()
    assert not MemberRoleAssignment.objects.filter(
        member=member, source="status"
    ).exists()

    mapping.enabled = True
    mapping.save()
    assert MemberRoleAssignment.objects.filter(member=member, source="status").exists()
    status.is_active = False
    status.save()
    assert not MemberRoleAssignment.objects.filter(
        member=member, source="status"
    ).exists()


@pytest.mark.django_db
def test_mapping_audit_records_actor_and_immutable_snapshot(status, role):
    from siteconfig.audit import actor_scope
    from siteconfig.models import MembershipStatusRoleMappingEvent

    actor = Member.objects.create_user(username="mapping-audit-actor")
    with actor_scope(actor):
        mapping = MembershipStatusRoleMapping.objects.create(
            membership_status=status, role=role
        )
        mapping.enabled = False
        mapping.save()

    events = list(
        MembershipStatusRoleMappingEvent.objects.values_list(
            "action", "status_key", "role_key", "enabled", "actor_username"
        )
    )
    assert events == [
        ("created", status.key, "reconciliation_role", True, "mapping-audit-actor"),
        ("updated", status.key, "reconciliation_role", False, "mapping-audit-actor"),
    ]

    event = MembershipStatusRoleMappingEvent.objects.first()
    with pytest.raises(ValidationError, match="immutable"):
        event.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        MembershipStatusRoleMappingEvent.objects.all().delete()


@pytest.mark.django_db
def test_mapping_delete_records_snapshot_audit(status, role):
    from siteconfig.models import MembershipStatusRoleMappingEvent

    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    mapping_id = mapping.pk
    mapping.delete()

    event = MembershipStatusRoleMappingEvent.objects.get(action="deleted")
    assert event.mapping_id is None
    assert event.mapping_id_snapshot == mapping_id
    assert event.status_key == status.key
    assert event.role_key == "reconciliation_role"


@pytest.mark.django_db
def test_admin_mapping_preview_reports_member_impact(member, status, role):
    from django.contrib import admin

    from siteconfig.admin import MembershipStatusRoleMappingAdmin

    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    preview = MembershipStatusRoleMappingAdmin(
        MembershipStatusRoleMapping, admin.site
    ).reconciliation_preview(mapping)

    assert "Members: 1" in str(preview)
    assert "Planned status grants: 1" in str(preview)


@pytest.mark.django_db(transaction=True)
def test_concurrent_reconciliation_does_not_duplicate_status_assignment(
    member, status, role
):
    MembershipStatusRoleMapping.objects.create(membership_status=status, role=role)
    MemberRoleAssignment.objects.filter(member=member, source="status").delete()
    member.groups.remove(role)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            results.append(apply(Member.objects.get(pk=member.pk)).grants)
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert sorted(results) == [0, 1]
    assert (
        MemberRoleAssignment.objects.filter(
            member=member,
            group=role,
            source="status",
            source_key=f"{status.key}:reconciliation_role",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_status_mapping_migration_preserves_existing_group_membership():
    """The status identity migration must not rewrite unrelated role state."""
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old_target = [node for node in latest if node[0] != "siteconfig"] + [
        ("siteconfig", "0057_siteconfiguration_show_today_roster_group")
    ]
    try:
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        OldStatus = old_apps.get_model("siteconfig", "MembershipStatus")
        OldMember = old_apps.get_model("members", "Member")
        OldGroup = old_apps.get_model("auth", "Group")

        old_status = OldStatus.objects.create(name="Migration Preservation Status")
        old_group = OldGroup.objects.create(name="Migration Preservation Group")
        old_member = OldMember.objects.create(
            username="migration-preservation-member",
            membership_status=old_status.name,
        )
        old_member.groups.add(old_group)
        group_id = old_group.pk
        member_id = old_member.pk

        new_target = [node for node in latest if node[0] != "siteconfig"] + [
            ("siteconfig", "0059_membershipstatusrolemappingevent")
        ]
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new_apps = executor.loader.project_state(new_target).apps
        NewStatus = new_apps.get_model("siteconfig", "MembershipStatus")
        NewMember = new_apps.get_model("members", "Member")
        NewMapping = new_apps.get_model("siteconfig", "MembershipStatusRoleMapping")

        migrated_status = NewStatus.objects.get(name=old_status.name)
        assert migrated_status.key == "migration-preservation-status"
        assert list(
            NewMember.objects.get(pk=member_id).groups.values_list("pk", flat=True)
        ) == [group_id]
        assert not NewMapping.objects.filter(membership_status=migrated_status).exists()
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
