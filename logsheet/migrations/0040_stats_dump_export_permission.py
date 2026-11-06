from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("logsheet", "0039_logsheet_finance_permissions")]

    operations = [
        migrations.AlterModelOptions(
            name="logsheet",
            options={
                "permissions": (
                    ("can_manage_logsheet_finances", "Can manage logsheet finances"),
                    ("can_export_logsheet_finances", "Can export logsheet finances"),
                    ("can_export_stats_dump", "Can export raw flight statistics"),
                ),
            },
        )
    ]
