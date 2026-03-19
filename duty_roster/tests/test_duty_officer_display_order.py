from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment
from members.models import Member
from siteconfig.models import MembershipStatus


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
def test_calendar_day_modal_orders_do_ado_before_surge_roles(client):
    _ensure_full_member_status()

    viewer = _make_member("duty_modal_viewer")
    instructor = _make_member("duty_modal_instructor")
    tow = _make_member("duty_modal_tow")
    do_member = _make_member("duty_modal_do")
    ado_member = _make_member("duty_modal_ado")
    surge_instructor = _make_member("duty_modal_surge_instructor")
    surge_tow = _make_member("duty_modal_surge_tow")

    target_day = date.today() + timedelta(days=7)
    assignment = DutyAssignment.objects.create(
        date=target_day,
        instructor=instructor,
        tow_pilot=tow,
        duty_officer=do_member,
        assistant_duty_officer=ado_member,
        surge_instructor=surge_instructor,
        surge_tow_pilot=surge_tow,
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:calendar_day_detail",
            kwargs={
                "year": assignment.date.year,
                "month": assignment.date.month,
                "day": assignment.date.day,
            },
        )
    )

    assert response.status_code == 200
    content = response.content.decode()

    do_idx = content.index("Duty Officer")
    ado_idx = content.index("Assistant DO")
    surge_instructor_idx = content.index("Surge Instructor")
    surge_tow_idx = content.index("Surge Tow Pilot")

    assert do_idx < ado_idx < surge_instructor_idx < surge_tow_idx


@pytest.mark.django_db
def test_calendar_agenda_shows_bootstrap_icons_for_do_and_ado(client):
    _ensure_full_member_status()

    viewer = _make_member("duty_agenda_viewer")
    do_member = _make_member("duty_agenda_do")
    ado_member = _make_member("duty_agenda_ado")

    target_day = date.today() + timedelta(days=10)
    DutyAssignment.objects.create(
        date=target_day,
        duty_officer=do_member,
        assistant_duty_officer=ado_member,
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": target_day.year, "month": target_day.month},
        )
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "bi bi-clipboard-check" in content
    assert "bi bi-person-badge" in content
