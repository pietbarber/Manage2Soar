from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0008_guest_payment_pending")]

    operations = [
        migrations.AlterField(
            model_name="ledgerentry",
            name="kind",
            field=models.CharField(
                choices=[
                    ("flight_charge", "Flight charge"),
                    ("misc_charge", "Miscellaneous charge"),
                    ("manual_charge", "Manual charge"),
                    ("payment", "Payment"),
                    ("credit", "Credit"),
                    ("opening_balance", "Opening balance"),
                    ("guest_payment_pending", "Guest payment pending"),
                    ("guest_remittance", "Guest payment remittance"),
                    ("reversal", "Reversal"),
                ],
                max_length=32,
            ),
        ),
    ]
