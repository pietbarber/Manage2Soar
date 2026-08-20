from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_billingperiod_billingperiodevent"),
        ("billing", "0007_one_opening_balance_per_ledger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ledgerentry",
            name="guest_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("cash", "Cash"),
                    ("check", "Check"),
                    ("zelle", "Zelle"),
                ],
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="ledgerentry",
            name="remits",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="remittance",
                to="billing.ledgerentry",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="ledgerentry",
            name="billing_entry_kind_effect_valid",
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        kind__in=(
                            "flight_charge",
                            "misc_charge",
                            "manual_charge",
                            "guest_payment_pending",
                        ),
                        effect="debit",
                    )
                    | models.Q(
                        kind__in=("payment", "credit", "guest_remittance"),
                        effect="credit",
                    )
                    | models.Q(kind="opening_balance")
                    | models.Q(kind="reversal")
                ),
                name="billing_entry_kind_effect_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(kind="guest_remittance")
                | models.Q(remits__isnull=False),
                name="billing_guest_remittance_has_collection",
            ),
        ),
    ]
