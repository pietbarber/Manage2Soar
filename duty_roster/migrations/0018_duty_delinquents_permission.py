from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("duty_roster", "0017_dutyroster_message_permission")]

    operations = [
        migrations.AlterModelOptions(
            name="dutyassignment",
            options={
                "ordering": ["date"],
                "permissions": [("view_duty_delinquents", "Can view duty delinquents")],
            },
        )
    ]
