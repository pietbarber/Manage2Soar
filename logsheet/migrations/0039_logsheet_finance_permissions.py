from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("logsheet", "0038_towplanecloseout_start_tach_manually_cleared_and_more")]

    operations = [
        migrations.AlterModelOptions(
            name="logsheet",
            options={
                "permissions": (
                    ("can_manage_logsheet_finances", "Can manage logsheet finances"),
                    ("can_export_logsheet_finances", "Can export logsheet finances"),
                ),
            },
        ),
    ]
