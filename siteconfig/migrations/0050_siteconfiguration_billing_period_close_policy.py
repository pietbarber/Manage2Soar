from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):
    dependencies = [("siteconfig", "0048_siteconfiguration_billing_app_enabled")]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="billing_period_close_policy",
            field=models.CharField(
                choices=[
                    ("manual", "Manual Close"),
                    ("nth_weekday", "Nth Weekday"),
                    ("days_before_month_end", "Days Before Month End"),
                ],
                default="manual",
                help_text="Choose manual close, an Nth weekday, or a number of days before month-end. Automatic closes occur at 11:59 PM club time.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="billing_period_close_month_offset",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Use 0 for the billing month or 1 for the following month when calculating an automatic close.",
                validators=[
                    MinValueValidator(0),
                    MaxValueValidator(1),
                ],
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="billing_period_close_week_number",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Week occurrence (1 through 5) for the Nth-weekday close policy.",
                validators=[MinValueValidator(1), MaxValueValidator(5)],
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="billing_period_close_weekday",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "Monday"),
                    (1, "Tuesday"),
                    (2, "Wednesday"),
                    (3, "Thursday"),
                    (4, "Friday"),
                    (5, "Saturday"),
                    (6, "Sunday"),
                ],
                default=0,
                help_text="Weekday for the Nth-weekday close policy.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="billing_period_close_days_before_month_end",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Days before the selected month ends for that automatic close policy.",
                validators=[MinValueValidator(0), MaxValueValidator(27)],
            ),
        ),
    ]
