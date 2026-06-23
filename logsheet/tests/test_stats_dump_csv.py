from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from logsheet.models import Airfield, Flight, Glider, Logsheet
from members.models import Member


@pytest.mark.django_db
def test_stats_dump_csv_requires_stats_monger_permission(client):
    user = Member.objects.create_user(
        username="no_stats_access",
        password="pass",
        membership_status="Full Member",
        stats_monger=False,
    )
    client.force_login(user)

    resp = client.get(reverse("logsheet:stats_dump_csv"))

    assert resp.status_code == 403


@pytest.mark.django_db
def test_stats_dump_csv_includes_expected_columns_and_data(client):
    creator = Member.objects.create_user(
        username="stats_owner",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
        first_name="Stats",
        last_name="Owner",
    )
    pilot = Member.objects.create_user(
        username="pilot_member",
        password="pass",
        membership_status="Full Member",
        first_name="Pilot",
        last_name="One",
    )
    passenger = Member.objects.create_user(
        username="passenger_member",
        password="pass",
        membership_status="Full Member",
        first_name="Passenger",
        last_name="Two",
    )
    instructor = Member.objects.create_user(
        username="instructor_member",
        password="pass",
        membership_status="Full Member",
        first_name="Instructor",
        last_name="Three",
    )
    towpilot = Member.objects.create_user(
        username="towpilot_member",
        password="pass",
        membership_status="Full Member",
        first_name="Tow",
        last_name="Pilot",
    )

    airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N123AA",
        rental_rate=Decimal("45.00"),
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today() - timedelta(days=1),
        airfield=airfield,
        created_by=creator,
        finalized=False,
    )

    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        passenger=passenger,
        instructor=instructor,
        tow_pilot=towpilot,
        glider=glider,
        flight_type="Dual",
        launch_time=time(10, 0, 0),
        landing_time=time(10, 20, 0),
        release_altitude=2500,
    )

    client.force_login(creator)
    resp = client.get(reverse("logsheet:stats_dump_csv"))

    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    assert 'attachment; filename="stats_dump_' in resp["Content-Disposition"]

    content = b"".join(resp.streaming_content).decode("utf-8")
    lines = [line for line in content.splitlines() if line.strip()]

    assert lines
    assert (
        lines[0]
        == "flight_tracking_id,flight_date,pilot,passenger,glider,instructor,towpilot,flight_type,takeoff_time,landing_time,flight_time,release_altitude,flight_cost,tow_cost,total_cost,field"
    )

    assert "Pilot One" in content
    assert "Passenger Two" in content
    assert "Instructor Three" in content
    assert "Tow Pilot" in content
    assert "KFRR" in content


@pytest.mark.django_db
def test_stats_dump_csv_prefers_flight_airfield_when_different(client):
    creator = Member.objects.create_user(
        username="stats_owner_airfield",
        password="pass",
        membership_status="Full Member",
        stats_monger=True,
    )
    pilot = Member.objects.create_user(
        username="pilot_airfield",
        password="pass",
        membership_status="Full Member",
        first_name="Pilot",
        last_name="Airfield",
    )

    logsheet_airfield = Airfield.objects.create(
        identifier="KLS1", name="Logsheet Field"
    )
    flight_airfield = Airfield.objects.create(identifier="KFL1", name="Flight Field")
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N124AA",
        rental_rate=Decimal("45.00"),
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today() - timedelta(days=1),
        airfield=logsheet_airfield,
        created_by=creator,
        finalized=False,
    )

    Flight.objects.create(
        logsheet=logsheet,
        airfield=flight_airfield,
        pilot=pilot,
        glider=glider,
        flight_type="Dual",
        launch_time=time(10, 0, 0),
        landing_time=time(10, 20, 0),
        release_altitude=2000,
    )

    client.force_login(creator)
    resp = client.get(reverse("logsheet:stats_dump_csv"))

    assert resp.status_code == 200
    content = b"".join(resp.streaming_content).decode("utf-8")
    assert "KFL1" in content
