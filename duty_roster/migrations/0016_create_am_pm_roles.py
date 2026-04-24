"""Create AM/PM tow and instructor DutyRoleDefinition rows.

This data migration is idempotent and will attach roles to the first
SiteConfiguration row (the demo site). It can be safely run multiple
times in staging/production.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    DutyRoleDefinition = apps.get_model("duty_roster", "DutyRoleDefinition")
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")

    site = SiteConfiguration.objects.first()
    if not site:
        return

    roles = [
        {
            "key": "am_tow",
            "display_name": "AM Tow",
            "legacy_role_key": "towpilot",
            "shift_code": "am",
            "is_active": True,
            "sort_order": 10,
        },
        {
            "key": "pm_tow",
            "display_name": "PM Tow",
            "legacy_role_key": "towpilot",
            "shift_code": "pm",
            "is_active": True,
            "sort_order": 20,
        },
        {
            "key": "am_instructor",
            "display_name": "AM Instructor",
            "legacy_role_key": "instructor",
            "shift_code": "am",
            "is_active": True,
            "sort_order": 30,
        },
        {
            "key": "pm_instructor",
            "display_name": "PM Instructor",
            "legacy_role_key": "instructor",
            "shift_code": "pm",
            "is_active": True,
            "sort_order": 40,
        },
    ]

    for r in roles:
        DutyRoleDefinition.objects.update_or_create(
            site_configuration=site,
            key=r["key"],
            defaults={
                "display_name": r["display_name"],
                "legacy_role_key": r["legacy_role_key"],
                "shift_code": r["shift_code"],
                "is_active": r["is_active"],
                "sort_order": r["sort_order"],
            },
        )


def backwards(apps, schema_editor):
    DutyRoleDefinition = apps.get_model("duty_roster", "DutyRoleDefinition")
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")

    site = SiteConfiguration.objects.first()
    if not site:
        return

    keys = ["am_tow", "pm_tow", "am_instructor", "pm_instructor"]
    DutyRoleDefinition.objects.filter(site_configuration=site, key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("duty_roster", "0015_dutyswaprequest_swap_request_dynamic_role_metadata_consistency"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
