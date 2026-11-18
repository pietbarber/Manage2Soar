"""Behavior regressions found while comparing PR 1140 with its base."""

from datetime import date

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from cms.admin import PageAdmin
from cms.models import Page, PageMemberPermission, PageRolePermission
from duty_roster.models import DutyAssignment
from instructors.models import (
    ClubQualificationType,
    InstructionReport,
    MemberQualification,
)
from knowledgetest.admin import TestPresetAdmin as PresetAdmin
from knowledgetest.models import TestPreset as Preset
from members.admin import MemberAdmin
from members.models import Member, MemberRoleAssignment, RoleMetadata
from members.services.status_role_reconciliation import apply
from notifications.models import Notification
from siteconfig.models import MembershipStatus, MembershipStatusRoleMapping

pytestmark = pytest.mark.django_db


@pytest.fixture
def status():
    return MembershipStatus.objects.create(name="Parity Active", is_active=True)


@pytest.fixture
def member(status):
    return Member.objects.create_user(
        username="parity-member", membership_status=status.name
    )


@pytest.fixture
def role():
    group = Group.objects.create(name="Parity Custom Role")
    RoleMetadata.objects.create(
        group=group, key="parity_custom", display_name=group.name
    )
    return group


def grant(member, permission):
    app_label, codename = permission.split(".")
    member.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )


def test_limited_changelist_cannot_assign_privileged_membership_status(
    client, member, role, django_capture_on_commit_callbacks
):
    member.is_staff = True
    member.save()
    grant(member, "members.change_member")
    privileged = MembershipStatus.objects.create(
        name="Parity Privileged", is_active=True
    )
    MembershipStatusRoleMapping.objects.create(membership_status=privileged, role=role)
    client.force_login(member)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("admin:members_member_changelist"),
            {
                "_save": "Save",
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(member.pk),
                "form-0-membership_status": privileged.name,
            },
        )
    assert response.status_code == 200
    member.refresh_from_db()
    assert member.membership_status == "Parity Active"
    assert not member.groups.filter(pk=role.pk).exists()


def test_superuser_changelist_retains_status_editing(member):
    member.is_superuser = True
    member.save()
    request = RequestFactory().get("/admin/members/member/")
    request.user = member
    assert MemberAdmin(Member, admin.site).get_changelist_instance(
        request
    ).list_editable == ("membership_status",)


def test_flight_report_cannot_award_qualification_without_assignment_grant(
    client, member
):
    grant(member, "instructors.can_record_instruction")
    qualification = ClubQualificationType.objects.create(code="PARITY", name="Parity")
    client.force_login(member)
    url = reverse(
        "instructors:fill_instruction_report",
        kwargs={
            "student_id": member.pk,
            "report_date": timezone.localdate().isoformat(),
        },
    )
    response = client.post(
        url,
        {
            "report_text": "A flight",
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "qual_qualification": str(qualification.pk),
            "qual_is_qualified": "on",
        },
    )
    assert response.status_code == 403
    assert not InstructionReport.objects.exists()
    assert not MemberQualification.objects.exists()


def test_training_record_grant_is_not_flying_instructor_eligibility(client, member):
    grant(member, "instructors.can_record_instruction")
    day = date(2030, 1, 5)
    assignment = DutyAssignment.objects.create(date=day)
    client.force_login(member)
    response = client.post(
        reverse(
            "duty_roster:calendar_instructor_signup",
            kwargs={
                "year": day.year,
                "month": day.month,
                "day": day.day,
            },
        )
    )
    assert response.status_code == 403
    assignment.refresh_from_db()
    assert assignment.instructor_id is None


def test_active_member_retains_written_test_practice_builder(client, member):
    from knowledgetest.views import CreateWrittenTestView

    request = RequestFactory().get("/knowledgetest/create/")
    request.user = member
    request.session = {}
    response = CreateWrittenTestView.as_view()(request)
    assert response.status_code == 200


def test_moving_mapping_reconciles_both_statuses(
    member, status, role, django_capture_on_commit_callbacks
):
    other_status = MembershipStatus.objects.create(name="Parity Other", is_active=True)
    other = Member.objects.create_user(
        username="parity-other", membership_status=other_status.name
    )
    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    apply(member)
    assert member.groups.filter(pk=role.pk).exists()
    with django_capture_on_commit_callbacks(execute=True):
        mapping.membership_status = other_status
        mapping.save()
    assert not member.groups.filter(pk=role.pk).exists()
    assert other.groups.filter(pk=role.pk).exists()


