"""
Backfill canonical group permissions after later app migrations.

Why this exists
---------------
members.0021 seeds canonical group permissions but depends only on initial
migrations for several apps. Models introduced in later migrations (for example
cms.Page / cms.SiteFeedback and knowledgetest.TestPreset family) can miss their
group assignments if they are not present when 0021 runs.

This migration reapplies the canonical mapping so all expected permissions are
present on each group in existing and fresh databases.
"""

from importlib import import_module

from django.db import migrations


def _get_group_permissions_mapping():
    """Load canonical mapping from members.0021 to avoid divergence."""
    mod = import_module("members.migrations.0021_setup_all_group_permissions")
    return mod.GROUP_PERMISSIONS


def backfill_group_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group_permissions = _get_group_permissions_mapping()

    for group_name, perm_tuples in group_permissions.items():
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        perms_to_add = []

        for app_label, model_name, codename in perm_tuples:
            try:
                ct, _ = ContentType.objects.using(db_alias).get_or_create(
                    app_label=app_label,
                    model=model_name,
                )

                if "_" in codename:
                    action, model_part = codename.split("_", 1)
                    perm_name = f"Can {action} {model_part.replace('_', ' ')}"
                else:
                    perm_name = codename

                perm, _ = Permission.objects.using(db_alias).get_or_create(
                    content_type=ct,
                    codename=codename,
                    defaults={"name": perm_name},
                )
                perms_to_add.append(perm)
            except Exception:
                # Keep migration resilient across historical/partial states.
                continue

        if perms_to_add:
            group.permissions.db_manager(db_alias).add(*perms_to_add)


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0024_align_stats_monger_column_name"),
        ("cms", "0020_document_updated_at"),
        ("siteconfig", "0050_siteconfiguration_billing_period_close_policy"),
        ("logsheet", "0028_flightsplitrequest_locked_status"),
        ("duty_roster", "0016_create_am_pm_roles"),
        ("instructors", "0004_add_sort_key_to_traininglesson"),
        ("knowledgetest", "0005_grant_instructor_admin_knowledgetest_permissions"),
    ]

    operations = [
        migrations.RunPython(
            backfill_group_permissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
