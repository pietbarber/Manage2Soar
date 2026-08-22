from django.db import migrations, models


def require_unique_opening_balances(apps, schema_editor):
    LedgerEntry = apps.get_model("billing", "LedgerEntry")
    duplicate_ledger_ids = list(
        LedgerEntry.objects.filter(kind="opening_balance")
        .values("ledger_id")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
        .values_list("ledger_id", flat=True)
    )
    if duplicate_ledger_ids:
        raise RuntimeError(
            "Cannot add the one-opening-balance constraint. Resolve duplicate opening "
            f"balances for ledger IDs: {', '.join(map(str, duplicate_ledger_ids))}."
        )


class Migration(migrations.Migration):

    dependencies = [("billing", "0006_ledgerentry_correction_group")]

    operations = [
        migrations.RunPython(require_unique_opening_balances, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="ledgerentry",
            constraint=models.UniqueConstraint(
                fields=("ledger",),
                condition=models.Q(kind="opening_balance"),
                name="billing_one_opening_balance_per_ledger",
            ),
        ),
    ]
