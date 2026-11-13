"""Create written-test capabilities before granting them.

Migration 0006 declares these permissions through model options, but Django
normally materializes option-defined permissions from ``post_migrate``. That
signal runs after migrations, so migration 0007 can run before the permission
rows exist on a fresh database. Keep 0007 as historical record and repair
both fresh installs and upgrades with an explicit, idempotent migration.
"""

from django.db import migrations


WRITTEN_TEST_PERMISSIONS = [
    (
        "writtentesttemplate",
        "start_unassigned_written_test",
        "Can start and submit an unassigned written test",
    ),
    (
        "writtentestattempt",
        "delete_any_written_test_attempt",
        "Can delete any written test attempt",
    ),
    (
        "writtentestattempt",
        "view_recent_written_tests",
        "Can view recent written tests",
    ),
    (
        "writtentestassignment",
        "delete_any_pending_written_test_assignment",
        "Can delete any pending written test assignment",
    ),
]


def create_and_grant_capabilities(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    permissions = []
    for model_name, codename, name in WRITTEN_TEST_PERMISSIONS:
        content_type, _ = ContentType.objects.using(db_alias).get_or_create(
            app_label="knowledgetest",
            model=model_name,
        )
        permission, _ = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions.append(permission)

    # This migration can run before the members migrations that seed canonical
    # Groups. Creating the Group here is safe: later role metadata migrations
    # attach metadata to the same stable Group name.
    group, _ = Group.objects.using(db_alias).get_or_create(
        name="Instructor Admins"
    )
    group.permissions.db_manager(db_alias).add(*permissions)


def revoke_capability_grants(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group = Group.objects.using(db_alias).filter(name="Instructor Admins").first()
    if not group:
        return

    for model_name, codename, _ in WRITTEN_TEST_PERMISSIONS:
        content_type = ContentType.objects.using(db_alias).filter(
            app_label="knowledgetest", model=model_name
        ).first()
        if not content_type:
            continue
        permission = Permission.objects.using(db_alias).filter(
            content_type=content_type, codename=codename
        ).first()
        if permission:
            group.permissions.db_manager(db_alias).remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("knowledgetest", "0007_grant_written_test_capabilities"),
    ]

    operations = [
        migrations.RunPython(create_and_grant_capabilities, revoke_capability_grants),
    ]
