from django.db import migrations

PERMISSIONS = (
    ("billing", "billingperiod", "can_manage_billing", "Can manage member billing"),
    (
        "logsheet",
        "logsheet",
        "can_manage_logsheet_finances",
        "Can manage logsheet finances",
    ),
    (
        "logsheet",
        "logsheet",
        "can_export_logsheet_finances",
        "Can export logsheet finances",
    ),
)


def grant_treasurer_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    group, _ = Group.objects.using(db_alias).get_or_create(name="Treasurer")
    for app_label, model, codename, name in PERMISSIONS:
        content_type, _ = ContentType.objects.using(db_alias).get_or_create(
            app_label=app_label, model=model
        )
        permission, _ = Permission.objects.using(db_alias).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        group.permissions.db_manager(db_alias).add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0043_privileged_contact_permission"),
        ("billing", "0011_billing_manage_permission"),
        ("logsheet", "0039_logsheet_finance_permissions"),
    ]

    operations = [
        migrations.RunPython(
            grant_treasurer_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
