from django.db import migrations, models


def default_existing_member_payments(apps, schema_editor):
    LogsheetPayment = apps.get_model("logsheet", "LogsheetPayment")
    LogsheetPayment.objects.filter(payment_method__isnull=True).update(
        payment_method="account"
    )


def restore_nullable_member_payments(apps, schema_editor):
    # Do not erase explicit account selections or later payment updates.
    pass


class Migration(migrations.Migration):
    dependencies = [
        (
            "logsheet",
            "0030_rename_logsheet_fl_logshee_25df4a_idx_logsheet_fl_logshee_3a0b41_idx",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="logsheetpayment",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("account", "On Account"),
                    ("check", "Check"),
                    ("zelle", "Zelle"),
                    ("cash", "Cash"),
                ],
                default="account",
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(
            default_existing_member_payments,
            restore_nullable_member_payments,
        ),
    ]
