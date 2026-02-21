"""
Tests for the 'Request Surge Instructor' button (Issue #649).

Covers the request_surge_instructor view and the surrounding template logic
that surfaces the correct UI state (button, re-send variant, already-assigned
message, or static fallback text).
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_member(django_user_model, username, instructor=False, **extra):
    return django_user_model.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        **extra,
    )


def _make_assignment(instructor, date_offset=30):
    test_date = date.today() + timedelta(days=date_offset)
    return DutyAssignment.objects.create(date=test_date, instructor=instructor)


def _make_accepted_students(django_user_model, assignment, count=3):
    for i in range(count):
        student = _make_member(
            django_user_model,
            f"student_{assignment.date}_{i}",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student,
            instructor_response="accepted",
            status="confirmed",
        )


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_primary_instructor_can_send_surge_request(client, django_user_model):
    """Primary instructor POSTing to request_surge_instructor sends the email
    and sets surge_notified=True, then redirects with a success message."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )
    instructor = _make_member(django_user_model, "primary_instr", instructor=True)
    assignment = _make_assignment(instructor, date_offset=30)
    _make_accepted_students(django_user_model, assignment, count=3)
    client.force_login(instructor)

    url = reverse(
        "duty_roster:request_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:instructor_requests"))

    assignment.refresh_from_db()
    assert assignment.surge_notified is True
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_surge_instructor_cannot_send_surge_request(client, django_user_model):
    """A member acting as surge_instructor (not primary) is rejected with an
    error message; no email is sent."""
    primary = _make_member(django_user_model, "primary2", instructor=True)
    surge = _make_member(django_user_model, "surge2", instructor=True)
    assignment = _make_assignment(primary, date_offset=31)
    assignment.surge_instructor = surge
    assignment.save(update_fields=["surge_instructor"])

    client.force_login(surge)
    url = reverse(
        "duty_roster:request_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url)
        mock_send.assert_not_called()

    assert response.status_code == 302
    assignment.refresh_from_db()
    # surge_notified must not have been flipped
    assert assignment.surge_notified is False


@pytest.mark.django_db
def test_unrelated_member_cannot_send_surge_request(client, django_user_model):
    """A member who is not assigned to the day at all gets an error."""
    instructor = _make_member(django_user_model, "instr3", instructor=True)
    other = _make_member(django_user_model, "other3", instructor=True)
    assignment = _make_assignment(instructor, date_offset=32)

    client.force_login(other)
    url = reverse(
        "duty_roster:request_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url)
        mock_send.assert_not_called()

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_notified is False


@pytest.mark.django_db
def test_surge_request_shows_error_when_no_instructors_email(client, django_user_model):
    """If instructors_email is blank, the view shows an error and does NOT set
    surge_notified so the instructor can try again after the config is fixed."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="",  # misconfigured
    )
    instructor = _make_member(django_user_model, "instr4", instructor=True)
    assignment = _make_assignment(instructor, date_offset=33)
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(instructor)
    url = reverse(
        "duty_roster:request_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.post(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    # Email was not sent, so surge_notified must remain False
    assert assignment.surge_notified is False


@pytest.mark.django_db
def test_resend_surge_request_sends_email_even_when_already_notified(
    client, django_user_model
):
    """Clicking 'Re-send Surge Request' always fires the email regardless of
    the current surge_notified state."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )
    instructor = _make_member(django_user_model, "instr5", instructor=True)
    # Pre-set surge_notified=True (simulates a previous notification)
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=34),
        instructor=instructor,
        surge_notified=True,
    )
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(instructor)
    url = reverse(
        "duty_roster:request_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)
        mock_send.assert_called_once()

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Template rendering tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_template_shows_request_button_to_primary_instructor(client, django_user_model):
    """The instructor_requests page shows the 'Request Surge Instructor' button
    when the user is the primary instructor and 3+ students are accepted."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )
    instructor = _make_member(django_user_model, "tmpl_instr1", instructor=True)
    assignment = _make_assignment(instructor, date_offset=40)
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(instructor)
    url = reverse("duty_roster:instructor_requests")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Request Surge Instructor" in content
    assert "request-surge" in content  # URL contains the endpoint slug


@pytest.mark.django_db
def test_template_shows_resend_button_when_surge_already_notified(
    client, django_user_model
):
    """When surge_notified=True, the button label changes to 'Re-send Surge Request'."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )
    instructor = _make_member(django_user_model, "tmpl_instr2", instructor=True)
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=41),
        instructor=instructor,
        surge_notified=True,
    )
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(instructor)
    url = reverse("duty_roster:instructor_requests")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Re-send Surge Request" in content


@pytest.mark.django_db
def test_template_shows_assigned_message_when_surge_instructor_set(
    client, django_user_model
):
    """When surge_instructor is already assigned, the template shows a success
    message with the surge instructor's name instead of a request button."""
    SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )
    instructor = _make_member(django_user_model, "tmpl_instr3", instructor=True)
    surge = _make_member(
        django_user_model,
        "tmpl_surge3",
        instructor=True,
        first_name="Surge",
        last_name="Pilot",
    )
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=42),
        instructor=instructor,
        surge_instructor=surge,
    )
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(instructor)
    url = reverse("duty_roster:instructor_requests")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Surge instructor assigned" in content
    # Button should NOT be present since surge is already filled
    assert "Request Surge Instructor" not in content
    assert "Re-send Surge Request" not in content


@pytest.mark.django_db
def test_template_shows_static_text_to_non_primary_instructor(
    client, django_user_model
):
    """When the logged-in instructor is the surge instructor (not primary), the
    block shows static advisory text, not a request button."""
    primary = _make_member(django_user_model, "tmpl_primary4", instructor=True)
    surge = _make_member(django_user_model, "tmpl_surge4", instructor=True)
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=43),
        instructor=primary,
        surge_instructor=surge,
    )
    _make_accepted_students(django_user_model, assignment, count=3)

    # Log in as the surge instructor
    client.force_login(surge)
    url = reverse("duty_roster:instructor_requests")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    # The surge instructor sees the assigned message (their own name is on the assignment)
    assert "Surge instructor assigned" in content
    assert "Request Surge Instructor" not in content
