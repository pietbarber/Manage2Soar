from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        (
            "logsheet",
            "0031_logsheetpayment_default_account",
        ),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LogsheetGuestPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("guest_name", models.CharField(max_length=150)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "payment_method",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("cash", "Cash"),
                            ("check", "Check"),
                            ("zelle", "Zelle"),
                        ],
                        max_length=10,
                        null=True,
                    ),
                ),
                ("note", models.CharField(blank=True, max_length=200)),
                (
                    "flight",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_payment",
                        to="logsheet.flight",
                    ),
                ),
                (
                    "logsheet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_payments",
                        to="logsheet.logsheet",
                    ),
                ),
                (
                    "responsible_member",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guest_flight_payment_responsibilities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
