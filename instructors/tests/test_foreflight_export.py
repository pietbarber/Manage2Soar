"""Tests for the ForeFlight logbook import export (Issue #921)."""

import csv
import io
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from django.urls import reverse

from instructors import foreflight_export as ff
from instructors.models import GroundInstruction
from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member
from siteconfig.models import MembershipStatus

TEMPLATE_PATH = (
    Path(__file__).parent / "fixtures" / "foreflight" / "logbook_template_faa.csv"
)
EXPORT_URL = "instructors:member_logbook_export_foreflight"


def _make_member(username, **kwargs):
    MembershipStatus.objects.update_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    return Member.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        email=f"{username}@example.com",
        first_name=username.split("_")[1].title(),
        last_name=username.split("_")[-1].title(),
        **kwargs,
    )


def _setup(pilot, log_date=date(2026, 5, 23), n_number="N1FF"):
    airfield, _ = Airfield.objects.get_or_create(
        identifier="KFFX", defaults={"name": "FF Field"}
    )
    glider = Glider.objects.create(
        n_number=n_number,
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=log_date, airfield=airfield, created_by=pilot
    )
    return glider, logsheet


def _export(client, user):
    client.force_login(user)
    response = client.get(reverse(EXPORT_URL))
    assert response.status_code == 200
    return response.content.decode()


def _all_rows(content):
    return list(csv.reader(io.StringIO(content, newline="")))


def _flight_rows(content):
    rows = _all_rows(content)
    marker = next(i for i, r in enumerate(rows) if r[0] == "Flights Table")
    header = rows[marker + 2]
    return [dict(zip(header, r)) for r in rows[marker + 3 :]]


def _aircraft_rows(content):
    rows = _all_rows(content)
    header_idx = next(i for i, r in enumerate(rows) if r[0] == "AircraftID")
    marker = next(i for i, r in enumerate(rows) if r[0] == "Flights Table")
    header = rows[header_idx]
    return [dict(zip(header, r)) for r in rows[header_idx + 1 : marker] if any(r)]


@pytest.mark.django_db
def test_structure_matches_reference_template(client):
    pilot = _make_member("ff_struct_pilot")
    glider, logsheet = _setup(pilot)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 20),
    )

    content = _export(client, pilot)
    exported = _all_rows(content)
    with open(TEMPLATE_PATH, newline="") as fh:
        template = list(csv.reader(fh))

    assert all(len(r) == ff.ROW_WIDTH for r in exported)
    assert "\r\n" in content

    # Preamble, Aircraft Table marker, datatype row and header row.
    assert exported[:5] == template[:5]

    # Flights Table marker, datatype row and header row; only the two custom
    # fields we name differ from the template placeholders.
    marker = next(i for i, r in enumerate(exported) if r[0] == "Flights Table")
    assert exported[marker] == template[6]
    assert exported[marker + 1] == template[7]
    expected_header = list(template[8])
    expected_header[expected_header.index("[Text]CustomFieldName")] = (
        ff.CUSTOM_LAUNCH_METHOD
    )
    expected_header[expected_header.index("[Numeric]CustomFieldName")] = (
        ff.CUSTOM_RELEASE_ALTITUDE
    )
    assert exported[marker + 2] == expected_header


@pytest.mark.django_db
def test_glider_flight_row_values(client):
    pilot = _make_member("ff_values_pilot")
    instructor = _make_member("ff_values_instructor", instructor=True)
    glider, logsheet = _setup(pilot)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        release_altitude=3000,
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    content = _export(client, pilot)
    (row,) = _flight_rows(content)
    assert row["AircraftID"] == "N1FF"
    assert row["TimeOut"] == ""
    assert row["TimeOff"] == "10:00"
    assert row["TimeOn"] == "10:25"
    assert row["TimeIn"] == ""
    assert row["TotalTime"] == "0.42"
    assert row["DualReceived"] == "0.42"
    assert row["Takeoff Day"] == "1"
    assert row["Landing Full-Stop Day"] == "1"
    assert row["InstructorName"] == instructor.full_display_name
    assert row[ff.CUSTOM_LAUNCH_METHOD] == "Aerotow"
    assert row[ff.CUSTOM_RELEASE_ALTITUDE] == "3000"

    (aircraft,) = _aircraft_rows(content)
    assert aircraft["AircraftID"] == "N1FF"
    assert aircraft["equipType"] == "aircraft"
    assert aircraft["TypeCode"] == ""
    assert aircraft["GearType"] == ""
    # Glider has no engine metadata (could be a motor glider), so this stays blank.
    assert aircraft["EngineType"] == ""
    assert aircraft["Category/Class"] == "Glider"
    assert aircraft["complexAircraft"] == ""


@pytest.mark.django_db
def test_very_short_flight_keeps_hundredths_precision(client):
    pilot = _make_member("ff_short_pilot")
    glider, logsheet = _setup(pilot)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 1),
    )

    (row,) = _flight_rows(_export(client, pilot))
    assert row["TotalTime"] == "0.02"


@pytest.mark.django_db
def test_instruction_given_maps_student_to_person_not_instructor_name(client):
    student = _make_member("ff_given_student")
    instructor = _make_member("ff_given_instructor", instructor=True)
    glider, logsheet = _setup(student)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=student,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    (row,) = _flight_rows(_export(client, instructor))
    assert row["DualGiven"] == "0.42"
    assert row["DualReceived"] == ""
    assert row["InstructorName"] == ""
    assert row["Person1"] == f"{student.full_display_name};Student;;"


