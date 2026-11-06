from django.db import migrations

GROUPS = ("Directors", "Secretary")
PERMISSIONS = (
    ("view_page", "Can view CMS pages"),
    ("change_page", "Can change CMS pages"),
)


def grant_cms_officer_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="cms", model="page"
    )
    permissions = [
        Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )[0]
        for codename, name in PERMISSIONS
    ]
    for group_name in GROUPS:
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        group.permissions.db_manager(db_alias).add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0047_director_membership_application_view"),
        ("cms", "0021_externalpdfcache"),
    ]

    operations = [migrations.RunPython(grant_cms_officer_permissions)]
