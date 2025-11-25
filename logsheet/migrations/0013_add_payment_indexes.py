# Generated manually for Issue #285 - Performance optimization for logsheet finances
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('logsheet', '0012_remove_towrate_model'),
    ]

    operations = [
        # NOTE: This index may be redundant due to unique_together constraint on LogsheetPayment model,
        # but is kept for explicit performance optimization and compatibility across database backends.
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS logsheet_payment_logsheet_member_idx ON logsheet_logsheetpayment (logsheet_id, member_id);",
            reverse_sql="DROP INDEX IF EXISTS logsheet_payment_logsheet_member_idx;"
        ),
    ]
