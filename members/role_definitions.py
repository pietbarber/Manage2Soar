"""Canonical built-in role metadata and migrated capability grants.

Historical migrations remain the replayable record of how existing databases
were changed. This module is the current registry for runtime code and future
role/capability changes; it must stay keyed by stable role keys rather than
editable Group display names.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    group_name: str
    display_name: str
    sort_order: int
    legacy_flag: str | None = None


CANONICAL_ROLES = (
    RoleDefinition(
        "instructor_admins", "Instructor Admins", "Instructor Admins", 10, "instructor"
    ),
    RoleDefinition("webmasters", "Webmasters", "Webmasters", 20, "webmaster"),
    RoleDefinition(
        "member_managers", "Member Managers", "Member Managers", 30, "member_manager"
    ),
    RoleDefinition(
        "rostermeisters", "Rostermeisters", "Rostermeisters", 40, "rostermeister"
    ),
    RoleDefinition("secretary", "Secretary", "Secretary", 50, "secretary"),
    RoleDefinition("treasurer", "Treasurer", "Treasurer", 60, "treasurer"),
    RoleDefinition("directors", "Directors", "Directors", 25, "director"),
    RoleDefinition(
        "safety_officers", "Safety Officers", "Safety Officers", 30, "safety_officer"
    ),
)

ROLE_BY_KEY = {role.key: role for role in CANONICAL_ROLES}
ROLE_BY_GROUP_NAME = {role.group_name: role for role in CANONICAL_ROLES}

# These are the legacy flag/group relationships that Member._sync_groups has
# historically maintained. Other built-in roles may be backfilled by their
# dedicated migration and are intentionally not added to that synchronization
# set here without a separate parity review.
LEGACY_SYNC_ROLES = tuple(
    role
    for role in CANONICAL_ROLES
    if role.key
    in {
        "instructor_admins",
        "webmasters",
        "member_managers",
        "rostermeisters",
        "secretary",
        "treasurer",
        "directors",
        "safety_officers",
    }
)

# Capability grants migrated after the original Group permission seed. Keep
# this allowlist explicit so new migrations can extend one registry and parity
# tests can verify that the database still reflects it.
CAPABILITY_GRANTS = {
    "treasurer": (
        "billing.can_manage_billing",
        "logsheet.can_manage_logsheet_finances",
        "logsheet.can_export_logsheet_finances",
        "logsheet.can_unfinalize_logsheet",
        "members.view_privileged_contact",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
    ),
    "safety_officers": (
        "members.access_safety_reports",
        "members.view_safetyreport",
        "members.change_safetyreport",
        "members.can_review_safety_report",
        "members.can_view_safety_dashboard",
        "instructors.can_bulk_assign_qualification",
    ),
    "directors": (
        "members.view_membership_applications",
        "cms.view_page",
        "cms.change_page",
        "duty_roster.view_duty_delinquents",
    ),
    "rostermeisters": (
        "duty_roster.edit_dutyroster_message",
        "duty_roster.can_edit_roster_message",
        "duty_roster.can_generate_roster",
        "duty_roster.can_edit_roster",
        "duty_roster.view_duty_delinquents",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
        "members.view_privileged_contact",
        "logsheet.can_unfinalize_logsheet",
        "logsheet.can_resolve_maintenance_issue",
        "logsheet.can_update_maintenance_deadline",
    ),
    "member_managers": (
        "members.view_privileged_contact",
        "members.view_membership_applications",
        "members.can_manage_membership_applications",
        "members.can_review_membership_application",
        "members.can_approve_membership_application",
        "members.can_manage_membership_waitlist",
        "duty_roster.view_duty_delinquents",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
    ),
    "webmasters": (
        "members.view_privileged_contact",
        "members.view_membership_applications",
        "members.can_manage_membership_applications",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
        "logsheet.can_unfinalize_logsheet",
        "logsheet.can_resolve_maintenance_issue",
        "logsheet.can_update_maintenance_deadline",
        "members.can_manage_member_roles",
    ),
    "secretary": (
        "cms.view_page",
        "cms.change_page",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
    ),
    "instructor_admins": (
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
        "instructors.view_trainingrecord",
        "instructors.can_record_instruction",
        "instructors.can_assign_qualification",
        "instructors.can_bulk_assign_qualification",
        "instructors.can_export_training_record",
        "instructors.can_manage_ground_instruction",
        "knowledgetest.start_unassigned_written_test",
        "knowledgetest.delete_any_written_test_attempt",
        "knowledgetest.view_recent_written_tests",
        "knowledgetest.delete_any_pending_written_test_assignment",
    ),
}


def legacy_sync_group_names():
    """Return the legacy groups whose membership sync remains flag-driven."""
    return {
        role.group_name: role.legacy_flag
        for role in LEGACY_SYNC_ROLES
        if role.legacy_flag
    }
