from django.db import migrations, models

import siteconfig.models


PROFILE_POLICY_DEFAULTS = {
    "username": "disabled",
    "email": "disabled",
    "emergency_contacts": "direct",
    "profile_photo": "direct",
    "biography": "direct",
    "password": "direct",
    "contact_visibility": "direct",
}


def normalize_profile_policies(apps, schema_editor):
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")
    fields = tuple(PROFILE_POLICY_DEFAULTS)
    for config in SiteConfiguration.objects.all().iterator():
        value = config.member_profile_field_policies
        existing = value if isinstance(value, dict) else {}
        normalized = {}
        for field in fields:
            policy = existing.get(field, PROFILE_POLICY_DEFAULTS[field])
            if policy == "request":
                policy = "disabled" if field in {"username", "email"} else "direct"
            if not isinstance(policy, str) or policy not in {"disabled", "direct"}:
                policy = PROFILE_POLICY_DEFAULTS[field]
            normalized[field] = policy
        if normalized != existing:
            config.member_profile_field_policies = normalized
            config.save(update_fields=["member_profile_field_policies"])


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0053_siteconfiguration_profile_policies"),
    ]

    operations = [
        migrations.RunPython(normalize_profile_policies, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="member_profile_self_service_enabled",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text="Allow members to edit configured profile fields directly.",
            ),
        ),
        migrations.AlterField(
            model_name="siteconfiguration",
            name="member_profile_field_policies",
            field=models.JSONField(
                db_default=PROFILE_POLICY_DEFAULTS,
                default=siteconfig.models.default_member_profile_field_policies,
                help_text="Per-field member profile policies.",
                validators=[siteconfig.models.validate_member_profile_field_policies],
            ),
        ),
    ]
