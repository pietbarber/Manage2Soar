from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from instructors.admin import ClubQualificationTypeAdmin
from instructors.models import (
    ClubQualificationType,
    GroundInstruction,
    MemberQualification,
    QualificationPermissionGrant,
)
from members.models import RoleMetadata
from siteconfig.models import MembershipStatus


@pytest.fixture(autouse=True)
def active_membership_status(db):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )


@pytest.fixture
def bundle(db):
    group = Group.objects.create(name="Current qualification operators")
    RoleMetadata.objects.create(
        group=group,
        key="current_qualification_operators",
        display_name=group.name,
        qualification_permission_bundle=True,
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(GroundInstruction),
        codename="can_manage_ground_instruction",
        defaults={"name": "Can manage ground instruction"},
    )
    group.permissions.add(permission)
    QualificationPermissionGrant.objects.create(group=group, permission=permission)
    return group, permission


@pytest.mark.django_db
def test_unmapped_qualification_grants_no_permission(db):
    member = get_user_model().objects.create_user(
        username="unmapped", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="UNMAPPED", name="Unmapped"
    )
    MemberQualification.objects.create(member=member, qualification=qualification)
    assert not member.has_perm("instructors.view_clubqualificationtype")


@pytest.mark.django_db
def test_unmapped_qualification_has_no_custom_permissions(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="unmapped-custom", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="UNMAPPED_CUSTOM", name="Unmapped custom"
    )
    MemberQualification.objects.create(member=member, qualification=qualification)

    permission_name = f"{permission.content_type.app_label}.{permission.codename}"
    assert permission_name not in member.get_all_permissions()
    assert not member.has_perm(permission_name)


