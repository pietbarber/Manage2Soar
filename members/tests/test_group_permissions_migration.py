"""
Tests for members migration 0021: setup_all_group_permissions.

These tests verify that the migration correctly creates every canonical group
and seeds them with the expected permissions.  Because the test database runs
all migrations at setup time, the groups and permissions should already exist
when these tests run -- we simply assert the expected state.
"""

from importlib import import_module

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_perm(group_name, app_label, model_name, codename):
    """Return True if the named group has the given permission.

    Intentionally lets DoesNotExist errors bubble up so tests fail loudly on
    missing ContentType/Permission rows or codename/model typos, rather than
    silently returning False and masking broken permission creation.
    """
    ct = ContentType.objects.get(app_label=app_label, model=model_name)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    group = Group.objects.get(name=group_name)
    return group.permissions.filter(pk=perm.pk).exists()


# ---------------------------------------------------------------------------
# Group existence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_all_canonical_groups_exist():
    """Every group defined in GROUP_PERMISSIONS must be present after migration."""
    expected = [
        "Instructor Admins",
        "Webmasters",
        "Member Managers",
        "Rostermeisters",
        "Secretary",
        "Treasurer",
        "Directors",
    ]
    for name in expected:
        assert Group.objects.filter(
            name=name
        ).exists(), f"Group '{name}' was not created by migration 0021"


@pytest.mark.django_db
def test_every_canonical_permission_is_backfilled_after_all_migrations():
    """0025 must complete any assignments unavailable when 0021 first runs."""
    mapping = import_module(
        "members.migrations.0021_setup_all_group_permissions"
    ).GROUP_PERMISSIONS
    missing = []

    for group_name, permission_tuples in mapping.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            missing.append(f"{group_name}: group missing")
            continue
        for app_label, model_name, codename in permission_tuples:
            permission = Permission.objects.filter(
                content_type__app_label=app_label,
                content_type__model=model_name,
                codename=codename,
            ).first()
            if (
                permission is None
                or not group.permissions.filter(pk=permission.pk).exists()
            ):
                missing.append(f"{group_name}: {app_label}.{model_name}.{codename}")

    assert (
        not missing
    ), "Canonical Group permissions missing after migrations:\n" + "\n".join(missing)


# ---------------------------------------------------------------------------
# Instructor Admins representative permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_instructor_admins_has_instructors_permissions():
    assert _has_perm(
        "Instructor Admins", "instructors", "traininglesson", "add_traininglesson"
    )
    assert _has_perm(
        "Instructor Admins", "instructors", "traininglesson", "change_traininglesson"
    )
    assert _has_perm(
        "Instructor Admins", "instructors", "syllabusdocument", "view_syllabusdocument"
    )


@pytest.mark.django_db
def test_instructor_admins_has_knowledgetest_permissions():
    """Permissions for knowledgetest models (TestPreset, WrittenTest*) must be present."""
    assert _has_perm(
        "Instructor Admins", "knowledgetest", "testpreset", "add_testpreset"
    )
    assert _has_perm(
        "Instructor Admins", "knowledgetest", "testpreset", "view_testpreset"
    )
    assert _has_perm(
        "Instructor Admins",
        "knowledgetest",
        "writtentesttemplate",
        "add_writtentesttemplate",
    )
    assert _has_perm(
        "Instructor Admins",
        "knowledgetest",
        "writtentesttemplate",
        "view_writtentesttemplate",
    )
    assert _has_perm(
        "Instructor Admins",
        "knowledgetest",
        "writtentestattempt",
        "view_writtentestattempt",
    )
    assert _has_perm(
        "Instructor Admins",
        "knowledgetest",
        "writtentestanswer",
        "view_writtentestanswer",
    )
    assert _has_perm(
        "Instructor Admins",
        "knowledgetest",
        "writtentesttemplatequestion",
        "add_writtentesttemplatequestion",
    )


@pytest.mark.django_db
def test_instructor_admins_does_not_have_member_write_permissions():
    """Instructor Admins should not be able to create/edit Member records."""
    assert not _has_perm("Instructor Admins", "members", "member", "add_member")
    assert not _has_perm("Instructor Admins", "members", "member", "delete_member")


