from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_flight_charge_snapshot_constraints")]

    operations = [
        migrations.AddField(
            model_name="ledgerentry",
            name="correction_group",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
