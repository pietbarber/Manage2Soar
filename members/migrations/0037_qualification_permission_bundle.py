from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("members", "0036_member_role_assignments")]

    operations = [
        migrations.AddField(
            model_name="rolemetadata",
            name="qualification_permission_bundle",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow this Group to be selected as a permission bundle for a "
                    "current member qualification."
                ),
            ),
        ),
    ]