def test_status_overlay_preserves_preexisting_unexplained_membership(
    member, status, role
):
    member.groups.add(role)
    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    apply(member)
    mapping.enabled = False
    mapping.save()
    apply(member)
    assert member.groups.filter(pk=role.pk).exists()
    assert MemberRoleAssignment.objects.filter(
        member=member, group=role, source="manual"
    ).exists()


@pytest.mark.parametrize(
    "permission",
    [
        "change_writtentesttemplate",
        "change_testpreset",
        "delete_testpreset",
    ],
)
def test_model_permission_does_not_grant_shared_preset_admin(member, permission):
    grant(member, "knowledgetest." + permission)
    request = RequestFactory().get("/admin/knowledgetest/testpreset/")
    request.user = member
    model_admin = PresetAdmin(Preset, admin.site)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


def test_instructor_group_retains_legacy_preset_admin_denial(member):
    member.instructor = True
    member.save()
    request = RequestFactory().get("/admin/knowledgetest/testpreset/")
    request.user = Member.objects.get(pk=member.pk)
    model_admin = PresetAdmin(Preset, admin.site)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


@pytest.mark.parametrize(
    "capability,can_edit,can_delete",
    [
        ("can_manage_test_presets", True, False),
        ("can_delete_test_presets", False, True),
    ],
)
def test_preset_capabilities_are_independent(member, capability, can_edit, can_delete):
    grant(member, "knowledgetest." + capability)
    request = RequestFactory().get("/admin/knowledgetest/testpreset/")
    request.user = member
    model_admin = PresetAdmin(Preset, admin.site)
    assert model_admin.has_add_permission(request) is can_edit
    assert model_admin.has_change_permission(request) is can_edit
    assert model_admin.has_delete_permission(request) is can_delete


def test_content_edit_permission_does_not_grant_navbar_promotion(member):
    grant(member, "cms.change_page")
    request = RequestFactory().get("/admin/cms/page/")
    request.user = member
    assert not PageAdmin(Page, admin.site)._can_manage_navbar_promotion(request)


@pytest.mark.parametrize("partial_save", [False, True])
def test_returning_member_is_reactivated(member, partial_save):
    inactive = MembershipStatus.objects.create(name="Parity Inactive", is_active=False)
    member.membership_status = inactive.name
    member.save()
    assert not member.is_active
    member.membership_status = "Parity Active"
    member.save(**({"update_fields": ["membership_status"]} if partial_save else {}))
    member.refresh_from_db()
    assert member.is_active


def test_explicit_account_suspension_is_preserved(member):
    member.is_active = False
    member.save()
    member.refresh_from_db()
    assert not member.is_active


@pytest.mark.parametrize("capability", ["can_generate_roster", "can_edit_roster"])
def test_roster_capabilities_do_not_authorize_each_others_actions(
    client, member, capability
):
    grant(member, "duty_roster." + capability)
    client.force_login(member)
    if capability == "can_generate_roster":
        response = client.get(
            reverse(
                "duty_roster:assignment_edit_form",
                kwargs={
                    "year": 2030,
                    "month": 1,
                    "day": 5,
                },
            )
        )
        assert response.status_code == 403
        assert not DutyAssignment.objects.filter(date=date(2030, 1, 5)).exists()
    else:
        response = client.get(reverse("duty_roster:propose_roster"))
        assert response.status_code in (302, 403)


@override_settings(DEBUG=False)
def test_empty_role_preview_does_not_inherit_personal_cms_grants(client, role):
    actor = Member.objects.create_superuser(
        username="parity-preview-actor", password="pass"
    )
    page = Page.objects.create(
        title="Private parity", slug="private-parity", is_public=False
    )
    PageRolePermission.objects.create(page=page, role_name="director")
    PageMemberPermission.objects.create(page=page, member=actor)
    client.force_login(actor)
    session = client.session
    session["role_preview"] = {"role_key": "parity_custom", "debug": False}
    session.save()
    response = client.get(reverse("cms:cms_page", kwargs={"path": page.slug}))
    assert response.status_code in (302, 403)
    assert page.member_permissions.filter(member=actor).exists()


def test_preview_does_not_dismiss_real_actors_notifications(client, role):
    actor = Member.objects.create_superuser(
        username="parity-notification-actor", password="pass"
    )
    notification = Notification.objects.create(
        user=actor, message="Parity notification"
    )
    client.force_login(actor)
    session = client.session
    session["role_preview"] = {"role_key": "parity_custom", "debug": False}
    session.save()
    response = client.get(reverse("dismiss_notification", args=[notification.pk]))
    assert response.status_code == 405
    notification.refresh_from_db()
    assert not notification.dismissed


