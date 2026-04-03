from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0038_alter_siteconfiguration_max_reservations_per_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="duty_default_max_assignments_per_month",
            field=models.PositiveIntegerField(
                default=8,
                help_text=(
                    "Default monthly assignment limit for members without a DutyPreference row. "
                    "Set to 0 to disable assignments for members who have not saved preferences."
                ),
            ),
        ),
    ]
