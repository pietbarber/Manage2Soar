from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0056_membershipstatus_flight_eligibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="show_today_roster_group",
            field=models.BooleanField(
                default=True,
                help_text="Show members scheduled for the logsheet date in a separate dropdown group.",
            ),
        ),
    ]