@pytest.mark.django_db
def test_current_expired_and_revoked_qualification_permissions(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="qualified", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="CURRENT", name="Current", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert member.has_perm(permission_name)
    assert not member.has_perm(permission_name, qualification)
    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert not member.has_perm(permission_name)
    record.expiration_date = None
    record.is_qualified = False
    record.save(update_fields=["expiration_date", "is_qualified"])
    assert not member.has_perm(permission_name)


@pytest.mark.django_db
def test_expiry_and_revocation_refresh_has_perm_for_same_user(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="has-perm-refresh", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="HAS_PERM_REFRESH", name="Has perm refresh", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert member.has_perm(permission_name)
    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert not member.has_perm(permission_name)

    record.expiration_date = timezone.localdate()
    record.is_qualified = True
    record.save(update_fields=["expiration_date", "is_qualified"])
    assert member.has_perm(permission_name)
    record.is_qualified = False
    record.save(update_fields=["is_qualified"])
    assert not member.has_perm(permission_name)


@pytest.mark.django_db
def test_expiry_and_revocation_refresh_get_all_permissions_for_same_user(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="all-permissions-refresh", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="ALL_PERMISSIONS_REFRESH",
        name="All permissions refresh",
        permission_group=group,
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert permission_name in member.get_all_permissions()
    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert permission_name not in member.get_all_permissions()

    record.expiration_date = None
    record.is_qualified = True
    record.save(update_fields=["expiration_date", "is_qualified"])
    assert permission_name in member.get_all_permissions()
    record.is_qualified = False
    record.save(update_fields=["is_qualified"])
    assert permission_name not in member.get_all_permissions()


@pytest.mark.django_db
def test_inactive_user_gets_no_qualification_permissions(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="inactive", membership_status="Full Member"
    )
    get_user_model().objects.filter(pk=member.pk).update(is_active=False)
    member.refresh_from_db()
    qualification = ClubQualificationType.objects.create(
        code="INACTIVE", name="Inactive", permission_group=group
    )
    MemberQualification.objects.create(member=member, qualification=qualification)
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert not member.has_perm(permission_name)
    assert permission_name not in member.get_all_permissions()


@pytest.mark.django_db
def test_inactive_membership_suspends_qualification_permissions(bundle, monkeypatch):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="inactive-membership", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="INACTIVE_STATUS", name="Inactive status", permission_group=group
    )
    MemberQualification.objects.create(member=member, qualification=qualification)
    monkeypatch.setattr(member, "is_active_member", lambda: False)
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"
    assert not member.has_perm(permission_name)
    assert permission_name not in member.get_all_permissions()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "codename", ["manage_roster", "impersonate_member", "export_members"]
)
def test_unapproved_sensitive_custom_permission_is_denied(bundle, codename):
    group, _ = bundle
    member = get_user_model().objects.create_user(
        username=f"deny-{codename}", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code=f"DENY_{codename}", name="Deny", permission_group=group
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(ClubQualificationType),
        codename=codename,
        defaults={"name": codename.replace("_", " ")},
    )
    group.permissions.add(permission)
    MemberQualification.objects.create(member=member, qualification=qualification)
    assert not member.has_perm(f"instructors.{codename}")


@pytest.mark.django_db
def test_expiration_date_is_inclusive_and_null_is_current(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="inclusive-expiry", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="INCLUSIVE", name="Inclusive", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member,
        qualification=qualification,
        expiration_date=timezone.localdate(),
    )
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert member.has_perm(permission_name)
    record.expiration_date = None
    record.save(update_fields=["expiration_date"])
    assert permission_name in member.get_all_permissions()


@pytest.mark.django_db
def test_bundle_group_is_not_added_to_member_groups(bundle):
    group, _ = bundle
    member = get_user_model().objects.create_user(
        username="not-a-role-member", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="NO_GROUP", name="No group membership", permission_group=group
    )
    MemberQualification.objects.create(member=member, qualification=qualification)
    assert not member.groups.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_group_without_metadata_cannot_be_a_bundle():
    group = Group.objects.create(name="Unconfigured bundle")
    with pytest.raises(ValidationError) as exc_info:
        ClubQualificationType.objects.create(
            code="NO_METADATA", name="No metadata", permission_group=group
        )
    assert "permission_group" in exc_info.value.message_dict


@pytest.mark.django_db
def test_backend_rejects_protected_bundle_and_admin_permissions(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="defense-in-depth", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="DEFENSE", name="Defense", permission_group=group
    )
    MemberQualification.objects.create(member=member, qualification=qualification)
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"
    assert member.has_perm(permission_name)

    admin_permission = Permission.objects.get(
        content_type__app_label="auth", codename="add_group"
    )
    group.permissions.add(admin_permission)
    assert not member.has_perm("auth.add_group")

    qualification_admin_permission = Permission.objects.get(
        content_type__app_label="instructors",
        codename="change_clubqualificationtype",
    )
    group.permissions.add(qualification_admin_permission)
    assert not member.has_perm("instructors.change_clubqualificationtype")

    standard_permission = Permission.objects.get(
        content_type__app_label="instructors", codename="view_clubqualificationtype"
    )
    group.permissions.add(standard_permission)
    assert not member.has_perm("instructors.view_clubqualificationtype")

    RoleMetadata.objects.filter(group=group).update(is_protected=True)
    assert not member.has_perm(permission_name)


@pytest.mark.django_db
def test_bundle_cannot_include_qualification_administration_permissions(bundle):
    group, _ = bundle
    permission = Permission.objects.get(
        content_type__app_label="instructors", codename="delete_memberqualification"
    )
    group.permissions.add(permission)

    with pytest.raises(ValidationError) as exc_info:
        ClubQualificationType.objects.create(
            code="ADMIN_PERMISSION", name="Admin permission", permission_group=group
        )
    assert "permission_group" in exc_info.value.message_dict


@pytest.mark.django_db
def test_admin_bundle_choices_exclude_qualification_administration_permissions(bundle):
    group, _ = bundle
    permission = Permission.objects.get(
        content_type__app_label="instructors",
        codename="add_clubqualificationtype",
    )
    group.permissions.add(permission)

    model_admin = ClubQualificationTypeAdmin(ClubQualificationType, admin.site)
    field = model_admin.formfield_for_foreignkey(
        ClubQualificationType._meta.get_field("permission_group"), None
    )
    assert not field.queryset.filter(pk=group.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "codename",
    [
        "add_clubqualificationtype",
        "change_clubqualificationtype",
        "delete_clubqualificationtype",
        "view_clubqualificationtype",
    ],
)
def test_bundle_rejects_standard_crud_permissions(bundle, codename):
    group, _ = bundle
    permission = Permission.objects.get(
        content_type__app_label="instructors", codename=codename
    )
    group.permissions.add(permission)

    with pytest.raises(ValidationError):
        ClubQualificationType.objects.create(
            code=f"STANDARD_{codename}",
            name="Standard permission",
            permission_group=group,
        )


@pytest.mark.django_db
def test_obsolete_qualification_does_not_grant_bundle_permissions(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="obsolete", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="OBSOLETE", name="Obsolete", permission_group=group, is_obsolete=True
    )
    MemberQualification.objects.create(member=member, qualification=qualification)

    permission_name = f"{permission.content_type.app_label}.{permission.codename}"
    assert not member.has_perm(permission_name)


@pytest.mark.django_db
@pytest.mark.parametrize("flag", ["is_builtin", "is_protected", "is_system_managed"])
def test_protected_or_system_role_cannot_opt_in(flag):
    group = Group.objects.create(name=f"Invalid {flag}")
    metadata = RoleMetadata(
        group=group,
        key=f"invalid_{flag}",
        display_name=group.name,
        qualification_permission_bundle=True,
    )
    setattr(metadata, flag, True)
    with pytest.raises(ValidationError):
        metadata.save()


@pytest.mark.django_db
def test_permission_evaluation_rechecks_expiry_without_refreshing_user(bundle):
    group, permission = bundle
    member = get_user_model().objects.create_user(
        username="expiry-recheck", membership_status="Full Member"
    )
    qualification = ClubQualificationType.objects.create(
        code="RECHECK", name="Expiry recheck", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    permission_name = f"{permission.content_type.app_label}.{permission.codename}"

    assert member.has_perm(permission_name)
    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert not member.has_perm(permission_name)
