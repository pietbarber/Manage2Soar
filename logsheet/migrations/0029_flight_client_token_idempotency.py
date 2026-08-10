from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logsheet", "0028_flightsplitrequest_locked_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="flight",
            name="client_token",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddConstraint(
            model_name="flight",
            constraint=models.UniqueConstraint(
                condition=models.Q(client_token__isnull=False)
                & ~models.Q(client_token=""),
                fields=("logsheet", "client_token"),
                name="flight_unique_client_token_per_logsheet",
            ),
        ),
    ]
