"""Reconcile the current canonical role capability registry."""

from django.db import migrations

# Keep the migration replayable if the runtime registry changes later.  The
# registry is the source for new runtime behavior; this is the frozen grant
# set that this migration reconciles.
MIGRATED_CAPABILITY_GRANTS = {
    "treasurer": (
        "billing.can_manage_billing",
        "logsheet.can_manage_logsheet_finances",
        "logsheet.can_export_logsheet_finances",
        "members.view_privileged_contact",
        "duty_roster.view_all_swap_requests",
    ),
    "safety_officers": ("members.access_safety_reports",),
    "directors": (
        "members.view_membership_applications",
        "cms.view_page",
        "cms.change_page",
        "duty_roster.view_duty_delinquents",
    ),
    "rostermeisters": (
        "duty_roster.edit_dutyroster_message",
        "duty_roster.view_duty_delinquents",
        "duty_roster.view_all_swap_requests",
        "members.view_privileged_contact",
    ),
    "member_managers": (
        "members.view_privileged_contact",
        "duty_roster.view_duty_delinquents",
        "duty_roster.view_all_swap_requests",
    ),
    "webmasters": (
        "members.view_privileged_contact",
        "duty_roster.view_all_swap_requests",
    ),
    "secretary": (
        "cms.view_page",
        "cms.change_page",
        "duty_roster.view_all_swap_requests",
    ),
    "instructor_admins": ("duty_roster.view_all_swap_requests",),
}


def sync_registered_capabilities(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Permission = apps.get_model("auth", "Permission")
    RoleMetadata = apps.get_model("members", "RoleMetadata")

    for role_key, capabilities in MIGRATED_CAPABILITY_GRANTS.items():
        metadata = (
            RoleMetadata.objects.using(db_alias)
            .select_related("group")
            .filter(key=role_key)
            .first()
        )
        if metadata is None:
            raise RuntimeError(
                f"Canonical role metadata is missing for capability registry key {role_key!r}."
            )

        permissions = []
        for capability in capabilities:
            app_label, codename = capability.split(".", 1)
            permission = (
                Permission.objects.using(db_alias)
                .filter(
                    content_type__app_label=app_label,
                    codename=codename,
                )
                .first()
            )
            if permission is None:
                raise RuntimeError(
                    f"Canonical capability {capability!r} has no database permission."
                )
            permissions.append(permission)
        metadata.group.permissions.db_manager(db_alias).add(*permissions)


class Migration(migrations.Migration):
    dependencies = [("members", "0051_repair_treasurer_finance_permissions")]

    operations = [
        migrations.RunPython(sync_registered_capabilities, migrations.RunPython.noop)
    ]
