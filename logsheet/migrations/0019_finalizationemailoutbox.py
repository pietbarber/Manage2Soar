from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "logsheet",
            "0018_maintenancedeadline_maintenance_deadline_must_have_aircraft",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="FinalizationEmailOutbox",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("sent", "Sent"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                (
                    "processed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "logsheet",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="finalization_email_outbox",
                        to="logsheet.logsheet",
                    ),
                ),
            ],
            options={"ordering": ["queued_at"]},
        ),
    ]
