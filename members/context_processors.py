"""Authorization decisions used only for template visibility."""

from members.authorization import (
    has_role_admin_access,
    has_webmaster_compatibility_access,
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
            "membership_applications": bool(
                has_perm("members.view_membership_applications")
                or getattr(user, "director", False)
                or getattr(user, "member_manager", False)
                or has_webmaster_compatibility_access(user)
            ),
            "duty_delinquents": bool(
                has_perm("duty_roster.view_duty_delinquents")
                or getattr(user, "rostermeister", False)
                or getattr(user, "member_manager", False)
                or getattr(user, "director", False)
                or getattr(user, "is_superuser", False)
            ),
            "billing": bool(
                has_perm("billing.can_manage_billing")
                or getattr(user, "treasurer", False)
                or getattr(user, "is_superuser", False)
            ),
            "commercial_ticket": bool(
                getattr(user, "duty_officer", False)
                or getattr(user, "treasurer", False)
            ),
            "instructor": bool(getattr(user, "instructor", False)),
            "safety_reports": bool(
                has_perm("members.access_safety_reports")
                or getattr(user, "safety_officer", False)
                or getattr(user, "is_superuser", False)
            ),
            "rostermeister": bool(
                has_perm("duty_roster.edit_dutyroster_message")
                or getattr(user, "rostermeister", False)
            ),
            "roster_admin": bool(
                has_perm("duty_roster.edit_dutyroster_message")
                or getattr(user, "rostermeister", False)
                or getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
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
                getattr(user, "duty_officer", False) or getattr(user, "is_staff", False)
            ),
        }
    }
