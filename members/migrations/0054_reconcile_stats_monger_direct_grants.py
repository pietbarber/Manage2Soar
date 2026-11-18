"""Preserve ambiguous direct stats-export grants for explicit reconciliation.

This historical migration name is retained for migration-graph compatibility.
The legacy flag alone is not evidence of ownership of a direct grant. Removing
it here could irreversibly revoke administrator-approved exceptions. Use the
read-only stats-export report and a tenant-approved plan before any cleanup.
"""

from django.db import migrations


def reconcile_cleared_stats_monger_grants(apps, schema_editor):
    """No-op: historical callers may import this function; never infer ownership."""


class Migration(migrations.Migration):
    dependencies = [("members", "0053_source_aware_stats_monger_grants")]

    operations = [
        migrations.RunPython(
            reconcile_cleared_stats_monger_grants,
            migrations.RunPython.noop,
        )
    ]
