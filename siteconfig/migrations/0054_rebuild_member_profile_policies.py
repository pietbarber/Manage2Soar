from django.db import migrations, models

import siteconfig.models

DEFAULT_POLICIES = {
    "username": "disabled",
    "phone": "request",
    "address": "request",
    "nickname": "request",
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

    normalized = {}
    for field in DEFAULT_POLICIES:
        legacy = field in {"username", "phone", "address", "nickname"}
        allowed = (
            {"disabled", "direct", "request"} if legacy else {"disabled", "direct"}
        )
        value = policies.get(field)
        normalized[field] = (
            value
            if isinstance(value, str) and value in allowed
            else DEFAULT_POLICIES[field] if legacy else "disabled"
        )
    return normalized


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


def legacy_member_profile_field_policies(policies):
    if not isinstance(policies, dict):
        policies = {}
    return {
        "username": policies.get("username", "disabled"),
        "email": policies.get("email", "disabled"),
        "phone": policies.get("phone", "request"),
        "address": policies.get("address", "request"),
        "emergency_contacts": policies.get("emergency_contacts", "disabled"),
        "nickname": policies.get("nickname", "request"),
        "profile_photo": policies.get("profile_photo", "disabled"),
        "biography": policies.get("biography", "disabled"),
        "password": policies.get("password", "disabled"),
        "contact_visibility": policies.get("contact_visibility", "disabled"),
    }


def restore_legacy_member_profile_field_policies(apps, schema_editor):
    """Restore the ten-key policy shape expected by migration 0053."""
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")
    for config in SiteConfiguration.objects.all().only(
        "pk", "member_profile_field_policies"
    ):
        legacy_policies = legacy_member_profile_field_policies(
            config.member_profile_field_policies
        )
        SiteConfiguration.objects.filter(pk=config.pk).update(
            member_profile_field_policies=legacy_policies
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
        migrations.RunPython(
            normalize_profile_policies, restore_legacy_member_profile_field_policies
        ),
    ]
