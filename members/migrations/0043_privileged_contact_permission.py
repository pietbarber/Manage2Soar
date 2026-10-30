"""Register the narrow capability used for privileged contact visibility."""

from django.db import migrations


PERMISSION_CODENAME = "view_privileged_contact"
PRIVILEGED_GROUPS = (
    "Webmasters",
    "Treasurer",
    "Member Managers",
    "Rostermeisters",
)


def grant_privileged_contact_permission(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    Member = apps.get_model("members", "Member")

    content_type = ContentType.objects.using(db_alias).get(
        app_label="members", model=Member._meta.model_name
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename=PERMISSION_CODENAME,
        defaults={"name": "Can view privileged member contact details"},
    )
    for group_name in PRIVILEGED_GROUPS:
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        group.permissions.db_manager(db_alias).add(permission)


def revoke_privileged_contact_permission(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    Member = apps.get_model("members", "Member")

    content_type = ContentType.objects.using(db_alias).get(
        app_label="members", model=Member._meta.model_name
    )
    permission = Permission.objects.using(db_alias).filter(
        content_type=content_type, codename=PERMISSION_CODENAME
    ).first()
    if permission is None:
        return
    for group in Group.objects.using(db_alias).filter(name__in=PRIVILEGED_GROUPS):
        group.permissions.remove(permission)
    permission.delete(using=db_alias)


class Migration(migrations.Migration):
    dependencies = [("members", "0042_grant_roster_message_permission")]

    operations = [
        migrations.RunPython(
            grant_privileged_contact_permission,
            reverse_code=revoke_privileged_contact_permission,
        )
    ]
