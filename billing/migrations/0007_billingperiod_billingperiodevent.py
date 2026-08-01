from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_ledgerentry_correction_group"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingPeriod",
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
                ("year", models.PositiveIntegerField()),
                ("month", models.PositiveSmallIntegerField()),
                ("is_closed", models.BooleanField(default=False)),
            ],
            options={"ordering": ("-year", "-month")},
        ),
        migrations.CreateModel(
            name="BillingPeriodEvent",
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
                (
                    "action",
                    models.CharField(
                        choices=[("closed", "Closed"), ("reopened", "Reopened")],
                        max_length=10,
                    ),
                ),
                ("reason", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="billing_period_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="billing.billingperiod",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="billingperiod",
            constraint=models.UniqueConstraint(
                fields=("year", "month"), name="billing_period_unique_month"
            ),
        ),
        migrations.AddConstraint(
            model_name="billingperiod",
            constraint=models.CheckConstraint(
                condition=models.Q(("month__gte", 1), ("month__lte", 12)),
                name="billing_period_month_valid",
            ),
        ),
    ]
