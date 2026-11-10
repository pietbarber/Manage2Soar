"""Exercise the final capability reconciliation on an existing database state."""

from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from members.role_definitions import CANONICAL_ROLES, CAPABILITY_GRANTS

CAPABILITY_MIGRATION = "members.migrations.0052_sync_registered_role_capabilities"


def _ensure_permission(Permission, ContentType, app_label, model, codename):
    content_type, _ = ContentType.objects.get_or_create(
        app_label=app_label, model=model
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=codename,
        defaults={"name": codename.replace("_", " ").capitalize()},
    )
    return permission


def test_migration_snapshot_is_a_subset_of_the_current_registry():
    """The frozen 0052 grants remain present after later capability slices."""
    snapshot = import_module(CAPABILITY_MIGRATION).MIGRATED_CAPABILITY_GRANTS
    assert set(snapshot) == set(CAPABILITY_GRANTS)
    for role, capabilities in snapshot.items():
        assert set(capabilities) <= set(CAPABILITY_GRANTS[role])


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
        ContentType = old_apps.get_model("contenttypes", "ContentType")
        migration = import_module(CAPABILITY_MIGRATION)
        for capabilities in migration.MIGRATED_CAPABILITY_GRANTS.values():
            for capability in capabilities:
                app_label, codename = capability.split(".", 1)
                model = migration.CAPABILITY_CONTENT_TYPES[capability][1]
                _ensure_permission(Permission, ContentType, app_label, model, codename)
        cms_edit = _ensure_permission(
            Permission, ContentType, "cms", "page", "change_page"
        )
        stale_permission = _ensure_permission(
            Permission, ContentType, "auth", "group", "change_group"
        )
        custom_permission = _ensure_permission(
            Permission, ContentType, "members", "member", "view_member"
        )
        for role in CANONICAL_ROLES:
            group, _ = Group.objects.get_or_create(name=role.group_name)
            RoleMetadata.objects.get_or_create(
                group=group,
                defaults={"key": role.key, "display_name": role.display_name},
            )

        directors = RoleMetadata.objects.select_related("group").get(key="directors")
        # Model a tenant missing one registered grant while retaining custom
        # permissions and manual memberships from before the final migration.
        directors.group.permissions.remove(cms_edit)
        # A formerly registered capability may still exist in production.
        # A future registry removal must not silently revoke that tenant grant.
        directors.group.permissions.add(stale_permission)
        custom_group = Group.objects.create(name="Tenant Custom Role")
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
        assert (
            Group.objects.get(pk=directors.group_id)
            .permissions.filter(pk=stale_permission.pk)
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
