import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from instructors.models import (
    ClubQualificationType,
    MemberQualification,
    QualificationPermissionGrant,
)
from members.models import (
    MemberRoleAssignment,
    MemberTag,
    MemberTagAssignment,
    RoleMetadata,
)
from members.permission_sources import get_permission_sources
from siteconfig.models import MembershipStatus


@pytest.fixture
def member(db):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    return get_user_model().objects.create_user(
        username="source-member", membership_status="Full Member"
    )


@pytest.fixture
def action_permission(db):
    permission, _ = Permission.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(ClubQualificationType),
        codename="can_dispatch_aircraft",
        defaults={"name": "Can dispatch aircraft"},
    )
    return permission


def name_of(permission):
    return f"{permission.content_type.app_label}.{permission.codename}"


def configured_qualification(member, permission, code):
    group = Group.objects.create(name=f"{code} bundle")
    RoleMetadata.objects.create(
        group=group,
        key=f"{code.lower()}_bundle",
        display_name=code,
        qualification_permission_bundle=True,
    )
    group.permissions.add(permission)
    QualificationPermissionGrant.objects.create(group=group, permission=permission)
    qualification = ClubQualificationType.objects.create(
        code=code, name=code, permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )
    return group, record


@pytest.mark.django_db
def test_direct_and_duplicate_group_provenance_remains_separate(
    member, action_permission
):
    group = Group.objects.create(name="Dispatchers")
    RoleMetadata.objects.create(
        group=group, key="dispatchers", display_name="Dispatch team"
    )
    group.permissions.add(action_permission)
    member.groups.add(group)
    member.user_permissions.add(action_permission)
    actor = get_user_model().objects.create_user(username="assigner")
    for source, key in (
        ("manual", "admin"),
        ("status", "Full Member"),
        ("legacy", "instructor"),
    ):
        MemberRoleAssignment.objects.create(
            member=member, group=group, source=source, source_key=key, actor=actor
        )

    result = get_permission_sources(member, name_of(action_permission))
    json.dumps(result)
    entry = result["permissions"][name_of(action_permission)]
    assert entry["effective"]
    assert [row["type"] for row in entry["sources"]] == [
        "direct",
        "group",
        "group",
        "group",
    ]
    assert [
        (row["source"], row["source_key"], row["actor_id"])
        for row in entry["sources"][1:]
    ] == [
        ("manual", "admin", actor.pk),
        ("status", "Full Member", actor.pk),
        ("legacy", "instructor", actor.pk),
    ]
    assert all(
        row["role_key"] == "dispatchers" and row["role_label"] == "Dispatch team"
        for row in entry["sources"][1:]
    )
    assert result == get_permission_sources(member, name_of(action_permission))


@pytest.mark.django_db
def test_untracked_group_and_tags_are_not_permission_sources(member, action_permission):
    group = Group.objects.create(name="Imported")
    group.permissions.add(action_permission)
    member.groups.add(group)
    tag = MemberTag.objects.create(key="dispatch", display_label="Dispatch")
    MemberTagAssignment.objects.create(member=member, tag=tag)
    entry = get_permission_sources(member)["permissions"][name_of(action_permission)]
    assert len(entry["sources"]) == 1
    assert entry["sources"][0]["source"] == "untracked"
    assert entry["sources"][0]["role_key"] is None


