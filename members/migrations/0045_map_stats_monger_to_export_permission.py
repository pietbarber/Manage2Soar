from django.db import migrations


def map_legacy_stats_monger(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Member = apps.get_model("members", "Member")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.using(db_alias).get_or_create(
        app_label="logsheet", model="logsheet"
    )
    permission, _ = Permission.objects.using(db_alias).get_or_create(
        content_type=content_type,
        codename="can_export_stats_dump",
        defaults={"name": "Can export raw flight statistics"},
    )
    for member in Member.objects.using(db_alias).filter(stats_monger=True).iterator():
        member.user_permissions.db_manager(db_alias).add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0044_grant_treasurer_finance_permissions"),
        ("logsheet", "0040_stats_dump_export_permission"),
    ]
    operations = [
        migrations.RunPython(map_legacy_stats_monger, migrations.RunPython.noop)
    ]
