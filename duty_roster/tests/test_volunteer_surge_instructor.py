"""
Tests for the 'Volunteer as Surge Instructor' self-signup flow (Issue #663).

Covers:
- GET confirmation page (renders for instructors, rejects non-instructors)
- POST success path (assigns surge_instructor, notifies primary, redirects)
- POST already-assigned guard (race-condition protection)
- Non-instructor rejection
- Unauthenticated redirect
- 404 for nonexistent assignment
- _notify_primary_instructor_surge_filled helper (success / failure paths)
- surge_instructor_alert email now includes volunteer_url in context
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from duty_roster.views import (
    _notify_primary_instructor_surge_filled,
    _notify_surge_instructor_needed,
)
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers (mirror test_request_surge_instructor.py for consistency)
# ---------------------------------------------------------------------------


def _make_member(django_user_model, username, instructor=False, **extra):
    extra.setdefault("email", f"{username}@example.com")
    return django_user_model.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        **extra,
    )


def _make_assignment(instructor, date_offset=60):
    test_date = date.today() + timedelta(days=date_offset)
    return DutyAssignment.objects.create(date=test_date, instructor=instructor)


def _make_accepted_students(django_user_model, assignment, count=4):
    for i in range(count):
        student = _make_member(
            django_user_model,
            f"student_v_{assignment.date}_{i}",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student,
            instructor_response="accepted",
            status="confirmed",
        )


def _make_site_config():
    return SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
    )


# ---------------------------------------------------------------------------
# GET — confirmation page
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_shows_confirmation_page_for_instructor(client, django_user_model):
    """An authenticated instructor GETting the URL sees the confirmation page."""
    _make_site_config()
    primary = _make_member(django_user_model, "vol_primary1", instructor=True)
    volunteer = _make_member(django_user_model, "vol_instr1", instructor=True)
    assignment = _make_assignment(primary, date_offset=60)
    _make_accepted_students(django_user_model, assignment, count=4)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Surge Instructor" in content
    assert "volunteer" in content.lower() or "surge" in content.lower()


@pytest.mark.django_db
def test_get_confirmation_page_shows_date_and_student_count(client, django_user_model):
    """The confirmation page renders the assignment date and accepted student count."""
    _make_site_config()
    primary = _make_member(django_user_model, "vol_primary2", instructor=True)
    volunteer = _make_member(django_user_model, "vol_instr2", instructor=True)
    assignment = _make_assignment(primary, date_offset=61)
    _make_accepted_students(django_user_model, assignment, count=3)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    # Student count should appear in the confirmation context
    assert "3" in content
    # The assignment date should appear
    formatted = assignment.date.strftime("%B")
    assert formatted in content


@pytest.mark.django_db
def test_get_rejected_for_non_instructor(client, django_user_model):
    """A non-instructor member GETting the URL is redirected with an error message."""
    primary = _make_member(django_user_model, "vol_primary3", instructor=True)
    non_instr = _make_member(django_user_model, "vol_noninstr3", instructor=False)
    assignment = _make_assignment(primary, date_offset=62)

    client.force_login(non_instr)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "duty_calendar" in response["Location"] or response["Location"].endswith("/")


@pytest.mark.django_db
def test_get_rejected_for_past_duty_day(client, django_user_model):
    """An instructor volunteering for a past day is redirected with an error message."""
    primary = _make_member(django_user_model, "vol_primary_past", instructor=True)
    volunteer = _make_member(django_user_model, "vol_volunteer_past", instructor=True)
    # Create assignment in the past
    past_assignment = DutyAssignment.objects.create(
        date=date.today() - timedelta(days=1),
        instructor=primary,
    )

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": past_assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "duty_calendar" in response["Location"] or response["Location"].endswith("/")
    # Surge instructor must remain unset
    past_assignment.refresh_from_db()
    assert past_assignment.surge_instructor_id is None


@pytest.mark.django_db
def test_get_rejected_when_no_primary_instructor(client, django_user_model):
    """Volunteering is rejected when no primary instructor is assigned (surge not needed)."""
    volunteer = _make_member(django_user_model, "vol_noprimary", instructor=True)
    # Assignment with no primary instructor set
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=10),
    )

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "duty_calendar" in response["Location"] or response["Location"].endswith("/")
    assignment.refresh_from_db()
    assert assignment.surge_instructor_id is None


@pytest.mark.django_db
def test_get_rejected_when_volunteer_is_the_primary(client, django_user_model):
    """The primary instructor cannot volunteer as their own surge instructor."""
    primary = _make_member(django_user_model, "vol_selfprimary", instructor=True)
    assignment = _make_assignment(primary, date_offset=11)

    client.force_login(primary)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "duty_calendar" in response["Location"] or response["Location"].endswith("/")
    assignment.refresh_from_db()
    assert assignment.surge_instructor_id is None


@pytest.mark.django_db
def test_get_redirects_if_surge_already_assigned_by_other(client, django_user_model):
    """If a surge instructor is already assigned, GET shows an informational redirect."""
    primary = _make_member(django_user_model, "vol_primary4", instructor=True)
    existing_surge = _make_member(django_user_model, "vol_existing4", instructor=True)
    volunteer = _make_member(django_user_model, "vol_late4", instructor=True)

    assignment = _make_assignment(primary, date_offset=63)
    assignment.surge_instructor = existing_surge
    assignment.save(update_fields=["surge_instructor"])

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302


@pytest.mark.django_db
def test_get_redirects_with_info_if_user_is_already_the_surge(
    client, django_user_model
):
    """If the requesting user is already the surge instructor, GET shows a
    friendly info message and redirects."""
    primary = _make_member(django_user_model, "vol_primary5", instructor=True)
    surge = _make_member(django_user_model, "vol_surge5", instructor=True)

    assignment = _make_assignment(primary, date_offset=64)
    assignment.surge_instructor = surge
    assignment.save(update_fields=["surge_instructor"])

    client.force_login(surge)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# POST — success path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_assigns_surge_instructor(client, django_user_model):
    """A valid POST assigns the volunteering instructor as surge_instructor."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "vol_post_primary1", instructor=True, email="prim1@sky.org"
    )
    volunteer = _make_member(django_user_model, "vol_post_instr1", instructor=True)
    assignment = _make_assignment(primary, date_offset=65)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_instructor == volunteer


