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


def repair_treasurer_finance_permissions(apps, schema_editor):
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
    dependencies = [("members", "0050_grant_duty_swap_visibility_permission")]

    operations = [migrations.RunPython(repair_treasurer_finance_permissions)]
