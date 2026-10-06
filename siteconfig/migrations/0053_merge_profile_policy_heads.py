from django.db import migrations


def convert_request_policies(apps, schema_editor):
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")
    for config in SiteConfiguration.objects.all().iterator():
        policies = config.member_profile_field_policies or {}
        normalized = {
            field: ("direct" if policy == "request" else policy)
            for field, policy in policies.items()
        }
        if normalized != policies:
            config.member_profile_field_policies = normalized
            config.save(update_fields=["member_profile_field_policies"])


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0052_siteconfiguration_member_profile_field_policies_and_more"),
    ]

    operations = [migrations.RunPython(convert_request_policies, migrations.RunPython.noop)]
