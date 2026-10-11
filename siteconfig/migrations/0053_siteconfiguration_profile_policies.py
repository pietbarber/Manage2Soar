from django.db import migrations, models

import siteconfig.models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0052_siteconfiguration_contact_visibility_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="member_profile_self_service_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Allow members to update or request changes to configured profile fields.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="member_profile_field_policies",
            field=models.JSONField(
                default=siteconfig.models.default_member_profile_field_policies,
                help_text="Per-field member profile policies.",
                validators=[siteconfig.models.validate_member_profile_field_policies],
            ),
        ),
    ]