# ---------------------------------------------------------------------------
# Webmasters representative permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webmasters_has_cms_permissions():
    assert _has_perm("Webmasters", "cms", "page", "add_page")
    assert _has_perm("Webmasters", "cms", "page", "change_page")
    assert _has_perm("Webmasters", "cms", "page", "delete_page")


# ---------------------------------------------------------------------------
# Secretary / Treasurer – deliberately scoped capabilities
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_secretary_group_has_only_registered_capabilities():
    group = Group.objects.get(name="Secretary")
    assert {
        f"{app}.{codename}"
        for app, codename in group.permissions.values_list(
            "content_type__app_label", "codename"
        )
    } == {
        "cms.view_page",
        "cms.change_page",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
    }


@pytest.mark.django_db
def test_treasurer_group_has_only_registered_capabilities():
    group = Group.objects.get(name="Treasurer")
    assert {
        f"{app}.{codename}"
        for app, codename in group.permissions.values_list(
            "content_type__app_label", "codename"
        )
    } == {
        "billing.can_manage_billing",
        "logsheet.can_manage_logsheet_finances",
        "logsheet.can_export_logsheet_finances",
        "members.view_privileged_contact",
        "duty_roster.view_all_swap_requests",
        "duty_roster.can_manage_any_swap",
        "logsheet.can_unfinalize_logsheet",
    }


@pytest.mark.django_db
def test_directors_have_only_membership_application_view_capability():
    assert _has_perm(
        "Directors",
        "members",
        "membershipapplication",
        "view_membership_applications",
    )
    for codename in (
        "add_membershipapplication",
        "change_membershipapplication",
        "delete_membershipapplication",
    ):
        assert not _has_perm("Directors", "members", "membershipapplication", codename)


# ---------------------------------------------------------------------------
# Member Managers representative permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_member_managers_has_member_crud_permissions():
    assert _has_perm("Member Managers", "members", "member", "add_member")
    assert _has_perm("Member Managers", "members", "member", "change_member")
    assert _has_perm("Member Managers", "members", "member", "delete_member")
    assert _has_perm("Member Managers", "members", "member", "view_member")


@pytest.mark.django_db
def test_member_managers_has_emergency_contact_permissions():
    for codename in (
        "add_emergencycontact",
        "change_emergencycontact",
        "delete_emergencycontact",
        "view_emergencycontact",
    ):
        assert _has_perm("Member Managers", "members", "emergencycontact", codename)


@pytest.mark.django_db
def test_member_managers_has_cms_sitefeedback_permissions():
    assert _has_perm("Member Managers", "cms", "sitefeedback", "add_sitefeedback")
    assert _has_perm("Member Managers", "cms", "sitefeedback", "view_sitefeedback")


@pytest.mark.django_db
def test_member_managers_has_view_only_badge_permission():
    """Member Managers can view the badge catalogue but not create/edit badges."""
    assert _has_perm("Member Managers", "members", "badge", "view_badge")
    assert not _has_perm("Member Managers", "members", "badge", "add_badge")
    assert not _has_perm("Member Managers", "members", "badge", "delete_badge")


# ---------------------------------------------------------------------------
# Rostermeisters representative permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rostermeisters_has_duty_assignment_permissions():
    assert _has_perm(
        "Rostermeisters", "duty_roster", "dutyassignment", "add_dutyassignment"
    )
    assert _has_perm(
        "Rostermeisters", "duty_roster", "dutyassignment", "change_dutyassignment"
    )
    assert _has_perm(
        "Rostermeisters", "duty_roster", "dutyassignment", "view_dutyassignment"
    )


@pytest.mark.django_db
def test_rostermeisters_has_view_only_member_permission():
    """Rostermeisters can look up members but cannot create or delete them."""
    assert _has_perm("Rostermeisters", "members", "member", "view_member")
    assert not _has_perm("Rostermeisters", "members", "member", "add_member")
    assert not _has_perm("Rostermeisters", "members", "member", "delete_member")
