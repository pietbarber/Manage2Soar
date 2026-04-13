from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("duty_roster", "0010_fractional_max_assignments"),
    ]

    operations = [
        migrations.AddField(
            model_name="dutyassignment",
            name="commercial_pilot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="as_commercial_pilot",
                to="members.member",
            ),
        ),
        migrations.AddField(
            model_name="dutypreference",
            name="commercial_pilot_percent",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
