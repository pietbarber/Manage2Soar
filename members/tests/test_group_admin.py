from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory
from django.urls import reverse

import members.admin as members_admin_module
from members.admin import MemberAdmin, RoleMetadataInline, SuperuserOnlyGroupAdmin
from members.models import Member, MemberRoleAssignment, RoleMetadata
from siteconfig.models import MailingList, MembershipStatus


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="group-admin-superuser", password="password"
    )


@pytest.fixture
def staff_user(db):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    user = get_user_model().objects.create_user(
        username="group-admin-staff",
        password="password",
        is_staff=True,
        membership_status="Full Member",
    )
    get_user_model().objects.filter(pk=user.pk).update(is_active=True)
    return user


@pytest.mark.django_db
def test_group_admin_is_superuser_only(client, superuser, staff_user):
    add_url = reverse("admin:auth_group_add")

    client.force_login(staff_user)
    response = client.get(add_url)
    assert response.status_code == 403
    assert not Group.objects.filter(name="Staff-created role").exists()

    client.force_login(superuser)
    assert client.get(add_url).status_code == 200


@pytest.mark.django_db
def test_group_admin_does_not_offer_bulk_delete(superuser):
    request = RequestFactory().get("/admin/auth/group/")
    request.user = superuser
    group_admin = SuperuserOnlyGroupAdmin(Group, admin.site)

    assert "delete_selected" not in group_admin.get_actions(request)


@pytest.mark.django_db
def test_custom_group_can_be_created_permissionless_with_metadata(client, superuser):
    client.force_login(superuser)

    response = client.post(
        reverse("admin:auth_group_add"),
        {
            "name": "Custom role",
            "permissions": [],
            "role_metadata-TOTAL_FORMS": "1",
            "role_metadata-INITIAL_FORMS": "0",
            "role_metadata-MIN_NUM_FORMS": "0",
            "role_metadata-MAX_NUM_FORMS": "1",
            "role_metadata-0-key": "custom_role",
            "role_metadata-0-display_name": "Custom role",
            "role_metadata-0-description": "A deliberately empty role",
            "role_metadata-0-sort_order": "10",
        },
    )

    assert response.status_code == 302
    group = Group.objects.get(name="Custom role")
    assert not group.permissions.exists()
    assert group.role_metadata.key == "custom_role"


@pytest.mark.django_db
def test_legacy_group_can_add_its_first_metadata_row(client, superuser):
    client.force_login(superuser)
    group = Group.objects.create(name="Legacy role")

    response = client.post(
        reverse("admin:auth_group_change", args=[group.pk]),
        {
            "name": group.name,
            "permissions": [],
            "role_metadata-TOTAL_FORMS": "1",
            "role_metadata-INITIAL_FORMS": "0",
            "role_metadata-MIN_NUM_FORMS": "0",
            "role_metadata-MAX_NUM_FORMS": "1",
            "role_metadata-0-key": "legacy_role",
            "role_metadata-0-display_name": "Legacy role",
            "role_metadata-0-description": "Metadata added later",
            "role_metadata-0-sort_order": "5",
        },
    )

    assert response.status_code == 302
    assert group.role_metadata.key == "legacy_role"


@pytest.mark.django_db
def test_protected_metadata_cannot_be_deleted_with_its_group(client, superuser):
    client.force_login(superuser)
    group = Group.objects.create(name="Built-in role")
    RoleMetadata.objects.create(
        group=group,
        key="built_in_role",
        display_name="Built-in role",
        is_builtin=True,
        is_protected=True,
        is_system_managed=True,
    )

    response = client.get(reverse("admin:auth_group_delete", args=[group.pk]))

    assert response.status_code == 403
    assert Group.objects.filter(pk=group.pk).exists()
    assert RoleMetadata.objects.filter(group=group, is_protected=True).exists()


@pytest.mark.django_db
def test_custom_group_deletion_cascades_to_metadata(client, superuser):
    client.force_login(superuser)
    group = Group.objects.create(name="Deletable custom role")
    metadata = RoleMetadata.objects.create(
        group=group,
        key="deletable_custom_role",
        display_name="Deletable custom role",
    )

    response = client.post(
        reverse("admin:auth_group_delete", args=[group.pk]),
        {"post": "yes"},
    )

    assert response.status_code == 302
    assert not Group.objects.filter(pk=group.pk).exists()
    assert not RoleMetadata.objects.filter(pk=metadata.pk).exists()


