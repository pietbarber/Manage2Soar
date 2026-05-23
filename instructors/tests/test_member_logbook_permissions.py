import csv
import io
import re
from datetime import date, time, timedelta

import pytest
from django.urls import reverse

from instructors.models import (
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    TrainingLesson,
)
from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member
from siteconfig.models import MembershipStatus


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(username, instructor=False, glider_rating="student"):
    return Member.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        glider_rating=glider_rating,
        email=f"{username}@example.com",
    )


def _parse_foreflight_flights_rows(csv_text):
    lines = csv_text.splitlines()
    flight_header = "Date,AircraftID,From,To,Route,TimeOut,TimeOff,TimeOn,TimeIn"
    header_idx = next(
        i for i, line in enumerate(lines) if line.startswith(flight_header)
    )
    return list(csv.DictReader(io.StringIO("\n".join(lines[header_idx:]))))


def _parse_foreflight_aircraft_rows(csv_text):
    lines = csv_text.splitlines()
    aircraft_header = "AircraftID,EquipmentType,TypeCode,Year,Make,Model,Category,Class"
    header_idx = next(
        i for i, line in enumerate(lines) if line.startswith(aircraft_header)
    )
    flights_table_idx = next(
        i for i, line in enumerate(lines) if line.startswith("Flights Table")
    )
    aircraft_section = "\n".join(lines[header_idx:flights_table_idx]).strip()
    return list(csv.DictReader(io.StringIO(aircraft_section)))


