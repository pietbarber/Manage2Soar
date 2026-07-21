from datetime import date, time, timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse

from duty_roster.models import DutyAssignment, GliderReservation, InstructionSlot
from logsheet.models import Glider
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
def test_calendar_does_not_render_surge_alert_icon_markup(client):
    """Calendar grid should not render surge alert icon markup for surge days."""
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
    assert "High demand alert" not in content
    assert "HIGH INSTRUCTION DEMAND" not in content
    assert "HIGH TOW DEMAND" not in content


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
def test_agenda_shows_confirmed_reservation_aircraft_member_and_times(client):
    day = date.today() + timedelta(days=8)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        allow_glider_reservations=True,
    )
    viewer = Member.objects.create_user(
        username="agenda_reservation_viewer",
        email="agenda_reservation_viewer@example.com",
        password="password",
        membership_status="Full Member",
    )
    reserver = Member.objects.create_user(
        username="agenda_reserver",
        email="agenda_reserver@example.com",
        password="password",
        first_name="Agenda",
        last_name="Pilot",
        membership_status="Full Member",
    )
    cancelled_reserver = Member.objects.create_user(
        username="cancelled_agenda_reserver",
        email="cancelled_agenda_reserver@example.com",
        password="password",
        first_name="Cancelled",
        last_name="Pilot",
        membership_status="Full Member",
    )
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK 21",
        n_number="N321AG",
        competition_number="AGD",
        seats=2,
        is_active=True,
        club_owned=True,
    )
    second_glider = Glider.objects.create(
        make="Schempp-Hirth",
        model="Duo Discus",
        n_number="N322AG",
        competition_number="AG2",
        seats=2,
        is_active=True,
        club_owned=True,
    )
    afternoon_glider = Glider.objects.create(
        make="Schleicher",
        model="ASW 28",
        n_number="N323AG",
        competition_number="AG3",
        seats=1,
        is_active=True,
        club_owned=True,
    )
    DutyAssignment.objects.create(date=day)
    GliderReservation.objects.create(
        member=reserver,
        glider=glider,
        date=day,
        reservation_type="guest",
        time_preference="specific",
        start_time=time(9, 15),
        end_time=time(11, 45),
        purpose="Guest orientation before the first flight. <script>agendaNoteMarker</script>",
    )
    GliderReservation.objects.create(
        member=reserver,
        glider=second_glider,
        date=day,
        reservation_type="solo",
        time_preference="specific",
        start_time=time(9, 15),
        end_time=time(11, 45),
    )
    GliderReservation.objects.create(
        member=reserver,
        glider=afternoon_glider,
        date=day,
        reservation_type="solo",
        time_preference="afternoon",
    )
    GliderReservation.objects.create(
        member=cancelled_reserver,
        glider=glider,
        date=day,
        reservation_type="solo",
        time_preference="afternoon",
        status="cancelled",
    )

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
    assert "Glider Reservations" in content
    assert "Agenda Pilot" in content
    assert "AGD" in content
    assert "Guest Flying" in content
    assert "9:15" in content
    assert "11:45" in content
    assert "View reservation notes" in content
    assert "Guest orientation before the first flight." in content
    assert "&lt;script&gt;agendaNoteMarker&lt;/script&gt;" in content
    assert "<script>agendaNoteMarker</script>" not in content
    assert "Cancelled Pilot" not in content
    assert "3 reservations" in content
    assert "Glider reservation timetable" in content
    assert "Reserved aircraft" in content
    assert content.count('class="agenda-reservation-period"') == 2
    assert content.count('class="agenda-reservation-aircraft-card"') == 3

    schedule = response.context["agenda_reservation_schedule_by_date"][day]
    assert schedule["count"] == 3
    assert [period["label"] for period in schedule["periods"]] == [
        "Afternoon",
        "9:15 AM–11:45 AM",
    ]
    assert len(schedule["periods"][1]["reservations"]) == 2


@pytest.mark.django_db
def test_agenda_hides_edit_link_for_past_reservations(client):
    day = date.today() - timedelta(days=1)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        allow_glider_reservations=True,
    )
    viewer = Member.objects.create_user(
        username="agenda_edit_owner",
        email="agenda_edit_owner@example.com",
        password="password",
        membership_status="Full Member",
    )
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK 21",
        n_number="N324AG",
        competition_number="AG4",
        seats=2,
        is_active=True,
        club_owned=True,
    )
    DutyAssignment.objects.create(date=day)
    reservation = GliderReservation.objects.create(
        member=viewer,
        glider=glider,
        date=day,
        reservation_type="solo",
        time_preference="morning",
    )

    client.force_login(viewer)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
        + "?view=agenda"
    )

    assert response.status_code == 200
    assert reverse(
        "duty_roster:reservation_edit", args=[reservation.pk]
    ) not in response.content.decode("utf-8")


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


@pytest.mark.django_db
def test_agenda_review_student_requests_disabled_for_inactive_instructor(client):
    day = date.today() + timedelta(days=5)

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
    )

    inactive_instructor = Member.objects.create_user(
        username="inactive_instructor",
        email="inactive_instructor@example.com",
        password="password",
        membership_status="Full Member",
        instructor=True,
    )
    Member.objects.filter(pk=inactive_instructor.pk).update(
        membership_status="Inactive",
        is_active=True,
    )
    inactive_instructor.refresh_from_db()

    DutyAssignment.objects.create(date=day)

    client.force_login(inactive_instructor)
    response = client.get(
        reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": day.year, "month": day.month},
        )
        + "?view=agenda"
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Review Student Requests" in content
    assert "Active membership is required." in content