@pytest.mark.django_db
def test_group_with_mailing_list_role_criterion_cannot_be_deleted(client, superuser):
    client.force_login(superuser)
    group = Group.objects.create(name="Mailing list role")
    metadata = RoleMetadata.objects.create(
        group=group,
        key="mailing_list_role",
        display_name="Mailing list role",
    )
    MailingList.objects.create(
        name="mailing-list-role-users", criteria=[f"role:{metadata.key}"]
    )

    response = client.get(reverse("admin:auth_group_delete", args=[group.pk]))

    assert response.status_code == 403
    assert Group.objects.filter(pk=group.pk).exists()
    assert RoleMetadata.objects.filter(pk=metadata.pk).exists()

    request = RequestFactory().get("/admin/")
    request.user = superuser
    inline = RoleMetadataInline(RoleMetadata, admin.site)
    assert inline.has_delete_permission(request, group) is False


@pytest.mark.django_db
def test_group_can_be_deleted_after_mailing_list_role_criterion_is_removed(
    client, superuser
):
    client.force_login(superuser)
    group = Group.objects.create(name="Removable mailing list role")
    metadata = RoleMetadata.objects.create(
        group=group,
        key="removable_mailing_list_role",
        display_name="Removable mailing list role",
    )
    mailing_list = MailingList.objects.create(
        name="removable-mailing-list-role-users",
        criteria=[f"role:{metadata.key}"],
    )

    mailing_list.criteria = []
    mailing_list.save(update_fields=["criteria"])

    response = client.post(
        reverse("admin:auth_group_delete", args=[group.pk]),
        {"post": "yes"},
    )

    assert response.status_code == 302
    assert not Group.objects.filter(pk=group.pk).exists()
    assert not RoleMetadata.objects.filter(pk=metadata.pk).exists()


@pytest.mark.django_db
def test_metadata_edit_preserves_group_permissions_and_memberships(client, superuser):
    client.force_login(superuser)
    group = Group.objects.create(name="Editable role")
    metadata = RoleMetadata.objects.create(
        group=group,
        key="editable_role",
        display_name="Editable role",
    )
    member = get_user_model().objects.create_user(username="role-member")
    member.groups.add(group)
    permission = Permission.objects.order_by("pk").first()
    assert permission is not None
    group.permissions.add(permission)

    response = client.post(
        reverse("admin:auth_group_change", args=[group.pk]),
        {
            "name": group.name,
            "permissions": [str(permission.pk)],
            "role_metadata-TOTAL_FORMS": "1",
            "role_metadata-INITIAL_FORMS": "1",
            "role_metadata-MIN_NUM_FORMS": "0",
            "role_metadata-MAX_NUM_FORMS": "1",
            "role_metadata-0-id": str(metadata.pk),
            "role_metadata-0-group": str(group.pk),
            "role_metadata-0-key": metadata.key,
            "role_metadata-0-display_name": "Renamed editable role",
            "role_metadata-0-description": "Updated without changing access",
            "role_metadata-0-sort_order": "20",
        },
    )

    assert response.status_code == 302
    group.refresh_from_db()
    member.refresh_from_db()
    assert group.permissions.values_list("pk", flat=True).get() == permission.pk
    assert member.groups.filter(pk=group.pk).exists()
    assert group.role_metadata.display_name == "Renamed editable role"
    assert group.role_metadata.key == metadata.key


@pytest.mark.django_db
def test_member_admin_group_add_and_remove_records_manual_provenance(superuser):
    member = Member.objects.create_user(username="admin-provenance-member")
    custom_group = Group.objects.create(name="Admin-selected custom role")
    request = RequestFactory().post("/admin/")
    request.user = superuser
    member_admin = MemberAdmin(Member, admin.site)
    form = SimpleNamespace(
        instance=member,
        changed_data=[],
        save_m2m=lambda: None,
    )

    member_admin.save_model(request, member, form, change=True)
    member.groups.add(custom_group)
    member_admin.save_related(request, form, [], change=True)

    assignment = MemberRoleAssignment.objects.get(
        member=member, group=custom_group, source="manual"
    )
    assert assignment.source_key == "admin"
    assert assignment.actor == superuser

    member_admin.save_model(request, member, form, change=True)
    member.groups.remove(custom_group)
    member_admin.save_related(request, form, [], change=True)
    assert not MemberRoleAssignment.objects.filter(pk=assignment.pk).exists()


