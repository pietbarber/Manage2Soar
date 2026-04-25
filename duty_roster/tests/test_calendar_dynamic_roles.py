from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, DutyAssignmentRole, DutyRoleDefinition
from duty_roster.utils.role_resolution import RoleResolutionService
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


@pytest.mark.django_db
def test_calendar_month_table_shows_dynamic_role_badge(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_table_viewer")
    dynamic_member = _make_member("dynamic_table_assigned")

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

    duty_date = date.today() + timedelta(days=9)
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
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Line Runner:" in content
    assert dynamic_member.last_name in content


@pytest.mark.django_db
def test_calendar_month_dynamic_roles_do_not_call_get_member_for_role_fallback(
    client, monkeypatch
):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_table_viewer_no_fallback")
    dynamic_member = _make_member("dynamic_table_assigned_no_fallback")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="launch_coord",
        display_name="Launch Coordinator",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=14)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="launch_coord",
        member=dynamic_member,
        role_definition=role_definition,
    )

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("get_member_for_role should not be used for dynamic rows")

    monkeypatch.setattr(DutyAssignment, "get_member_for_role", _raise_if_called)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_calendar_month_dynamic_roles_do_not_call_get_role_label_per_key(
    client, monkeypatch
):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_table_viewer_no_role_label_calls")
    dynamic_member = _make_member("dynamic_table_assigned_no_role_label_calls")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="launch_coord",
        display_name="Launch Coordinator",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=15)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="launch_coord",
        member=dynamic_member,
        role_definition=role_definition,
    )

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("get_role_label should not be called for month labels")

    monkeypatch.setattr(RoleResolutionService, "get_role_label", _raise_if_called)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200


@pytest.mark.django_db
def test_calendar_agenda_shows_dynamic_role_card(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_agenda_viewer")
    dynamic_member = _make_member("dynamic_agenda_assigned")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="launch_coord",
        display_name="Launch Coordinator",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=10)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="launch_coord",
        member=dynamic_member,
        role_definition=role_definition,
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Launch Coordinator" in content
    assert dynamic_member.full_display_name in content


@pytest.mark.django_db
def test_calendar_month_mapped_dynamic_tow_role_uses_display_name_and_tow_badge(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_table_tow_styling_viewer")
    dynamic_member = _make_member("dynamic_table_tow_styling_assigned")

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

    duty_date = date.today() + timedelta(days=16)
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
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "AM Tow:" in content
    assert "badge-tow-pilot" in content
    assert "bi bi-airplane" in content


@pytest.mark.django_db
def test_calendar_agenda_mapped_dynamic_tow_role_uses_display_name_and_tow_card(client):
    _ensure_full_member_status()

    viewer = _make_member("dynamic_agenda_tow_styling_viewer")
    dynamic_member = _make_member("dynamic_agenda_tow_styling_assigned")

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

    duty_date = date.today() + timedelta(days=17)
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
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "AM Tow" in content
    assert "bg-danger bg-opacity-10 border border-danger" in content
    assert "bi bi-airplane me-2" in content


@pytest.mark.django_db
def test_calendar_day_modal_shows_dynamic_role_assignment_card_for_assigned_member(
    client,
):
    _ensure_full_member_status()

    dynamic_member = _make_member("dynamic_modal_self_assigned")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="wing_runner",
        display_name="Wing Runner",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=11)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="wing_runner",
        member=dynamic_member,
        role_definition=role_definition,
    )

    client.force_login(dynamic_member)
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
    assert "Your Dynamic Role Assignments" in content
    assert "Wing Runner" in content


@pytest.mark.django_db
def test_calendar_day_modal_mapped_dynamic_role_shows_coverage_link(client):
    _ensure_full_member_status()

    dynamic_member = _make_member("dynamic_modal_mapped_assigned")

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

    duty_date = date.today() + timedelta(days=12)
    assignment = DutyAssignment.objects.create(
        date=duty_date,
        tow_pilot=dynamic_member,
    )
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="am_tow",
        member=dynamic_member,
        role_definition=role_definition,
        legacy_role_key="towpilot",
    )

    client.force_login(dynamic_member)
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
    expected_url = reverse(
        "duty_roster:create_swap_request",
        kwargs={
            "year": duty_date.year,
            "month": duty_date.month,
            "day": duty_date.day,
            "role": "TOW",
        },
    )
    assert "Tow Captain" in content
    assert expected_url in content


@pytest.mark.django_db
def test_calendar_day_modal_nonlegacy_dynamic_role_shows_dynamic_coverage_link(client):
    _ensure_full_member_status()

    dynamic_member = _make_member("dynamic_modal_nonlegacy_assigned")

    site_config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        enable_dynamic_duty_roles=True,
    )
    role_definition = DutyRoleDefinition.objects.create(
        site_configuration=site_config,
        key="launch_coord",
        display_name="Launch Coordinator",
        is_active=True,
        sort_order=10,
    )

    duty_date = date.today() + timedelta(days=13)
    assignment = DutyAssignment.objects.create(date=duty_date)
    DutyAssignmentRole.objects.create(
        assignment=assignment,
        role_key="launch_coord",
        member=dynamic_member,
        role_definition=role_definition,
    )

    client.force_login(dynamic_member)
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
    expected_dynamic_url = reverse(
        "duty_roster:create_swap_request",
        kwargs={
            "year": duty_date.year,
            "month": duty_date.month,
            "day": duty_date.day,
            "role": "DYNAMIC",
        },
    )
    assert "Launch Coordinator" in content
    assert f"{expected_dynamic_url}?dynamic_role_key=launch_coord" in content
