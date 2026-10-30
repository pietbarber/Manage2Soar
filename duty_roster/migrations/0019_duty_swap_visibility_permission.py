from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("duty_roster", "0018_duty_delinquents_permission")]

    operations = [
        migrations.AlterModelOptions(
            name="dutyswaprequest",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("view_all_swap_requests", "Can view all duty swap requests")
                ],
            },
        )
    ]
