"""Create and grant the approved endpoint authorization capabilities.

The capability names are deliberately created in one forward-only migration so
an existing tenant receives the same permission objects as a clean install.
The grants are additive; unrelated tenant permissions and memberships are not
changed.
"""

from django.db import migrations


CAPABILITIES = {
    "members": {
        "member": (
            "can_manage_member_roles",
            "can_manage_member_tags",
            "can_manage_kiosk_tokens",
            "can_view_member_contact",
            "can_edit_own_profile",
            "can_change_own_email",
            "can_change_own_password",
            "can_manage_own_contact_visibility",
            "can_manage_own_emergency_contacts",
        ),
        "membershipapplication": (
            "can_manage_membership_applications",
            "can_review_membership_application",
            "can_approve_membership_application",
            "can_manage_membership_waitlist",
        ),
        "safetyreport": (
            "view_safetyreport",
            "change_safetyreport",
            "can_review_safety_report",
            "can_view_safety_dashboard",
        ),
        "emergencycontact": (),
    },
    "instructors": {
        "instructionreport": (
            "view_trainingrecord",
            "can_export_training_record",
        ),
        "groundinstruction": (
            "can_record_instruction",
            "can_manage_ground_instruction",
        ),
        "memberqualification": (
            "can_assign_qualification",
            "can_bulk_assign_qualification",
        ),
    },
    "duty_roster": {
        "dutyassignment": (
            "view_calendar",
            "can_volunteer_for_duty",
            "can_rescind_own_duty",
            "can_generate_roster",
            "can_edit_roster",
            "can_edit_roster_message",
        ),
        "dutyswaprequest": (
            "can_manage_own_swap",
            "can_manage_any_swap",
        ),
        "gliderreservation": ("can_manage_own_reservation",),
    },
    "logsheet": {
        "logsheet": (
            "can_edit_open_logsheet",
            "can_sync_offline_flights",
            "can_finalize_logsheet",
            "can_unfinalize_logsheet",
            "can_edit_closeout",
            "can_manage_logsheet_finances",
            "can_export_logsheet_finances",
            "can_export_stats_dump",
            "can_export_personal_charges",
            "can_export_tow_logbook",
        ),
        "maintenanceissue": (
            "can_resolve_maintenance_issue",
            "can_update_maintenance_deadline",
        ),
    },
}


CAPABILITY_LABELS = {
    codename: codename.replace("_", " ").capitalize()
    for models in CAPABILITIES.values()
    for codenames in models.values()
    for codename in codenames
}


ROLE_GRANTS = {
    "Webmasters": (
        "members.can_manage_member_roles",
        "members.can_manage_member_tags",
        "members.can_manage_kiosk_tokens",
        "members.view_membership_applications",
        "members.can_manage_membership_applications",
        "duty_roster.can_manage_any_swap",
        "logsheet.can_unfinalize_logsheet",
        "logsheet.can_resolve_maintenance_issue",
        "logsheet.can_update_maintenance_deadline",
    ),
    "Member Managers": (
        "members.can_view_member_contact",
        "members.view_membership_applications",
        "members.can_manage_membership_applications",
        "members.can_review_membership_application",
        "members.can_approve_membership_application",
        "members.can_manage_membership_waitlist",
        "duty_roster.can_manage_any_swap",
    ),
    "Directors": (
        "members.can_view_member_contact",
    ),
    "Treasurer": (
        "logsheet.can_unfinalize_logsheet",
        "duty_roster.can_manage_any_swap",
    ),
    "Rostermeisters": (
        "duty_roster.can_generate_roster",
        "duty_roster.can_edit_roster",
        "duty_roster.can_edit_roster_message",
        "duty_roster.can_manage_any_swap",
        "logsheet.can_unfinalize_logsheet",
        "logsheet.can_resolve_maintenance_issue",
        "logsheet.can_update_maintenance_deadline",
    ),
    "Secretary": ("duty_roster.can_manage_any_swap",),
    "Instructor Admins": (
        "instructors.view_trainingrecord",
        "instructors.can_record_instruction",
        "instructors.can_assign_qualification",
        "instructors.can_bulk_assign_qualification",
        "instructors.can_export_training_record",
        "instructors.can_manage_ground_instruction",
        "duty_roster.can_manage_any_swap",
    ),
    "Safety Officers": (
        "members.view_safetyreport",
        "members.change_safetyreport",
        "members.can_review_safety_report",
        "members.can_view_safety_dashboard",
        "instructors.can_bulk_assign_qualification",
    ),
    "Stats Mongers": ("logsheet.can_export_stats_dump",),
}


def create_and_grant_capabilities(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    permissions = {}
    for app_label, models in CAPABILITIES.items():
        for model_name, codenames in models.items():
            content_type, _ = ContentType.objects.using(db_alias).get_or_create(
                app_label=app_label,
                model=model_name,
            )
            for codename in codenames:
                permission, _ = Permission.objects.using(db_alias).get_or_create(
                    content_type=content_type,
                    codename=codename,
                    defaults={"name": CAPABILITY_LABELS[codename]},
                )
                permissions[f"{app_label}.{codename}"] = permission

    # Several approved capabilities predate this migration.  Resolve those
    # existing permission rows as well so the additive grant pass remains
    # replayable across both clean and upgraded databases.
    for capability in {
        capability
        for capabilities in ROLE_GRANTS.values()
        for capability in capabilities
        if capability not in permissions
    }:
        app_label, codename = capability.split(".", 1)
        permission = (
            Permission.objects.using(db_alias)
            .filter(content_type__app_label=app_label, codename=codename)
            .first()
        )
        if permission is None:
            raise RuntimeError(f"Approved capability {capability!r} is missing.")
        permissions[capability] = permission

    for group_name, capabilities in ROLE_GRANTS.items():
        group = Group.objects.using(db_alias).filter(name=group_name).first()
        if group is None:
            continue
        group.permissions.db_manager(db_alias).add(
            *(permissions[capability] for capability in capabilities)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0056_member_manager_import_permission"),
        ("instructors", "0008_groundinstruction_manage_permission"),
        ("duty_roster", "0019_duty_swap_visibility_permission"),
        ("logsheet", "0040_stats_dump_export_permission"),
        ("cms", "0021_externalpdfcache"),
        ("billing", "0011_billing_manage_permission"),
        ("knowledgetest", "0008_create_and_grant_written_test_capabilities"),
    ]

    operations = [
        migrations.RunPython(
            create_and_grant_capabilities,
            reverse_code=migrations.RunPython.noop,
        )
    ]
