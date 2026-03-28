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
from logsheet.models import Airfield, Flight, Glider, Logsheet
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
