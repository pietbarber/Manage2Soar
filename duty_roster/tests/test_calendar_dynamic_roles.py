from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, DutyAssignmentRole, DutyRoleDefinition
from members.models import Member
from siteconfig.models import MembershipStatus, SiteConfiguration


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(username):
    return Member.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        email=f"{username}@example.com",
    )


@pytest.mark.django_db
def test_calendar_day_modal_shows_dynamic_non_legacy_role_assignments(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_modal_viewer")
    dynamic_member = _make_member("dynamic_modal_assigned")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="line_runner",
        display_name="Line Runner",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=7)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="line_runner",
        member=dynamic_member,
        role_definition=role_definition,
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:calendar_day_detail",
            kwargs={
                "year": duty_date.year,
                "month": duty_date.month,
                "day": duty_date.day,
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Line Runner" in content
    assert dynamic_member.full_display_name in content


@pytest.mark.django_db
def test_calendar_day_modal_dynamic_role_uses_legacy_terminology_label(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_modal_viewer_label")
    dynamic_member = _make_member("dynamic_modal_assigned_label")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
        towpilot_title="Tow Captain",
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="am_tow",
        display_name="AM Tow",
        legacy_role_key="towpilot",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=8)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="am_tow",
        member=dynamic_member,
        role_definition=role_definition,
        legacy_role_key="towpilot",
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:calendar_day_detail",
            kwargs={
                "year": duty_date.year,
                "month": duty_date.month,
                "day": duty_date.day,
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Tow Captain" in content
    assert dynamic_member.full_display_name in content
