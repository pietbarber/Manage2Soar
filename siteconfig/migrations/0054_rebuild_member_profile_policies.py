from django.db import migrations, models

import siteconfig.models


DEFAULT_POLICIES = {
    "email": "disabled",
    "emergency_contacts": "direct",
    "profile_photo": "direct",
    "biography": "direct",
    "password": "direct",
    "contact_visibility": "direct",
}


def normalize_member_profile_field_policies(policies):
    if not isinstance(policies, dict):
        return DEFAULT_POLICIES.copy()

    return {
        field: policies.get(field)
        if policies.get(field) in {"disabled", "direct"}
        else default
        for field, default in DEFAULT_POLICIES.items()
    }


def normalize_profile_policies(apps, schema_editor):
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")
    for config in SiteConfiguration.objects.all().only(
        "pk", "member_profile_field_policies"
    ):
        policies = normalize_member_profile_field_policies(
            config.member_profile_field_policies
        )
        if policies != config.member_profile_field_policies:
            SiteConfiguration.objects.filter(pk=config.pk).update(
                member_profile_field_policies=policies
            )


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0053_siteconfiguration_profile_policies"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="member_profile_field_policies",
            field=models.JSONField(
                db_default=DEFAULT_POLICIES,
                default=siteconfig.models.default_member_profile_field_policies,
                help_text="Per-field member profile policies.",
                validators=[siteconfig.models.validate_member_profile_field_policies],
            ),
        ),
        migrations.RunPython(normalize_profile_policies, migrations.RunPython.noop),
    ]
