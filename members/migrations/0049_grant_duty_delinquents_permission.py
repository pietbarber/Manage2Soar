from django.db import migrations

GROUPS = ("Rostermeisters", "Member Managers", "Directors")


def grant_duty_delinquents_permission(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="duty_roster", model="dutyassignment"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="view_duty_delinquents",
        defaults={"name": "Can view duty delinquents"},
    )
    for group_name in GROUPS:
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        group.permissions.db_manager(db_alias).add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0048_grant_cms_officer_permissions"),
        ("duty_roster", "0018_duty_delinquents_permission"),
    ]

    operations = [migrations.RunPython(grant_duty_delinquents_permission)]
