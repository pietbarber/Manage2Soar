from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("logsheet", "0027_flightsplitrequest_requester_differs")]

    operations = [
        migrations.AlterField(
            model_name="flightsplitrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                    ("stale", "Stale"),
                    ("locked", "Locked by accounting period"),
                ],
                default="pending",
                max_length=10,
            ),
        ),
    ]
