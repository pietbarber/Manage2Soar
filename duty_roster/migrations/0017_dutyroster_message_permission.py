from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("duty_roster", "0016_create_am_pm_roles"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="dutyrostermessage",
            options={
                "permissions": [
                    (
                        "edit_dutyroster_message",
                        "Can edit the duty roster message",
                    ),
                ],
                "verbose_name": "Duty Roster Message",
                "verbose_name_plural": "Duty Roster Message",
            },
        ),
    ]