@pytest.mark.django_db
def test_post_redirects_to_duty_calendar(client, django_user_model):
    """A successful POST redirects to the duty calendar."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "vol_post_primary2", instructor=True, email="prim2@sky.org"
    )
    volunteer = _make_member(django_user_model, "vol_post_instr2", instructor=True)
    assignment = _make_assignment(primary, date_offset=66)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:duty_calendar"))


@pytest.mark.django_db
def test_post_notifies_primary_instructor_by_email(client, django_user_model):
    """After a successful POST, the primary instructor receives an HTML email."""
    _make_site_config()
    primary = _make_member(
        django_user_model,
        "vol_post_primary3",
        instructor=True,
        email="primary3@sky.org",
    )
    volunteer = _make_member(django_user_model, "vol_post_instr3", instructor=True)
    assignment = _make_assignment(primary, date_offset=67)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        client.post(url)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    # The notification must be sent to the primary instructor's email
    recipients = (
        call_kwargs.args[3]
        if len(call_kwargs.args) > 3
        else call_kwargs.kwargs.get("recipient_list", [])
    )
    assert "primary3@sky.org" in recipients
    # HTML message must be present
    html_content = call_kwargs.kwargs.get("html_message", "")
    assert "<html" in html_content.lower()


@pytest.mark.django_db
def test_post_non_instructor_is_rejected(client, django_user_model):
    """A POST from a non-instructor is rejected and surge_instructor stays unset."""
    primary = _make_member(django_user_model, "vol_post_primary4", instructor=True)
    non_instr = _make_member(django_user_model, "vol_post_noninstr4", instructor=False)
    assignment = _make_assignment(primary, date_offset=68)

    client.force_login(non_instr)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url)
        mock_send.assert_not_called()

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_instructor is None


@pytest.mark.django_db
def test_post_already_assigned_does_not_overwrite(client, django_user_model):
    """If another volunteer was assigned between the GET and POST (race),
    the late POST is a no-op — the existing surge instructor is not overwritten."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "vol_race_primary", instructor=True, email="rp@sky.org"
    )
    first_volunteer = _make_member(django_user_model, "vol_race_first", instructor=True)
    late_volunteer = _make_member(django_user_model, "vol_race_late", instructor=True)
    assignment = _make_assignment(primary, date_offset=69)
    # Simulate first volunteer already assigned before late_volunteer POSTs
    assignment.surge_instructor = first_volunteer
    assignment.save(update_fields=["surge_instructor"])

    client.force_login(late_volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        response = client.post(url)
        mock_send.assert_not_called()

    assert response.status_code == 302
    assignment.refresh_from_db()
    # first_volunteer must remain; late_volunteer must not have overwritten
    assert assignment.surge_instructor == first_volunteer


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login(client, django_user_model):
    """Unauthenticated GET redirects to the login page."""
    primary = _make_member(django_user_model, "vol_anon_p", instructor=True)
    assignment = _make_assignment(primary, date_offset=70)

    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_unauthenticated_post_redirects_to_login(client, django_user_model):
    """Unauthenticated POST redirects to the login page."""
    primary = _make_member(django_user_model, "vol_anon_p2", instructor=True)
    assignment = _make_assignment(primary, date_offset=71)

    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.post(url)

    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_invalid_assignment_id_returns_404(client, django_user_model):
    """Nonexistent assignment_id returns 404."""
    volunteer = _make_member(django_user_model, "vol_404", instructor=True)
    client.force_login(volunteer)

    url = reverse(
        "duty_roster:volunteer_surge_instructor",
        kwargs={"assignment_id": 999999},
    )
    response = client.get(url)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# _notify_primary_instructor_surge_filled helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notify_primary_returns_true_on_success(django_user_model):
    """Helper returns True and sends HTML email to primary instructor on success."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "nfp_primary", instructor=True, email="nfp@sky.org"
    )
    surge = _make_member(
        django_user_model,
        "nfp_surge",
        instructor=True,
        first_name="Alice",
        last_name="Flyer",
    )
    assignment = _make_assignment(primary, date_offset=80)
    assignment.surge_instructor = surge
    assignment.save(update_fields=["surge_instructor"])

    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        result = _notify_primary_instructor_surge_filled(assignment)

    assert result is True
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    html_content = call_kwargs.kwargs.get("html_message", "")
    assert "<html" in html_content.lower()
    # Primary instructor's email should be among recipients
    recipients = (
        call_kwargs.args[3]
        if len(call_kwargs.args) > 3
        else call_kwargs.kwargs.get("recipient_list", [])
    )
    assert "nfp@sky.org" in recipients


@pytest.mark.django_db
def test_notify_primary_returns_false_when_primary_has_no_email(django_user_model):
    """Helper returns False (without crashing) when primary instructor has no email."""
    _make_site_config()
    primary = django_user_model.objects.create_user(
        username="nfp_noemail",
        email="",  # no email
        password="password",
        membership_status="Full Member",
        instructor=True,
    )
    surge = _make_member(django_user_model, "nfp_surge2", instructor=True)
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=81),
        instructor=primary,
        surge_instructor=surge,
    )

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_primary_instructor_surge_filled(assignment)
        mock_send.assert_not_called()

    assert result is False


@pytest.mark.django_db
def test_notify_primary_returns_false_on_smtp_failure(django_user_model):
    """Helper returns False when send_mail raises an exception."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "nfp_smtp", instructor=True, email="smtp@sky.org"
    )
    surge = _make_member(django_user_model, "nfp_surge3", instructor=True)
    assignment = _make_assignment(primary, date_offset=82)
    assignment.surge_instructor = surge
    assignment.save(update_fields=["surge_instructor"])

    with patch("duty_roster.views.send_mail", side_effect=Exception("SMTP error")):
        result = _notify_primary_instructor_surge_filled(assignment)

    assert result is False


@pytest.mark.django_db
def test_notify_primary_returns_false_when_no_surge_instructor(django_user_model):
    """Helper returns False without sending if surge_instructor is not yet set."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "nfp_nosurge", instructor=True, email="nosurge@sky.org"
    )
    assignment = _make_assignment(primary, date_offset=83)
    # Do NOT assign surge_instructor

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_primary_instructor_surge_filled(assignment)
        mock_send.assert_not_called()

    assert result is False


# ---------------------------------------------------------------------------
# _notify_surge_instructor_needed now includes volunteer_url
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_alert_email_context_includes_volunteer_url(django_user_model):
    """The surge alert email is sent with a context that includes the volunteer URL."""
    _make_site_config()
    primary = _make_member(django_user_model, "vurl_primary", instructor=True)
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=90),
        instructor=primary,
    )

    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        _notify_surge_instructor_needed(assignment, student_count=4)

    mock_send.assert_called_once()
    # The text body (2nd positional arg) should contain the volunteer URL path
    text_body = mock_send.call_args.args[1]
    assert "volunteer-surge" in text_body

    # The HTML body should also contain the volunteer URL path
    html_body = mock_send.call_args.kwargs.get("html_message", "")
    assert "volunteer-surge" in html_body
