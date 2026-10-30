from django.db import migrations


def grant_roster_message_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type, _ = ContentType.objects.get_or_create(
        app_label="duty_roster", model="dutyrostermessage"
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename="edit_dutyroster_message",
        defaults={"name": "Can edit the duty roster message"},
    )
    group = Group.objects.filter(name="Rostermeisters").first()
    if permission and group:
        group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0041_rolemetadata_admin_access"),
        ("duty_roster", "0017_dutyroster_message_permission"),
    ]

    operations = [
        migrations.RunPython(
            grant_roster_message_permission,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
