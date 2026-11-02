from importlib import import_module
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db
def test_role_assignment_backfill_preserves_memberships_and_classifies_them():
    # 0051 is intentionally irreversible, so reversing the entire migration
    # graph from the latest state to 0035 cannot test this backfill. Exercise
    # the frozen 0036 function using its historical app registry instead.
    apps = (
        MigrationExecutor(connection)
        .loader.project_state([("members", "0036_member_role_assignments")])
        .apps
    )
    OldGroup = apps.get_model("auth", "Group")
    OldMember = apps.get_model("members", "Member")
    OldPermission = apps.get_model("auth", "Permission")
    Assignment = apps.get_model("members", "MemberRoleAssignment")

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

    backfill = import_module("members.migrations.0036_member_role_assignments")
    backfill.backfill_role_assignments(apps, SimpleNamespace(connection=connection))
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
