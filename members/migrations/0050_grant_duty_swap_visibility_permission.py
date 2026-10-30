from django.db import migrations

GROUPS = (
    "Instructor Admins",
    "Member Managers",
    "Rostermeisters",
    "Webmasters",
    "Secretary",
    "Treasurer",
)


def grant_duty_swap_visibility_permission(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="duty_roster", model="dutyswaprequest"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="view_all_swap_requests",
        defaults={"name": "Can view all duty swap requests"},
    )
    for group_name in GROUPS:
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        group.permissions.db_manager(db_alias).add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0049_grant_duty_delinquents_permission"),
        ("duty_roster", "0019_duty_swap_visibility_permission"),
    ]

    operations = [migrations.RunPython(grant_duty_swap_visibility_permission)]
