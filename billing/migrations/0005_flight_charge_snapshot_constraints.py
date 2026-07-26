from django.db import migrations, models
from django.db.models import F


class Migration(migrations.Migration):
    dependencies = [("billing", "0004_snapshot_immutability")]

    operations = [
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(kind="flight_charge")
                | models.Q(flight__isnull=False),
                name="billing_flight_charge_has_flight",
            ),
        ),
        migrations.AddConstraint(
            model_name="flightchargesnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    tow_amount=F("total_amount")
                    - F("rental_amount")
                    - F("instruction_amount")
                ),
                name="billing_snapshot_components_equal_total",
            ),
        ),
    ]
