from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture(autouse=True)
def clear_cache():
    """Avoid cross-test bleed from cached SiteConfiguration values."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_calendar_renders_compact_role_icons_markup(client):
    """Calendar grid should include compact role icon markup for mobile mode."""
    day = date.today() + timedelta(days=7)

    viewer = Member.objects.create_user(
        username="viewer",
        email="viewer@example.com",
        password="password",
        membership_status="Full Member",
    )
    instructor = Member.objects.create_user(
        username="inst",
        email="inst@example.com",
        password="password",
        membership_status="Full Member",
        instructor=True,
    )
    towpilot = Member.objects.create_user(
        username="tow",
        email="tow@example.com",
        password="password",
        membership_status="Full Member",
        towpilot=True,
    )

    DutyAssignment.objects.create(
        date=day,
        instructor=instructor,
        tow_pilot=towpilot,
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "calendar-role-icons" in content
    assert "Instructor assigned" in content
    assert "Tow pilot assigned" in content


@pytest.mark.django_db
def test_calendar_renders_compact_surge_alert_icon_markup(client):
    """Calendar grid should include compact alert icon markup for surge days."""
    day = date.today() + timedelta(days=10)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instruction_surge_threshold=2,
    )

    viewer = Member.objects.create_user(
        username="viewer2",
        email="viewer2@example.com",
        password="password",
        membership_status="Full Member",
    )
    student_one = Member.objects.create_user(
        username="student1",
        email="student1@example.com",
        password="password",
        membership_status="Full Member",
    )
    student_two = Member.objects.create_user(
        username="student2",
        email="student2@example.com",
        password="password",
        membership_status="Full Member",
    )

    assignment = DutyAssignment.objects.create(date=day)
    InstructionSlot.objects.create(assignment=assignment, student=student_one)
    InstructionSlot.objects.create(assignment=assignment, student=student_two)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "calendar-alert-icon" in content
    assert "High demand alert" in content


@pytest.mark.django_db
def test_agenda_quick_actions_show_disabled_plan_to_fly_when_instruction_exists(client):
    day = date.today() + timedelta(days=6)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
    )

    viewer = Member.objects.create_user(
        username="agenda_viewer",
        email="agenda_viewer@example.com",
        password="password",
        membership_status="Full Member",
    )
    instructor = Member.objects.create_user(
        username="agenda_inst",
        email="agenda_inst@example.com",
        password="password",
        membership_status="Full Member",
        instructor=True,
    )

    assignment = DutyAssignment.objects.create(date=day, instructor=instructor)
    InstructionSlot.objects.create(assignment=assignment, student=viewer)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
        + "?view=agenda"
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Plan to Fly" in content
    assert "You already requested instruction for this day." in content
    assert "Review Student Requests" not in content


@pytest.mark.django_db
def test_agenda_quick_actions_show_reservation_disabled_reason_when_feature_off(client):
    day = date.today() + timedelta(days=8)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        allow_glider_reservations=False,
    )

    viewer = Member.objects.create_user(
        username="reserve_viewer",
        email="reserve_viewer@example.com",
        password="password",
        membership_status="Full Member",
    )

    DutyAssignment.objects.create(date=day)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
        + "?view=agenda"
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Reserve a Glider" in content
    assert "Glider reservations are currently disabled." in content


@pytest.mark.django_db
def test_agenda_quick_actions_open_modal_panel_urls(client):
    day = date.today() + timedelta(days=5)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        allow_glider_reservations=False,
    )

    viewer = Member.objects.create_user(
        username="agenda_modal_viewer",
        email="agenda_modal_viewer@example.com",
        password="password",
        membership_status="Full Member",
    )
    instructor = Member.objects.create_user(
        username="agenda_modal_inst",
        email="agenda_modal_inst@example.com",
        password="password",
        membership_status="Full Member",
        instructor=True,
    )

    DutyAssignment.objects.create(date=day, instructor=instructor)

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
        + "?view=agenda"
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "open_panel=plan_to_fly" in content
    assert "open_panel=request_instruction" in content
