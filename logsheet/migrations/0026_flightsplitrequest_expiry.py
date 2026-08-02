from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("logsheet", "0025_flightsplitrequest")]

    operations = [
        migrations.AddField(
            model_name="flightsplitrequest",
            name="expires_at",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="flightsplitrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"), ("accepted", "Accepted"),
                    ("rejected", "Rejected"), ("cancelled", "Cancelled"),
                    ("expired", "Expired"), ("stale", "Stale"),
                ],
                default="pending",
                max_length=10,
            ),
        ),
    ]