def test_preview_assignment_form_does_not_create_an_operational_day(client, role):
    actor = Member.objects.create_superuser(
        username="preview-roster-actor", password="pass"
    )
    role.permissions.add(
        Permission.objects.get(
            content_type__app_label="duty_roster", codename="can_edit_roster"
        )
    )
    client.force_login(actor)
    session = client.session
    session["role_preview"] = {"role_key": "parity_custom", "debug": False}
    session.save()
    day = date(2030, 1, 7)
    response = client.get(
        reverse(
            "duty_roster:assignment_edit_form",
            kwargs={
                "year": day.year,
                "month": day.month,
                "day": day.day,
            },
        )
    )
    assert response.status_code == 200
    assert not DutyAssignment.objects.filter(date=day).exists()


def test_preview_biography_does_not_create_a_member_record(client, role, member):
    from members.models import Biography

    actor = Member.objects.create_superuser(
        username="preview-bio-actor", password="pass"
    )
    client.force_login(actor)
    session = client.session
    session["role_preview"] = {"role_key": "parity_custom", "debug": False}
    session.save()
    response = client.get(reverse("members:biography_view", args=[member.pk]))
    assert response.status_code == 200
    assert not Biography.objects.filter(member=member).exists()


def test_preview_blocks_database_writes_hidden_in_get_handlers(role, member):
    from django.core.exceptions import PermissionDenied
    from django.db import transaction

    from members.role_preview import RolePreviewMiddleware

    actor = Member.objects.create_superuser(
        username="preview-write-actor", password="pass"
    )
    request = RequestFactory().get("/a-get-handler/")
    request.user = actor
    request.session = {"role_preview": {"role_key": "parity_custom", "debug": False}}

    def writes_during_get(request):
        Member.objects.filter(pk=member.pk).update(first_name="Unexpected write")

    with pytest.raises(PermissionDenied, match="database write"), transaction.atomic():
        RolePreviewMiddleware(writes_during_get)(request)
    member.refresh_from_db()
    assert member.first_name != "Unexpected write"
    assert request.user is actor


def test_notification_owner_can_still_dismiss_with_post(client, member):
    notification = Notification.objects.create(user=member, message="Dismiss with POST")
    client.force_login(member)
    response = client.post(reverse("dismiss_notification", args=[notification.pk]))
    assert response.status_code == 302
    notification.refresh_from_db()
    assert notification.dismissed


def test_legacy_staff_retains_roster_message_and_written_test_capabilities(
    client, member
):
    from knowledgetest.views import VIEW_RECENT_TESTS, _has_written_test_capability
    from members.context_processors import authorization

    member.is_staff = True
    member.save()
    client.force_login(member)
    response = client.get(reverse("duty_roster:edit_roster_message"))
    assert response.status_code == 200
    request = RequestFactory().get("/")
    request.user = member
    assert authorization(request)["role_access"]["roster_message"]
    assert _has_written_test_capability(member, VIEW_RECENT_TESTS)


@pytest.mark.parametrize(
    "access,expected_status", [("staff", 200), ("capability", 200), ("ordinary", 403)]
)
def test_written_test_review_keeps_staff_and_explicit_capability_access(
    client, member, access, expected_status
):
    from knowledgetest.models import WrittenTestTemplate

    if access == "staff":
        member.is_staff = True
        member.save()
    elif access == "capability":
        grant(member, "knowledgetest.view_recent_written_tests")
    student = Member.objects.create_user(
        username="review-parity-student", membership_status=member.membership_status
    )
    template = WrittenTestTemplate.objects.create(name="Review parity")
    client.force_login(member)

    response = client.get(
        reverse("knowledgetest:quiz-review", args=[template.pk, student.pk])
    )

    assert response.status_code == expected_status


def test_status_rename_keeps_member_identity_and_later_revocation(
    member, status, role, django_capture_on_commit_callbacks
):
    mapping = MembershipStatusRoleMapping.objects.create(
        membership_status=status, role=role
    )
    apply(member)
    original_key = status.key
    with django_capture_on_commit_callbacks(execute=True):
        status.name = "Parity Renamed"
        status.save()
    member.refresh_from_db()
    assert member.membership_status == status.name
    assert status.key == original_key
    with django_capture_on_commit_callbacks(execute=True):
        mapping.enabled = False
        mapping.save()
    assert not member.groups.filter(pk=role.pk).exists()
