from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("duty_roster", "0009_add_opsintent_date_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dutypreference",
            name="max_assignments_per_month",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("2.00"),
                help_text="Monthly assignment rate (0.5 means about once every two months over a range)",
                max_digits=4,
                validators=[
                    MinValueValidator(Decimal("0.00")),
                    MaxValueValidator(Decimal("12.00")),
                ],
            ),
        ),
    ]
