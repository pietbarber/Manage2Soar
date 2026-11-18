"""Authorization decisions used only for template visibility."""

from billing.permissions import has_billing_access
from duty_roster.permissions import (
    EDIT_ROSTER_MESSAGE_PERMISSION,
    has_duty_delinquents_access,
    has_roster_edit_access,
    has_roster_generation_access,
)
from logsheet.permissions import (
    has_logsheet_finance_access,
    has_stats_dump_export_access,
)
from members.authorization import (
    can_manage_ground_instruction,
    has_bulk_qualification_access,
    has_membership_application_view_access,
    has_qualification_assignment_access,
    has_role_admin_access,
    has_syllabus_edit_access,
    has_training_record_access,
    has_training_record_action,
    has_webmaster_compatibility_access,
)
from members.utils.membership import is_active_member


def _can_edit_roster_message(user):
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or getattr(user, "rostermeister", False)
        or user.has_perm(EDIT_ROSTER_MESSAGE_PERMISSION)
        or user.has_perm("duty_roster.edit_dutyroster_message")
    )


def authorization(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"role_access": {}}

    has_perm = user.has_perm
    return {
        "role_access": {
            # Keep compatibility fallbacks here until the corresponding view
            # policies are fully migrated. Templates never enforce access.
            "membership_applications": has_membership_application_view_access(user),
            "duty_delinquents": has_duty_delinquents_access(user),
            "billing": has_billing_access(user),
            # Keep this in sync with the view's active-member decorator and
            # stats capability gate, including the canonical superuser path.
            "stats_dump_export": bool(
                is_active_member(user) and has_stats_dump_export_access(user)
            ),
            "commercial_ticket": bool(
                getattr(user, "duty_officer", False)
                or has_logsheet_finance_access(user)
            ),
            "instructor": has_training_record_access(user),
            "training_view": has_training_record_access(user),
            "training_write": has_training_record_action(user),
            "qualification_assignment": has_qualification_assignment_access(user),
            "bulk_qualification": has_bulk_qualification_access(user),
            "syllabus_edit": has_syllabus_edit_access(user),
            "ground_instruction": can_manage_ground_instruction(user),
            "safety_reports": bool(
                has_perm("members.access_safety_reports")
                or getattr(user, "safety_officer", False)
                or getattr(user, "is_superuser", False)
            ),
            "rostermeister": has_roster_edit_access(user),
            "roster_generate": has_roster_generation_access(user),
            "roster_admin": bool(
                has_perm("duty_roster.edit_dutyroster_message")
                or has_perm("duty_roster.can_generate_roster")
                or has_perm("duty_roster.can_edit_roster")
                or getattr(user, "rostermeister", False)
                or getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
            ),
            "roster_message": _can_edit_roster_message(user),
            "recent_written_tests": bool(
                getattr(user, "is_staff", False)
                or user.has_perm("knowledgetest.view_recent_written_tests")
                or has_webmaster_compatibility_access(user)
            ),
            "written_test_delete": bool(
                getattr(user, "is_staff", False)
                or user.has_perm("knowledgetest.delete_any_written_test_attempt")
                or has_webmaster_compatibility_access(user)
            ),
            "member_admin": bool(
                has_perm("members.change_member")
                or getattr(user, "member_manager", False)
                or getattr(user, "is_superuser", False)
            ),
            # Preserve the existing technical staff gate for the directory's
            # admin action until its Django admin permission is migrated.
            "can_edit_member_list": bool(getattr(user, "is_staff", False)),
            "admin": bool(
                getattr(user, "is_staff", False) or has_role_admin_access(user)
            ),
            "visiting_pilot": bool(
                getattr(user, "duty_officer", False)
                or getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
            ),
        }
    }
