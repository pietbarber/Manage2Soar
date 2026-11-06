"""Exercise the final capability reconciliation on an existing database state."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from members.role_definitions import CANONICAL_ROLES


@pytest.mark.django_db(transaction=True)
def test_capability_sync_restores_missing_grant_without_changing_existing_roles():
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()
    before = ("members", "0051_repair_treasurer_finance_permissions")
    after = ("members", "0052_sync_registered_role_capabilities")

    try:
        executor.migrate([before])
        old_apps = executor.loader.project_state([before]).apps
        Group = old_apps.get_model("auth", "Group")
        Permission = old_apps.get_model("auth", "Permission")
        RoleMetadata = old_apps.get_model("members", "RoleMetadata")
        Member = old_apps.get_model("members", "Member")

        # transaction=True flushes migration-seeded rows between tests. Restore
        # only the canonical prerequisites when this test runs after another
        # transaction test; on a fresh install they are already present.
        for role in CANONICAL_ROLES:
            group, _ = Group.objects.get_or_create(name=role.group_name)
            RoleMetadata.objects.get_or_create(
                group=group,
                defaults={"key": role.key, "display_name": role.display_name},
            )

        directors = RoleMetadata.objects.select_related("group").get(key="directors")
        cms_edit = Permission.objects.get(
            content_type__app_label="cms",
            content_type__model="page",
            codename="change_page",
        )
        # Model a tenant missing one registered grant while retaining custom
        # permissions and manual memberships from before the final migration.
        directors.group.permissions.remove(cms_edit)
        custom_group = Group.objects.create(name="Tenant Custom Role")
        custom_permission = Permission.objects.get(
            content_type__app_label="members",
            content_type__model="member",
            codename="view_member",
        )
        custom_group.permissions.add(custom_permission)
        member = Member.objects.create(username="existing-role-member")
        member.groups.add(custom_group)
        original_metadata = (directors.pk, directors.group_id, directors.display_name)

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        assert (
            Group.objects.get(pk=directors.group_id)
            .permissions.filter(pk=cms_edit.pk)
            .exists()
        )
        assert RoleMetadata.objects.filter(
            pk=original_metadata[0],
            group_id=original_metadata[1],
            display_name=original_metadata[2],
        ).exists()
        assert (
            Group.objects.get(pk=custom_group.pk)
            .permissions.filter(pk=custom_permission.pk)
            .exists()
        )
        assert (
            Member.objects.get(pk=member.pk).groups.filter(pk=custom_group.pk).exists()
        )
    finally:
        MigrationExecutor(connection).migrate(leaf_targets)
