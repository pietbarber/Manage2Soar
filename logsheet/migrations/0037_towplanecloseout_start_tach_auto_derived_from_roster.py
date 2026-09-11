from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logsheet", "0036_non_negative_roster_start_tach"),
    ]

    operations = [
        migrations.AddField(
            model_name="towplanecloseout",
            name="start_tach_auto_derived_from_roster",
            field=models.BooleanField(default=False),
        ),
    ]