@pytest.mark.django_db
def test_member_can_view_own_logbook(client):
    _ensure_full_member_status()
    student = _make_member("logbook_self")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_rated_pilot_logs_dual_and_pic_for_instructor_flight(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_rated_dual", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2024, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    instructor = _make_member(
        "logbook_rated_dual_instructor", instructor=True, glider_rating="rated"
    )

    airfield = Airfield.objects.create(name="Front Royal", identifier="KFRR")
    glider = Glider.objects.create(
        n_number="N762A",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 6, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    row = response.context["pages"][0]["rows"][0]
    assert row["dual_received_m"] == 25
    assert row["pic_m"] == 25


@pytest.mark.django_db
def test_pre_rating_instructor_flight_logs_dual_not_pic(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_prerating_dual", glider_rating="student")
    pilot.private_glider_checkride_date = date(2024, 7, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    instructor = _make_member(
        "logbook_prerating_instructor", instructor=True, glider_rating="rated"
    )

    airfield = Airfield.objects.create(name="Winchester", identifier="KWGO")
    glider = Glider.objects.create(
        n_number="N762B",
        make="Schweizer",
        model="2-33",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 6, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(11, 0),
        landing_time=time(11, 30),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    row = response.context["pages"][0]["rows"][0]
    assert row["dual_received_m"] == 30
    assert row["pic_m"] == 0


@pytest.mark.django_db
def test_logbook_glider_summary_is_all_time_even_on_default_view(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_all_time_summary")
    instructor = _make_member(
        "logbook_all_time_summary_instructor", instructor=True, glider_rating="rated"
    )

    airfield = Airfield.objects.create(name="Summit Point", identifier="KSUM")
    glider = Glider.objects.create(
        n_number="N762C",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )

    old_logsheet = Logsheet.objects.create(
        log_date=date.today() - timedelta(days=365 * 5),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=old_logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 30),
    )

    recent_logsheet = Logsheet.objects.create(
        log_date=date.today() - timedelta(days=10),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=recent_logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 45),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook"))

    assert response.status_code == 200

    pages = response.context["pages"]
    total_rows = sum(len(page["rows"]) for page in pages)
    assert total_rows == 1

    summary_rows = response.context["glider_time_summary"]
    row = next(r for r in summary_rows if r["make_model"] == "Schleicher ASK-21")
    assert row["total"] == "1:15"
    assert row["dual_received"] == "1:15"


@pytest.mark.django_db
def test_guest_instructor_flight_counts_as_dual_and_rated_pic(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_guest_instructor", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2020, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    airfield = Airfield.objects.create(name="Guest Field", identifier="KGST")
    glider = Glider.objects.create(
        n_number="N762G",
        make="DG",
        model="DG-1000",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 5, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 20),
        guest_instructor_name="Guest CFI",
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    row = response.context["pages"][0]["rows"][0]
    assert row["dual_received_m"] == 20
    assert row["pic_m"] == 20
    assert "instruction received" in row["comments"]
    assert "Guest CFI" in row["comments"]

    summary_rows = response.context["glider_time_summary"]
    summary_row = next(r for r in summary_rows if r["make_model"] == "DG DG-1000")
    assert summary_row["dual_received"] == "0:20"
    assert summary_row["pic_summary"] == "0:20"


@pytest.mark.django_db
def test_whitespace_guest_name_falls_back_to_legacy_instructor_name(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_legacy_instructor_fallback", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2020, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    airfield = Airfield.objects.create(name="Legacy Field", identifier="KLGY")
    glider = Glider.objects.create(
        n_number="N762L",
        make="ASK",
        model="21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 5, 2),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 20),
        guest_instructor_name="   ",
        legacy_instructor_name="Legacy CFI",
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    row = response.context["pages"][0]["rows"][0]
    assert row["dual_received_m"] == 20
    assert "instruction received" in row["comments"]
    assert "Legacy CFI" in row["comments"]


@pytest.mark.django_db
def test_private_flights_are_included_in_all_time_summary(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_private_summary", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2020, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    airfield = Airfield.objects.create(name="Private Field", identifier="KPRV")
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 8, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        launch_method="tow",
        launch_time=time(8, 0),
        landing_time=time(8, 25),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    summary_rows = response.context["glider_time_summary"]
    private_row = next(r for r in summary_rows if r["make_model"] == "Private")
    assert private_row["solo"] == "0:25"
    assert private_row["total"] == "0:25"


@pytest.mark.django_db
def test_instructor_can_view_student_logbook(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_instructor", instructor=True)
    student = _make_member("logbook_student")

    client.force_login(instructor)
    response = client.get(
        reverse("instructors:member_logbook_member", args=[student.pk])
    )

    assert response.status_code == 200
    assert response.context["member"].pk == student.pk


@pytest.mark.django_db
def test_non_instructor_cannot_view_another_members_logbook(client):
    _ensure_full_member_status()
    member_a = _make_member("logbook_member_a")
    member_b = _make_member("logbook_member_b")

    client.force_login(member_a)
    response = client.get(
        reverse("instructors:member_logbook_member", args=[member_b.pk])
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_invalid_member_logbook_returns_404(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_instructor_404", instructor=True)

    client.force_login(instructor)
    response = client.get(reverse("instructors:member_logbook_member", args=[999999]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_member_can_export_own_logbook_csv(client):
    _ensure_full_member_status()
    student = _make_member("logbook_csv_self")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook_export_csv"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_instructor_can_export_student_logbook_csv(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_csv_instructor", instructor=True)
    student = _make_member("logbook_csv_student")

    client.force_login(instructor)
    response = client.get(
        reverse("instructors:member_logbook_export_csv_member", args=[student.pk])
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_non_instructor_cannot_export_another_members_logbook_csv(client):
    _ensure_full_member_status()
    member_a = _make_member("logbook_csv_member_a")
    member_b = _make_member("logbook_csv_member_b")

    client.force_login(member_a)
    response = client.get(
        reverse("instructors:member_logbook_export_csv_member", args=[member_b.pk])
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_csv_export_uses_shared_dual_and_pic_classification(client):
    _ensure_full_member_status()
    pilot = _make_member("logbook_csv_rated_dual", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2020, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    instructor = _make_member(
        "logbook_csv_rated_dual_instructor", instructor=True, glider_rating="rated"
    )
    airfield = Airfield.objects.create(name="CSV Field", identifier="KCSV")
    glider = Glider.objects.create(
        n_number="N762CSV",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 6, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_csv"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert len(rows) == 1
    assert rows[0]["Dual"] == "0:25"
    assert rows[0]["PIC"] == "0:25"
    assert rows[0]["Total"] == "0:25"


@pytest.mark.django_db
def test_instruction_record_shows_logbook_link(client):
    _ensure_full_member_status()
    student = _make_member("instruction_record_logbook_link")

    client.force_login(student)
    response = client.get(
        reverse("instructors:member_instruction_record", args=[student.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("instructors:member_logbook_member", args=[student.pk]) in content


@pytest.mark.django_db
def test_progress_dashboard_dropdown_shows_logbook_link(client):
    _ensure_full_member_status()
    instructor = _make_member(
        "progress_dashboard_instructor", instructor=True, glider_rating="rated"
    )
    student = _make_member("progress_dashboard_student", glider_rating="student")

    client.force_login(instructor)
    response = client.get(reverse("instructors:instructors-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("instructors:member_logbook_member", args=[student.pk]) in content


@pytest.mark.django_db
def test_logbook_training_modal_uses_large_dialog_class(client):
    _ensure_full_member_status()
    student = _make_member("logbook_modal_margin_check")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook"))

    assert response.status_code == 200
    content = response.content.decode()
    modal_match = re.search(
        r'<div[^>]*id="trainingModal"[^>]*>.*?<div[^>]*class="([^"]*modal-dialog[^"]*)"',
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert modal_match is not None
    assert "modal-lg" in modal_match.group(1)


@pytest.mark.django_db
def test_instruction_report_detail_keeps_notes_inside_modal_body(client):
    _ensure_full_member_status()
    student = _make_member("instruction_modal_student")
    instructor = _make_member("instruction_modal_instructor", instructor=True)
    lesson = TrainingLesson.objects.create(
        code="1a",
        title="Preflight",
        description="Test lesson",
    )
    report = InstructionReport.objects.create(
        student=student,
        instructor=instructor,
        report_date=date.today(),
        report_text="<p>Notes paragraph</p>",
    )
    LessonScore.objects.create(report=report, lesson=lesson, score="2")

    client.force_login(student)
    response = client.get(
        reverse("instructors:instruction_report_detail", args=[report.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    modal_body_match = re.search(
        r'<div[^>]*class="[^"]*modal-body[^"]*"[^>]*>(?P<body>.*?)</div>',
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert modal_body_match is not None
    modal_body_inner_html = modal_body_match.group("body")
    # Ensure the notes block is rendered inside the modal-body.
    assert '<div class="cms-content px-1">' in modal_body_inner_html


@pytest.mark.django_db
def test_logbook_signature_renders_on_new_line_for_flight_and_ground(client):
    _ensure_full_member_status()
    student = _make_member("signature_student")
    instructor = Member.objects.create_user(
        username="signature_instructor",
        password="password",
        membership_status="Full Member",
        instructor=True,
        email="signature_instructor@example.com",
        first_name="Brian",
        last_name="Clark",
        pilot_certificate_number="3303513",
    )
    airfield = Airfield.objects.create(name="Front Royal", identifier="KFRR")
    glider = Glider.objects.create(
        make="Schweizer",
        model="2-33",
        n_number="N123AB",
        is_active=True,
    )
    lesson = TrainingLesson.objects.create(
        code="1c",
        title="Cockpit Familiarization",
        description="Test lesson",
    )

    flight_day = date.today()
    logsheet = Logsheet.objects.create(
        log_date=flight_day, airfield=airfield, created_by=student
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=student,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 20),
        duration=timedelta(minutes=20),
    )
    report = InstructionReport.objects.create(
        student=student,
        instructor=instructor,
        report_date=flight_day,
    )
    LessonScore.objects.create(report=report, lesson=lesson, score="2")

    ground = GroundInstruction.objects.create(
        student=student,
        instructor=instructor,
        date=flight_day,
        duration=timedelta(minutes=30),
        location="Briefing room",
    )
    GroundLessonScore.objects.create(session=ground, lesson=lesson, score="2")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    rows = response.context["pages"][0]["rows"]

    flight_row = next((r for r in rows if r.get("flight_id")), None)
    ground_row = next((r for r in rows if r.get("ground_inst_m", 0) > 0), None)

    assert flight_row is not None
    assert ground_row is not None

    assert "<br>/s/" in flight_row["signature_html"]
    assert "3303513CFI" in flight_row["signature_html"]
    assert ", 3303513CFI" not in flight_row["signature_html"]

    assert "<br>/s/" in ground_row["signature_html"]
    assert "3303513CFI" in ground_row["signature_html"]
    assert ", 3303513CFI" not in ground_row["signature_html"]
    assert ground_row["airfield"] == "Briefing room"


@pytest.mark.django_db
def test_logbook_signature_without_lesson_codes_has_no_leading_line_break(client):
    _ensure_full_member_status()
    student = _make_member("signature_no_codes_student")
    instructor = Member.objects.create_user(
        username="signature_no_codes_instructor",
        password="password",
        membership_status="Full Member",
        instructor=True,
        email="signature_no_codes_instructor@example.com",
        first_name="Pat",
        last_name="Lee",
        pilot_certificate_number="112233",
    )
    airfield = Airfield.objects.create(name="Front Royal", identifier="KFRR")
    glider = Glider.objects.create(
        make="Schweizer",
        model="2-33",
        n_number="N321BA",
        is_active=True,
    )

    flight_day = date.today()
    logsheet = Logsheet.objects.create(
        log_date=flight_day, airfield=airfield, created_by=student
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=student,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(11, 0),
        landing_time=time(11, 20),
        duration=timedelta(minutes=20),
    )
    # Intentionally no LessonScore rows on this report.
    InstructionReport.objects.create(
        student=student,
        instructor=instructor,
        report_date=flight_day,
    )

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook") + "?show_all_years=1")

    assert response.status_code == 200
    rows = response.context["pages"][0]["rows"]
    flight_row = next((r for r in rows if r.get("flight_id")), None)
    assert flight_row is not None
    assert "/s/" in flight_row["signature_html"]
    assert not flight_row["signature_html"].startswith("<br>/s/")


@pytest.mark.django_db
def test_member_can_export_own_logbook_foreflight_csv(client):
    _ensure_full_member_status()
    student = _make_member("foreflight_export_self")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "foreflight" in response["Content-Disposition"]


@pytest.mark.django_db
def test_instructor_can_export_student_logbook_foreflight_csv(client):
    _ensure_full_member_status()
    instructor = _make_member("foreflight_export_instructor", instructor=True)
    student = _make_member("foreflight_export_student")

    client.force_login(instructor)
    response = client.get(
        reverse(
            "instructors:member_logbook_export_foreflight_member", args=[student.pk]
        )
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_non_instructor_cannot_export_another_members_logbook_foreflight_csv(client):
    _ensure_full_member_status()
    member_a = _make_member("foreflight_export_member_a")
    member_b = _make_member("foreflight_export_member_b")

    client.force_login(member_a)
    response = client.get(
        reverse(
            "instructors:member_logbook_export_foreflight_member", args=[member_b.pk]
        )
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_foreflight_csv_uses_decimal_hours(client):
    _ensure_full_member_status()
    pilot = _make_member("foreflight_decimal_hours_pilot", glider_rating="rated")
    pilot.private_glider_checkride_date = date(2020, 1, 1)
    pilot.save(update_fields=["private_glider_checkride_date"])

    instructor = _make_member(
        "foreflight_decimal_hours_instructor", instructor=True, glider_rating="rated"
    )
    airfield = Airfield.objects.create(name="Decimal Hours Field", identifier="KDEC")
    glider = Glider.objects.create(
        n_number="N123DEC",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 6, 1),
        airfield=airfield,
        created_by=pilot,
    )
    # 25-minute flight = 0.42 hours (rounded to 2 decimals)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        instructor=instructor,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 25),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")

    content = response.content.decode()
    flight_rows = _parse_foreflight_flights_rows(content)
    assert len(flight_rows) >= 1, "Should have at least one flight row"
    flight_row = flight_rows[0]
    # 25 min = 0.42 hours
    assert float(flight_row["TotalTime"]) == 0.42
    assert float(flight_row["PIC"]) == 0.42


@pytest.mark.django_db
def test_foreflight_csv_has_aircraft_and_flights_sections(client):
    _ensure_full_member_status()
    pilot = _make_member("foreflight_sections_pilot")

    airfield = Airfield.objects.create(name="Section Test Field", identifier="KSEC")
    glider = Glider.objects.create(
        n_number="N456SEC",
        make="Sailplane",
        model="2-33",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 6, 1),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 15),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    content = response.content.decode()
    lines = content.splitlines()

    required_text = (
        "This row is required for importing into ForeFlight. "
        "Do not delete or modify."
    )
    assert lines[0] == f"ForeFlight Logbook Import,{required_text}"
    assert lines[1] == ""
    assert lines[2] == "Aircraft Table"
    assert (
        lines[3]
        == "Text,Text,Text,YYYY,Text,Text,Text,Text,Text,Text,Boolean,Boolean,Boolean,Boolean"
    )

    # Check for aircraft section header
    assert "AircraftID,EquipmentType,TypeCode,Year,Make,Model,Category,Class" in content
    # Check for flights preamble rows before the flights header
    assert "Flights Table" in content
    assert "Decimal or HH:MM" in content
    # Check for flights section header
    assert "Date,AircraftID,From,To,Route,TimeOut,TimeOff,TimeOn,TimeIn" in content
    # Check for aircraft data
    assert "N456SEC" in content
    assert "Sailplane" in content
    assert "2-33" in content
    assert "Glider" in content


@pytest.mark.django_db
def test_foreflight_csv_handles_flight_with_no_glider(client):
    _ensure_full_member_status()
    pilot = _make_member("foreflight_no_glider_pilot")

    airfield = Airfield.objects.create(name="No Glider Field", identifier="KNGL")
    logsheet = Logsheet.objects.create(
        log_date=date(2024, 7, 1),
        airfield=airfield,
        created_by=pilot,
    )
    # Flight with glider=None (e.g. offline sync scenario)
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=None,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 15),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    content = response.content.decode()
    # Flight with no glider should use the placeholder AircraftID
    assert "UNKNOWN-AIRCRAFT" in content
    # A corresponding aircraft row should also be present
    lines = [line for line in content.split("\n") if "UNKNOWN-AIRCRAFT" in line]
    assert (
        len(lines) >= 2
    ), "UNKNOWN-AIRCRAFT should appear in both aircraft and flights sections"


@pytest.mark.django_db
def test_foreflight_csv_uses_logsheet_airfield_when_flight_airfield_missing(client):
    _ensure_full_member_status()
    pilot = _make_member("foreflight_airfield_fallback_pilot")

    logsheet_airfield = Airfield.objects.create(
        name="Fallback Field",
        identifier="KFBK",
    )
    glider = Glider.objects.create(
        n_number="N999FBK",
        make="Schempp-Hirth",
        model="Discus",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2026, 4, 25),
        airfield=logsheet_airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        airfield=None,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 15),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    rows = _parse_foreflight_flights_rows(response.content.decode())

    assert rows
    assert rows[0]["From"] == "KFBK"
    assert rows[0]["To"] == "KFBK"


@pytest.mark.django_db
def test_foreflight_csv_includes_required_import_preamble_row(client):
    _ensure_full_member_status()
    pilot = _make_member("foreflight_required_row_pilot")

    airfield = Airfield.objects.create(name="Marker Field", identifier="KMKR")
    glider = Glider.objects.create(
        n_number="N111MKR",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2026, 5, 23),
        airfield=airfield,
        created_by=pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 15),
    )

    client.force_login(pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    lines = response.content.decode().splitlines()

    required_text = (
        "This row is required for importing into ForeFlight. "
        "Do not delete or modify."
    )
    assert lines[0] == f"ForeFlight Logbook Import,{required_text}"


@pytest.mark.django_db
def test_foreflight_csv_aggregates_tow_pilot_daily_summary_rows(client):
    _ensure_full_member_status()
    tow_pilot = _make_member("foreflight_towpilot", glider_rating="rated")
    tow_pilot.towpilot = True
    tow_pilot.save(update_fields=["towpilot"])

    glider_pilot = _make_member("foreflight_glider_pilot")
    airfield = Airfield.objects.create(name="Tow Ops Field", identifier="KTOW")
    glider = Glider.objects.create(
        n_number="N200TOW",
        make="DG",
        model="DG-1000",
        club_owned=True,
        is_active=True,
    )
    towplane = Towplane.objects.create(
        n_number="N30TP",
        make="Piper",
        model="PA-25",
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2026, 5, 23),
        airfield=airfield,
        created_by=tow_pilot,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=glider_pilot,
        tow_pilot=tow_pilot,
        towplane=towplane,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 0),
        landing_time=time(10, 24),
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=glider_pilot,
        tow_pilot=tow_pilot,
        towplane=towplane,
        glider=glider,
        launch_method="tow",
        launch_time=time(10, 30),
        landing_time=time(10, 54),
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=glider_pilot,
        tow_pilot=tow_pilot,
        towplane=towplane,
        glider=glider,
        launch_method="tow",
        launch_time=time(11, 0),
        landing_time=time(11, 25),
    )

    client.force_login(tow_pilot)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    aircraft_rows = _parse_foreflight_aircraft_rows(response.content.decode())
    towplane_rows = [row for row in aircraft_rows if row.get("AircraftID") == "N30TP"]
    assert len(towplane_rows) == 1
    assert towplane_rows[0]["Category"] == "Airplane"

    rows = _parse_foreflight_flights_rows(response.content.decode())

    tow_rows = [
        row for row in rows if row.get("PilotComments", "") == "Tow pilot daily summary"
    ]

    assert len(tow_rows) == 1
    tow_row = tow_rows[0]
    assert tow_row["Date"] == "2026-05-23"
    assert tow_row["DayTakeoffs"] == "3"
    assert tow_row["DayLandingsFullStop"] == "3"
    assert tow_row["AllLandings"] == "3"
    assert float(tow_row["PIC"]) > 0


@pytest.mark.django_db
def test_foreflight_csv_sorts_rows_by_date_across_events_and_tow_summaries(client):
    _ensure_full_member_status()
    bob = _make_member("foreflight_bob_mixed_dates", glider_rating="rated")
    bob.towpilot = True
    bob.save(update_fields=["towpilot"])

    glider_pilot = _make_member("foreflight_bob_glider_pilot")
    instructor = _make_member(
        "foreflight_bob_ground_instructor", instructor=True, glider_rating="rated"
    )
    airfield = Airfield.objects.create(name="Mixed Date Field", identifier="KMDT")
    towplane = Towplane.objects.create(
        n_number="N88TP",
        make="Piper",
        model="PA-25",
        is_active=True,
    )
    glider = Glider.objects.create(
        n_number="N88GLD",
        make="Schleicher",
        model="ASK-21",
        club_owned=True,
        is_active=True,
    )

    saturday_logsheet = Logsheet.objects.create(
        log_date=date(2026, 5, 23),
        airfield=airfield,
        created_by=bob,
    )
    monday_logsheet = Logsheet.objects.create(
        log_date=date(2026, 5, 25),
        airfield=airfield,
        created_by=bob,
    )

    Flight.objects.create(
        logsheet=saturday_logsheet,
        pilot=glider_pilot,
        tow_pilot=bob,
        towplane=towplane,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 20),
    )
    Flight.objects.create(
        logsheet=monday_logsheet,
        pilot=glider_pilot,
        tow_pilot=bob,
        towplane=towplane,
        glider=glider,
        launch_method="tow",
        launch_time=time(9, 0),
        landing_time=time(9, 20),
    )

    GroundInstruction.objects.create(
        student=bob,
        instructor=instructor,
        date=date(2026, 5, 24),
        duration=timedelta(minutes=45),
        notes="Sunday instruction",
    )

    client.force_login(bob)
    response = client.get(reverse("instructors:member_logbook_export_foreflight"))

    assert response.status_code == 200
    rows = _parse_foreflight_flights_rows(response.content.decode())

    observed_dates = [
        row["Date"]
        for row in rows
        if row.get("PilotComments", "") == "Tow pilot daily summary"
        or float(row.get("GroundTraining", "0") or 0) > 0
    ]

    assert observed_dates == ["2026-05-23", "2026-05-24", "2026-05-25"]
