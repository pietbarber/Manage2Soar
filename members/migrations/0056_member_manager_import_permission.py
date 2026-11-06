from django.db import migrations


def grant_safe_member_import_permission(apps, schema_editor):
    """Allow Member Managers to import profiles without granting roles."""
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type = ContentType.objects.using(db_alias).get(
        app_label="members", model="member"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="import_member",
        defaults={"name": "Can import member profiles"},
    )
    group = Group.objects.using(db_alias).filter(name="Member Managers").first()
    if group:
        group.permissions.db_manager(db_alias).add(permission)


class Migration(migrations.Migration):
    dependencies = [("members", "0055_alter_member_options")]

    operations = [
        migrations.RunPython(
            grant_safe_member_import_permission,
            reverse_code=migrations.RunPython.noop,
        )
    ]
