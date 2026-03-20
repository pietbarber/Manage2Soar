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
    signature_rows = [
        r for r in rows if r.get("signature_html") and "/s/" in r["signature_html"]
    ]
    assert signature_rows
    for row in signature_rows:
        assert "<br>/s/" in row["signature_html"]
        assert "3303513CFI" in row["signature_html"]
        assert ", 3303513CFI" not in row["signature_html"]
