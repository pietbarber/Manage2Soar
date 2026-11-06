import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from tablib import Dataset

from members.admin import MemberAdmin
from members.models import Member
from members.resources import MEMBER_CSV_PRIVILEGE_FIELDS
from siteconfig.models import MembershipStatus


def _request(user):
    request = RequestFactory().post("/admin/members/member/import/")
    request.user = user
    return request


def _limited_editor(username="member-import-editor"):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    editor = get_user_model().objects.create_user(
        username=username,
        password="password",
        is_staff=True,
        membership_status="Full Member",
    )
    editor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="members", codename="change_member"
        ),
        Permission.objects.get(
            content_type__app_label="members", codename="import_member"
        ),
    )
    return editor


@pytest.mark.django_db
def test_limited_member_importer_cannot_import_role_or_privilege_fields():
    editor = _limited_editor()
    target = Member.objects.create_user(username="csv-import-target")
    member_admin = MemberAdmin(Member, admin.site)
    request = _request(editor)

    assert member_admin.has_import_permission(request)
    resource_class = member_admin.get_import_resource_classes(request)[0]
    imported_fields = set(resource_class().fields)
    assert not MEMBER_CSV_PRIVILEGE_FIELDS.intersection(imported_fields)

    privilege_headers = sorted(MEMBER_CSV_PRIVILEGE_FIELDS)
    dataset = Dataset(headers=["id", "username", *privilege_headers])
    dataset.append((str(target.pk), target.username, *(["1"] * len(privilege_headers))))
    result = resource_class().import_data(dataset, dry_run=False, user=editor)

    assert not result.has_errors()
    target.refresh_from_db()
    assert not target.instructor
    assert not target.is_staff
    assert not target.member_manager
    assert not target.stats_monger


@pytest.mark.django_db
def test_limited_member_importer_can_still_import_profile_fields():
    editor = _limited_editor(username="member-profile-import-editor")
    target = Member.objects.create_user(
        username="profile-import-target", first_name="Before"
    )
    member_admin = MemberAdmin(Member, admin.site)
    request = _request(editor)
    resource_class = member_admin.get_import_resource_classes(request)[0]

    dataset = Dataset(headers=["id", "username", "first_name", "email"])
    dataset.append((str(target.pk), target.username, "After", "after@example.com"))
    result = resource_class().import_data(dataset, dry_run=False, user=editor)

    assert not result.has_errors()
    target.refresh_from_db()
    assert target.first_name == "After"
    assert target.email == "after@example.com"


@pytest.mark.django_db
def test_member_import_requires_explicit_import_permission():
    editor = _limited_editor(username="member-import-denied")
    editor.user_permissions.remove(
        Permission.objects.get(
            content_type__app_label="members", codename="import_member"
        )
    )

    assert not MemberAdmin(Member, admin.site).has_import_permission(_request(editor))


@pytest.mark.django_db
def test_member_import_also_requires_member_change_permission():
    editor = _limited_editor(username="member-import-no-change")
    editor.user_permissions.remove(
        Permission.objects.get(
            content_type__app_label="members", codename="change_member"
        )
    )

    assert not MemberAdmin(Member, admin.site).has_import_permission(_request(editor))


@pytest.mark.django_db
def test_superuser_member_import_can_import_role_fields():
    superuser = get_user_model().objects.create_superuser(
        username="member-import-superuser", password="password"
    )
    target = Member.objects.create_user(username="superuser-import-target")
    member_admin = MemberAdmin(Member, admin.site)
    request = _request(superuser)

    resource_class = member_admin.get_import_resource_classes(request)[0]
    imported_fields = set(resource_class().fields)
    assert {"instructor", "member_manager", "stats_monger"}.issubset(imported_fields)

    dataset = Dataset(
        headers=["id", "username", "instructor", "member_manager", "stats_monger"]
    )
    dataset.append((str(target.pk), target.username, "1", "1", "1"))
    result = resource_class().import_data(dataset, dry_run=False, user=superuser)

    assert not result.has_errors()
    target.refresh_from_db()
    assert target.instructor
    assert target.member_manager
    assert target.stats_monger
