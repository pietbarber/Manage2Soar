from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0057_siteconfiguration_member_name_ordering"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="allow_inactive_crew_selection",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow inactive members to be selected as pilots, instructors, and "
                    "tow pilots on logsheets. Inactive members remain available as passengers."
                ),
            ),
        ),
    ]
