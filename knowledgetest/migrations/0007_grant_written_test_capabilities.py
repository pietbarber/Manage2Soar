from django.db import migrations


PERMISSIONS = [
    ("writtentesttemplate", "start_unassigned_written_test"),
    ("writtentestattempt", "delete_any_written_test_attempt"),
    ("writtentestattempt", "view_recent_written_tests"),
    ("writtentestassignment", "delete_any_pending_written_test_assignment"),
]


def grant_capabilities(apps, schema_editor):
    db = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    try:
        group = Group.objects.using(db).get(name="Instructor Admins")
    except Group.DoesNotExist:
        return
    grants = []
    for model_name, codename in PERMISSIONS:
        try:
            content_type = ContentType.objects.using(db).get(
                app_label="knowledgetest", model=model_name
            )
            grants.append(
                Permission.objects.using(db).get(
                    content_type=content_type, codename=codename
                )
            )
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            continue
    group.permissions.db_manager(db).add(*grants)


def revoke_capabilities(apps, schema_editor):
    db = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    try:
        group = Group.objects.using(db).get(name="Instructor Admins")
    except Group.DoesNotExist:
        return
    for model_name, codename in PERMISSIONS:
        try:
            content_type = ContentType.objects.using(db).get(
                app_label="knowledgetest", model=model_name
            )
            permission = Permission.objects.using(db).get(
                content_type=content_type, codename=codename
            )
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            continue
        group.permissions.db_manager(db).remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("knowledgetest", "0006_written_test_capability_permissions"),
        # The canonical role is created by the members role bootstrap.  Keep
        # this grant after that bootstrap so fresh installs do not silently
        # skip the Instructor Admin assignment.
        ("members", "0042_grant_roster_message_permission"),
    ]
    operations = [migrations.RunPython(grant_capabilities, revoke_capabilities)]
