from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Ledger",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("member", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="billing_ledger", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("flight_charge", "Flight charge"), ("misc_charge", "Miscellaneous charge"), ("manual_charge", "Manual charge"), ("payment", "Payment"), ("credit", "Credit"), ("opening_balance", "Opening balance"), ("reversal", "Reversal")], max_length=32)),
                ("effect", models.CharField(choices=[("debit", "Debit"), ("credit", "Credit")], max_length=6)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("effective_date", models.DateField()),
                ("member_description", models.CharField(max_length=255)),
                ("internal_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source_key", models.CharField(blank=True, max_length=160, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_billing_entries", to=settings.AUTH_USER_MODEL)),
                ("ledger", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="entries", to="billing.ledger")),
                ("reverses", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal", to="billing.ledgerentry")),
            ],
            options={
                "ordering": ("effective_date", "created_at", "id"),
                "indexes": [
                    models.Index(fields=["ledger", "effective_date", "created_at", "id"], name="billing_entry_statement_idx"),
                    models.Index(fields=["kind"], name="billing_entry_kind_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="billing_entry_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.UniqueConstraint(condition=models.Q(("source_key__isnull", False)), fields=("source_key",), name="billing_entry_source_key_unique"),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(kind__in=("flight_charge", "misc_charge", "manual_charge"), effect="debit")
                    | models.Q(kind__in=("payment", "credit"), effect="credit")
                    | models.Q(kind="opening_balance")
                    | models.Q(kind="reversal")
                ),
                name="billing_entry_kind_effect_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.CheckConstraint(
                condition=~models.Q(kind="reversal") | models.Q(reverses__isnull=False),
                name="billing_reversal_has_original",
            ),
        ),
    ]