@pytest.mark.django_db
def test_passenger_flight_is_kept_without_time_or_landings(client):
    member = _make_member("ff_passenger_member")
    pilot = _make_member("ff_passenger_pilot")
    glider, logsheet = _setup(pilot)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        passenger=member,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    content = _export(client, member)
    (row,) = _flight_rows(content)
    assert row["AircraftID"] == "N1FF"
    assert row["TotalTime"] == ""
    for column in ("PIC", "Solo", "DualReceived", "DualGiven"):
        assert row[column] == ""
    assert row["Takeoff Day"] == ""
    assert row["Landing Full-Stop Day"] == ""
    assert row["PilotComments"].startswith("Passenger (logbook owner not pilot)")
    assert "0:25 aloft" in row["PilotComments"]
    assert row["Person1"] == f"{pilot.full_display_name};PIC;;"
    assert [a["AircraftID"] for a in _aircraft_rows(content)] == ["N1FF"]


@pytest.mark.django_db
def test_legacy_passenger_name_fallback_is_exported(client):
    pilot = _make_member("ff_legacy_pilot")
    glider, logsheet = _setup(pilot)
    # No passenger member, no plain passenger_name; only the legacy fallback.
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        legacy_passenger_name="Rider From Legacy Import",
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    (row,) = _flight_rows(_export(client, pilot))
    # No instructor on the flight, so the passenger occupies Person1.
    assert row["Person1"] == "Rider From Legacy Import;Passenger;;"


@pytest.mark.django_db
def test_ground_sessions_received_given_and_zero_duration_are_kept(client):
    student = _make_member("ff_ground_student")
    instructor = _make_member("ff_ground_instructor", instructor=True)
    GroundInstruction.objects.create(
        student=student,
        instructor=instructor,
        date=date(2026, 5, 1),
        duration=timedelta(minutes=90),
        location="Clubhouse",
        notes="<p>Covered <b>14 CFR 91.161</b> recency of experience.</p>",
    )
    GroundInstruction.objects.create(
        student=student,
        instructor=instructor,
        date=date(2026, 5, 2),
        duration=timedelta(0),
    )

    received = _flight_rows(_export(client, student))
    assert [r["GroundTraining"] for r in received] == ["1.50", "0.00"]
    for row in received:
        assert row["AircraftID"] == ""
        assert row["From"] == ""
        assert row["TotalTime"] == ""
        assert row["GroundTrainingGiven"] == ""
        assert row["InstructorName"] == instructor.full_display_name
    # Session notes (HTMLField) are exported as plain text, tags stripped.
    assert received[0]["PilotComments"] == (
        "Ground instruction (Clubhouse). Covered 14 CFR 91.161 recency of experience."
    )
    # The zero-duration session has no notes, so its comment is unchanged.
    assert received[1]["PilotComments"] == "Ground instruction"

    given = _flight_rows(_export(client, instructor))
    assert [r["GroundTrainingGiven"] for r in given] == ["1.50", "0.00"]
    for row in given:
        assert row["GroundTraining"] == ""
        assert row["InstructorName"] == ""
        assert row["Person1"] == f"{student.full_display_name};Student;;"


@pytest.mark.django_db
def test_ground_session_notes_with_multiple_paragraphs_are_preserved(client):
    student = _make_member("ff_ground_multi")
    instructor = _make_member("ff_ground_multi_inst", instructor=True)
    GroundInstruction.objects.create(
        student=student,
        instructor=instructor,
        date=date(2026, 5, 3),
        duration=timedelta(minutes=45),
        notes="<p>First &amp; second</p><p>Third</p>",
    )

    received = _flight_rows(_export(client, student))
    comment = received[0]["PilotComments"]
    # Paragraphs must not be merged into a single word, and entities decoded.
    assert "First & second" in comment
    assert "Third" in comment
    assert "FirstThird" not in comment


@pytest.mark.django_db
def test_tow_day_with_two_towplanes_yields_one_row_per_towplane(client):
    tow_pilot = _make_member("ff_tow_pilot", towpilot=True)
    glider_pilot = _make_member("ff_tow_glider_pilot")
    glider, logsheet = _setup(tow_pilot)
    plane_a = Towplane.objects.create(n_number="N1TA", make="Piper", model="PA-25")
    plane_b = Towplane.objects.create(n_number="N2TB", make="Piper", model="PA-25")
    for plane, count in ((plane_a, 2), (plane_b, 1)):
        for i in range(count):
            Flight.objects.create(
                logsheet=logsheet,
                pilot=glider_pilot,
                tow_pilot=tow_pilot,
                towplane=plane,
                glider=glider,
                launch_method="tow",
                launch_time=time(10 + i, 0),
                landing_time=time(10 + i, 20),
            )

    content = _export(client, tow_pilot)
    rows = [
        r
        for r in _flight_rows(content)
        if r["PilotComments"].startswith("Tow pilot daily summary")
    ]
    assert [(r["AircraftID"], r["Takeoff Day"], r["PIC"]) for r in rows] == [
        ("N1TA", "2", "0.20"),
        ("N2TB", "1", "0.10"),
    ]
    assert {a["AircraftID"] for a in _aircraft_rows(content)} == {"N1TA", "N2TB"}


@pytest.mark.django_db
def test_free_text_is_quoted_and_formula_neutralized(client):
    pilot = _make_member("ff_text_pilot")
    glider, logsheet = _setup(pilot)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 20),
        notes='Line one, "quoted"\nLine two \u00e9\u00fc',
        guest_instructor_name="=CMD()",
    )

    (row,) = _flight_rows(_export(client, pilot))
    assert row["PilotComments"] == 'Line one, "quoted"\nLine two \u00e9\u00fc'
    assert row["InstructorName"] == "'=CMD()"
