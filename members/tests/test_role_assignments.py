import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_role_assignment_migration_preserves_memberships_and_classifies_them():
    executor = MigrationExecutor(connection)
    original_leaf_targets = executor.loader.graph.leaf_nodes()
    before = ("members", "0035_member_tags")
    after = ("members", "0036_member_role_assignments")

    executor.migrate([before])
    old_apps = executor.loader.project_state([before]).apps
    OldGroup = old_apps.get_model("auth", "Group")
    OldMember = old_apps.get_model("members", "Member")
    OldPermission = old_apps.get_model("auth", "Permission")

    mapped, _ = OldGroup.objects.get_or_create(name="Instructor Admins")
    safety_group = OldGroup.objects.create(name="User-created Safety Coordinators")
    equipment_group = OldGroup.objects.create(
        name="User-created Equipment Coordinators"
    )
    member = OldMember.objects.create(username="migration-provenance", instructor=True)
    second_member = OldMember.objects.create(username="second-manual-member")
    member.groups.add(mapped, safety_group)
    second_member.groups.add(safety_group, equipment_group)
    permissions = list(OldPermission.objects.order_by("pk")[:2])
    assert len(permissions) == 2
    safety_group.permissions.add(permissions[0])
    equipment_group.permissions.add(permissions[1])
    before_memberships = {
        user.pk: set(user.groups.values_list("pk", flat=True))
        for user in (member, second_member)
    }
    before_permissions = {
        group.name: set(group.permissions.values_list("pk", flat=True))
        for group in (mapped, safety_group, equipment_group)
    }

    try:
        # MigrationExecutor caches applied migrations; refresh it after moving
        # to the historical state before calculating the forward plan.
        executor = MigrationExecutor(connection)
        executor.migrate([after])
        new_apps = MigrationExecutor(connection).loader.project_state([after]).apps
        Assignment = new_apps.get_model("members", "MemberRoleAssignment")
        rows_by_member = {}
        for row in Assignment.objects.filter(
            member_id__in=(member.pk, second_member.pk)
        ).select_related("group", "member"):
            rows_by_member.setdefault(row.member.username, set()).add(
                (row.group.name, row.source, row.source_key)
            )

        assert rows_by_member == {
            "migration-provenance": {
                ("Instructor Admins", "legacy", "instructor"),
                ("User-created Safety Coordinators", "manual", "migration"),
            },
            "second-manual-member": {
                ("User-created Safety Coordinators", "manual", "migration"),
                ("User-created Equipment Coordinators", "manual", "migration"),
            },
        }
        assert {
            user.pk: set(user.groups.values_list("pk", flat=True))
            for user in OldMember.objects.filter(pk__in=before_memberships)
        } == before_memberships
        assert {
            group.name: set(group.permissions.values_list("pk", flat=True))
            for group in OldGroup.objects.filter(
                pk__in=(mapped.pk, safety_group.pk, equipment_group.pk)
            )
        } == before_permissions
    finally:
        MigrationExecutor(connection).migrate(original_leaf_targets)
