from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from members.models import Member
from siteconfig.models import SiteConfiguration


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