@pytest.mark.django_db
def test_qualification_requires_current_approved_safe_grant(member, action_permission):
    group = Group.objects.create(name="Qualified dispatch")
    RoleMetadata.objects.create(
        group=group,
        key="qualified_dispatch",
        display_name="Qualified dispatch",
        qualification_permission_bundle=True,
    )
    group.permissions.add(action_permission)
    QualificationPermissionGrant.objects.create(
        group=group, permission=action_permission
    )
    unapproved, _ = Permission.objects.get_or_create(
        content_type=action_permission.content_type,
        codename="can_dispatch_unapproved",
        defaults={"name": "Unapproved"},
    )
    group.permissions.add(unapproved)
    qualification = ClubQualificationType.objects.create(
        code="DISPATCH", name="Dispatch", permission_group=group
    )
    record = MemberQualification.objects.create(
        member=member, qualification=qualification
    )

    key = name_of(action_permission)
    entry = get_permission_sources(member, key)["permissions"][key]
    assert entry["effective"]
    assert [row["type"] for row in entry["sources"]] == ["qualification"]
    assert name_of(unapproved) not in get_permission_sources(member)["permissions"]
    assert not get_permission_sources(member, name_of(unapproved))["permissions"][
        name_of(unapproved)
    ]["effective"]

    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    expired = get_permission_sources(member, key)["permissions"][key]
    assert not expired["effective"]
    assert expired["sources"][0]["type"] == "qualification"
    assert not expired["sources"][0]["effective"]
    assert expired["sources"][0]["ineffective_reason"] == "expired"
    record.expiration_date = None
    record.is_qualified = False
    record.save(update_fields=["expiration_date", "is_qualified"])
    revoked = get_permission_sources(member, key)["permissions"][key]
    assert not revoked["effective"]
    assert revoked["sources"][0]["type"] == "qualification"
    assert not revoked["sources"][0]["effective"]
    assert revoked["sources"][0]["ineffective_reason"] == "revoked"


@pytest.mark.django_db
def test_qualification_source_shows_disabled_bundle(member, action_permission):
    group, _ = configured_qualification(member, action_permission, "DISABLED")
    RoleMetadata.objects.filter(group=group).update(
        qualification_permission_bundle=False
    )

    key = name_of(action_permission)
    source = get_permission_sources(member, key)["permissions"][key]["sources"][0]
    assert source["effective"] is False
    assert source["ineffective_reason"] == "bundle_disabled"
    assert not member.has_perm(key)


@pytest.mark.django_db
def test_qualification_source_shows_removed_permission(member, action_permission):
    group, _ = configured_qualification(member, action_permission, "REMOVED")
    group.permissions.remove(action_permission)

    key = name_of(action_permission)
    source = get_permission_sources(member, key)["permissions"][key]["sources"][0]
    assert source["effective"] is False
    assert source["ineffective_reason"] == "permission_removed"
    assert not member.has_perm(key)


@pytest.mark.django_db
def test_qualification_source_shows_permission_that_became_unsafe(
    member, action_permission
):
    configured_qualification(member, action_permission, "UNSAFE")
    Permission.objects.filter(pk=action_permission.pk).update(codename="view_unsafe")
    action_permission.refresh_from_db()

    key = name_of(action_permission)
    source = get_permission_sources(member, key)["permissions"][key]["sources"][0]
    assert source["effective"] is False
    assert source["ineffective_reason"] == "unsafe_permission"
    assert not member.has_perm(key)


@pytest.mark.django_db
def test_inactive_user_keeps_configured_direct_source_but_not_effective(
    member, action_permission
):
    member.user_permissions.add(action_permission)
    # Member.save() derives is_active from membership status, so emulate an
    # administratively disabled account without invoking that reconciliation.
    get_user_model().objects.filter(pk=member.pk).update(is_active=False)
    member.refresh_from_db()
    entry = get_permission_sources(member, name_of(action_permission))["permissions"][
        name_of(action_permission)
    ]
    assert not entry["effective"]
    assert entry["sources"][0]["type"] == "direct"
    assert not entry["sources"][0]["effective"]


@pytest.mark.django_db
def test_superuser_override_does_not_expand_all_permissions(member):
    member.is_superuser = True
    member.save(update_fields=["is_superuser"])
    assert get_permission_sources(member)["permissions"] == {}
    result = get_permission_sources(member, "some_app.anything")
    assert result["superuser_override"]
    assert result["permissions"]["some_app.anything"] == {
        "effective": True,
        "sources": [{"type": "superuser", "effective": True}],
    }
