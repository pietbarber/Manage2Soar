"""Tests for the policy-neutral, read-only authorization boundary."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from instructors.models import (
    ClubQualificationType,
    GroundInstruction,
    MemberQualification,
    QualificationPermissionGrant,
)
from members.authorization import (
    AuthorizationDecision,
    can_manage_ground_instruction,
    has_admin_model_permission,
    has_membership_application_modify_access,
    has_membership_application_view_access,
    has_webmaster_compatibility_access,
    resolve_authorization,
)
from members.models import RoleMetadata
from siteconfig.models import MembershipStatus


@pytest.fixture
def member(db):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    return get_user_model().objects.create_user(
        username="authorization-member", membership_status="Full Member"
    )


def test_anonymous_never_gets_context_or_kiosk_access():
    assert resolve_authorization(
        AnonymousUser(),
        "auth.view_group",
        context_allow=True,
        require_active_member=True,
        kiosk_authenticated=True,
        allow_kiosk_membership_bypass=True,
    ) == AuthorizationDecision(False, "unauthenticated")


@pytest.mark.django_db
def test_inactive_account_denied_even_with_context_and_kiosk(member):
    member.is_active = False
    assert resolve_authorization(
        member,
        "auth.view_group",
        context_allow=True,
        kiosk_authenticated=True,
        require_active_member=True,
        allow_kiosk_membership_bypass=True,
    ) == AuthorizationDecision(False, "inactive_account")


@pytest.mark.django_db
@pytest.mark.parametrize("grant", ["is_superuser", "webmaster", "preview"])
def test_disabled_account_denied_by_webmaster_compatibility_helpers(member, grant):
    if grant == "preview":
        member._role_preview_group_name = "Webmasters"
    else:
        setattr(member, grant, True)
    member.is_active = False
    assert not has_webmaster_compatibility_access(member)
    assert not has_admin_model_permission(member, "members", "member", "change")


@pytest.mark.django_db
def test_membership_application_helpers_require_active_account_and_membership(member):
    member.member_manager = True
    assert has_membership_application_view_access(member)
    assert has_membership_application_modify_access(member)

    member.is_active = False
    assert not has_membership_application_view_access(member)
    assert not has_membership_application_modify_access(member)

    member.is_active = True
    member.membership_status = "Inactive Member"
    assert not has_membership_application_view_access(member)
    assert not has_membership_application_modify_access(member)


@pytest.mark.django_db
def test_superuser_uses_django_global_permission_and_membership_policy(member):
    member.is_superuser = True
    member.membership_status = "Not an active status"
    assert resolve_authorization(
        member, "auth.view_group", require_active_member=True
    ) == AuthorizationDecision(True, "global_permission")
    member.is_active = False
    assert not resolve_authorization(member, "auth.view_group").allow


@pytest.mark.django_db
def test_group_and_direct_user_permissions(member):
    group_permission = Permission.objects.get(
        content_type__app_label="auth", codename="view_group"
    )
    direct_permission = Permission.objects.get(
        content_type__app_label="auth", codename="add_group"
    )
    group = Group.objects.create(name="Authorization test group")
    group.permissions.add(group_permission)
    member.groups.add(group)
    member.user_permissions.add(direct_permission)

    assert resolve_authorization(member, "auth.view_group") == AuthorizationDecision(
        True, "global_permission"
    )
    assert resolve_authorization(member, "auth.add_group") == AuthorizationDecision(
        True, "global_permission"
    )
    assert resolve_authorization(member, "auth.delete_group") == AuthorizationDecision(
        False, "no_grant"
    )


@pytest.mark.django_db
def test_context_is_explicit_or_not_inferred_from_identity_or_flags(member):
    member.instructor = True  # Legacy flags are not grants.
    assert resolve_authorization(member, "auth.delete_group") == AuthorizationDecision(
        False, "no_grant"
    )
    assert resolve_authorization(
        member, "auth.delete_group", context_allow=True
    ) == AuthorizationDecision(True, "context_grant")
    assert resolve_authorization(
        member, "auth.delete_group", context_allow=False
    ) == AuthorizationDecision(False, "no_grant")


@pytest.mark.django_db
def test_ground_instruction_helper_keeps_legacy_instructor_grant(member):
    member.instructor = True
    assert can_manage_ground_instruction(member)


@pytest.mark.django_db
def test_ground_instruction_helper_allows_scoped_permission(member):
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(GroundInstruction),
        codename="can_manage_ground_instruction",
    )
    member.user_permissions.add(permission)
    member = get_user_model().objects.get(pk=member.pk)

    assert can_manage_ground_instruction(member)


@pytest.mark.django_db
def test_ground_instruction_helper_denies_ordinary_and_inactive_users(member):
    assert not can_manage_ground_instruction(member)

    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(GroundInstruction),
        codename="can_manage_ground_instruction",
    )
    member.user_permissions.add(permission)
    member = get_user_model().objects.get(pk=member.pk)
    member.is_active = False
    assert not can_manage_ground_instruction(member)


@pytest.mark.django_db
def test_ground_instruction_helper_preserves_active_superuser_compatibility(member):
    member.is_superuser = True
    member.membership_status = "Inactive Member"

    assert can_manage_ground_instruction(member)


@pytest.mark.django_db
def test_membership_gate_precedes_global_permission_for_non_superuser(member):
    permission = Permission.objects.get(
        content_type__app_label="auth", codename="view_group"
    )
    member.user_permissions.add(permission)
    member.membership_status = "Inactive Member"

    assert resolve_authorization(
        member, "auth.view_group", require_active_member=True
    ) == AuthorizationDecision(False, "inactive_membership")
    assert resolve_authorization(member, "auth.view_group") == AuthorizationDecision(
        True, "global_permission"
    )


@pytest.mark.django_db
def test_kiosk_needs_explicit_membership_bypass_and_still_needs_grant(member):
    member.membership_status = "Role Account"
    permission = "auth.view_group"
    assert resolve_authorization(
        member, permission, require_active_member=True, context_allow=True
    ) == AuthorizationDecision(False, "inactive_membership")
    assert resolve_authorization(
        member,
        permission,
        require_active_member=True,
        context_allow=True,
        kiosk_authenticated=True,
    ) == AuthorizationDecision(False, "inactive_membership")
    assert resolve_authorization(
        member,
        permission,
        require_active_member=True,
        context_allow=True,
        allow_kiosk_membership_bypass=True,
    ) == AuthorizationDecision(False, "inactive_membership")
    assert resolve_authorization(
        member,
        permission,
        require_active_member=True,
        kiosk_authenticated=True,
        allow_kiosk_membership_bypass=True,
    ) == AuthorizationDecision(False, "no_grant")
    assert resolve_authorization(
        member,
        permission,
        require_active_member=True,
        kiosk_authenticated=True,
        allow_kiosk_membership_bypass=True,
        context_allow=True,
    ) == AuthorizationDecision(True, "context_grant")


@pytest.mark.django_db
def test_qualification_expiry_is_rechecked_on_same_user(member):
    group = Group.objects.create(name="Authorization qualification bundle")
    RoleMetadata.objects.create(
        group=group,
        key="authorization_qualification_bundle",
        display_name=group.name,
        qualification_permission_bundle=True,
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(ClubQualificationType),
        codename="can_manage_ground_instruction",
        defaults={"name": "Can manage ground instruction"},
    )
    group.permissions.add(permission)
    QualificationPermissionGrant.objects.create(group=group, permission=permission)
    qualification = ClubQualificationType.objects.create(
        code="AUTHORIZATION_TEST", name="Authorization test", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    action = "instructors.can_manage_ground_instruction"

    assert resolve_authorization(member, action).allow
    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert resolve_authorization(member, action) == AuthorizationDecision(
        False, "no_grant"
    )
    record.expiration_date = None
    record.save(update_fields=["expiration_date"])
    assert resolve_authorization(member, action).allow
    record.is_qualified = False
    record.save(update_fields=["is_qualified"])
    assert not resolve_authorization(member, action).allow


@pytest.mark.django_db
def test_django_modelbackend_cache_requires_fresh_user_after_role_change(member):
    permission = Permission.objects.get(
        content_type__app_label="auth", codename="view_group"
    )
    group = Group.objects.create(name="Authorization mutable role")
    group.permissions.add(permission)
    member.groups.add(group)
    assert resolve_authorization(member, "auth.view_group").allow
    member.groups.remove(group)
    # ModelBackend caches ordinary permissions on the user instance; this
    # resolver deliberately does not clear Django's cache behind the caller's back.
    assert resolve_authorization(member, "auth.view_group").allow
    fresh_member = get_user_model().objects.get(pk=member.pk)
    assert resolve_authorization(
        fresh_member, "auth.view_group"
    ) == AuthorizationDecision(False, "no_grant")


@pytest.mark.django_db
def test_direct_permission_changes_require_fresh_user_after_cache(member):
    permission = Permission.objects.get(
        content_type__app_label="auth", codename="view_group"
    )
    assert not resolve_authorization(member, "auth.view_group").allow
    member.user_permissions.add(permission)
    assert not resolve_authorization(member, "auth.view_group").allow

    granted = get_user_model().objects.get(pk=member.pk)
    assert resolve_authorization(granted, "auth.view_group").allow
    member.user_permissions.remove(permission)
    assert resolve_authorization(granted, "auth.view_group").allow
    assert not resolve_authorization(
        get_user_model().objects.get(pk=member.pk), "auth.view_group"
    ).allow