@pytest.mark.django_db
def test_member_admin_removes_only_its_manual_source(superuser):
    member = Member.objects.create_user(username="admin-multi-source-member")
    group = Group.objects.create(name="Multi-source role")
    request = RequestFactory().post("/admin/")
    request.user = superuser
    member_admin = MemberAdmin(Member, admin.site)
    form = SimpleNamespace(instance=member, changed_data=[], save_m2m=lambda: None)

    member_admin.save_model(request, member, form, change=True)
    member.groups.add(group)
    member_admin.save_related(request, form, [], change=True)
    committee = MemberRoleAssignment.objects.create(
        member=member,
        group=group,
        source="manual",
        source_key="committee",
    )

    member_admin.save_model(request, member, form, change=True)
    member.groups.remove(group)
    member_admin.save_related(request, form, [], change=True)

    assert MemberRoleAssignment.objects.filter(pk=committee.pk).exists()
    assert not MemberRoleAssignment.objects.filter(
        member=member, group=group, source="manual", source_key="admin"
    ).exists()
    assert member.groups.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_real_member_admin_form_routes_groups_through_role_service(
    superuser, monkeypatch
):
    member = Member.objects.create_user(username="real-admin-form-member")
    group = Group.objects.create(name="Real form selected role")
    request = RequestFactory().post("/admin/")
    request.user = superuser
    member_admin = MemberAdmin(Member, admin.site)
    form_class = member_admin.get_form(request, member)
    form = form_class(
        data={
            "username": member.username,
            "date_joined_0": member.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": member.date_joined.strftime("%H:%M:%S"),
            "glider_rating": member.glider_rating,
            "contact_visibility_email": "inherit",
            "contact_visibility_phone": "inherit",
            "contact_visibility_address": "inherit",
            "is_active": "on",
            "groups": [str(group.pk)],
        },
        instance=member,
    )
    assert form.is_valid(), form.errors
    form.instance = form.save(commit=False)
    member_admin.save_model(request, form.instance, form, change=True)

    original_save_m2m = form.save_m2m
    groups_present_during_save_m2m = None

    def observed_save_m2m():
        nonlocal groups_present_during_save_m2m
        groups_present_during_save_m2m = "groups" in form.cleaned_data
        original_save_m2m()

    form.save_m2m = observed_save_m2m
    calls = []
    real_set_manual_role = members_admin_module.set_manual_role

    def observed_set_manual_role(*args, **kwargs):
        calls.append((args, kwargs))
        return real_set_manual_role(*args, **kwargs)

    monkeypatch.setattr(
        members_admin_module, "set_manual_role", observed_set_manual_role
    )

    member_admin.save_related(request, form, [], change=True)

    assert groups_present_during_save_m2m is False
    assert len(calls) == 1
    assert calls[0][0][:2] == (member, group)
    assert calls[0][1] == {"enabled": True, "actor": superuser}
    assert MemberRoleAssignment.objects.filter(
        member=member,
        group=group,
        source="manual",
        source_key="admin",
        actor=superuser,
    ).exists()
    assert member.groups.filter(pk=group.pk).exists()


@pytest.mark.django_db
def test_member_admin_permission_summary_shows_every_group_source(superuser):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    member = Member.objects.create_user(
        username="permission-summary-member", membership_status="Full Member"
    )
    group = Group.objects.create(name="Summary role")
    permission = Permission.objects.get(
        content_type__app_label="auth", codename="view_group"
    )
    group.permissions.add(permission)
    member.groups.add(group)
    MemberRoleAssignment.objects.create(
        member=member,
        group=group,
        source="manual",
        source_key="admin",
        actor=superuser,
    )
    MemberRoleAssignment.objects.create(
        member=member,
        group=group,
        source="status",
        source_key="Full Member",
    )

    summary = str(MemberAdmin(Member, admin.site).permission_source_summary(member))

    assert "auth.view_group [effective]" in summary
    assert "Group Summary role (manual:admin)" in summary
    assert f"actor member #{superuser.pk}" in summary
    assert "Group Summary role (status:Full Member)" in summary


@pytest.mark.django_db
def test_member_admin_canonical_group_with_enabled_flag_is_not_manual(superuser):
    member = Member.objects.create_user(
        username="admin-canonical-role", instructor=True
    )
    canonical_group, _ = Group.objects.get_or_create(name="Instructor Admins")
    request = RequestFactory().post("/admin/")
    request.user = superuser
    member_admin = MemberAdmin(Member, admin.site)
    form = SimpleNamespace(
        instance=member,
        changed_data=[],
        save_m2m=lambda: None,
    )

    member_admin.save_model(request, member, form, change=True)
    member.groups.add(canonical_group)
    member_admin.save_related(request, form, [], change=True)

    assert not MemberRoleAssignment.objects.filter(
        member=member, group=canonical_group, source="manual"
    ).exists()
    member._sync_groups()
    assert (
        MemberRoleAssignment.objects.filter(
            member=member,
            group=canonical_group,
            source="legacy",
            source_key="instructor",
        ).count()
        == 1
    )
