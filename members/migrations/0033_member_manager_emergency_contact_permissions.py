from django.db import migrations

PERMISSIONS = (
    "add_emergencycontact",
    "change_emergencycontact",
    "delete_emergencycontact",
    "view_emergencycontact",
)


def add_member_manager_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    try:
        apps.get_model("members", "EmergencyContact")
    except LookupError:
        return
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="members", model="emergencycontact"
    )
    permissions = []
    for codename in PERMISSIONS:
        action, model_name = codename.split("_", 1)
        permission, _ = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": f"Can {action} {model_name.replace('_', ' ')}"},
        )
        permissions.append(permission)
    group = Group.objects.using(db_alias).filter(name="Member Managers").first()
    if group:
        group.permissions.db_manager(db_alias).add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("members", "0032_member_pending_email")]

    operations = [
        migrations.RunPython(
            add_member_manager_permissions,
            reverse_code=migrations.RunPython.noop,
        )
    ]
