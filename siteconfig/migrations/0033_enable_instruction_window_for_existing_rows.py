"""
Data migration (Issue #648): enable restrict_instruction_requests_window for
any pre-existing SiteConfiguration row.

Before this feature, ops_intent_toggle hard-coded a 14-day instruction
request window unconditionally.  Clubs that were already using the site
get that same behaviour automatically after the upgrade; new clubs that
install fresh will have the toggle off by default (opt-in).
"""

from django.db import migrations


def enable_instruction_window_for_existing(apps, schema_editor):
    SiteConfiguration = apps.get_model("siteconfig", "SiteConfiguration")
    SiteConfiguration.objects.update(
        restrict_instruction_requests_window=True,
        instruction_request_max_days_ahead=14,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0032_update_instructors_email_help_text"),
    ]

    operations = [
        migrations.RunPython(
            enable_instruction_window_for_existing,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
