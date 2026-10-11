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
                db_default=True,
                default=True,
                help_text="Allow members to update or request changes to configured profile fields.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="member_profile_field_policies",
            field=models.JSONField(
                db_default={
                    "username": "direct",
                    "email": "request",
                    "phone": "request",
                    "address": "request",
                    "emergency_contacts": "direct",
                    "nickname": "request",
                    "profile_photo": "direct",
                    "biography": "direct",
                    "password": "direct",
                    "contact_visibility": "direct",
                },
                default=siteconfig.models.default_member_profile_field_policies,
                help_text="Per-field member profile policies.",
                validators=[siteconfig.models.validate_member_profile_field_policies],
            ),
        ),
    ]
