"""
Tests for the 'Volunteer as Surge Tow Pilot' self-signup flow (Issue #688).

Mirrors test_volunteer_surge_instructor.py for the tow pilot role.

Covers:
- GET confirmation page (renders for tow pilots, rejects non-tow-pilots)
- POST success path (assigns surge_tow_pilot, notifies primary, redirects)
- POST already-assigned guard (race-condition protection)
- Non-tow-pilot rejection
- Unauthenticated redirect
- 404 for nonexistent assignment
- _notify_primary_tow_pilot_surge_filled helper (success / failure paths)
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment
from duty_roster.views import _notify_primary_tow_pilot_surge_filled
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_member(django_user_model, username, towpilot=False, **extra):
    extra.setdefault("email", f"{username}@example.com")
    return django_user_model.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        towpilot=towpilot,
        **extra,
    )


def _make_assignment(tow_pilot, date_offset=60):
    test_date = date.today() + timedelta(days=date_offset)
    return DutyAssignment.objects.create(date=test_date, tow_pilot=tow_pilot)


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
def test_get_shows_confirmation_page_for_tow_pilot(client, django_user_model):
    """An authenticated tow pilot GETting the URL sees the confirmation page."""
    _make_site_config()
    primary = _make_member(django_user_model, "tp_primary1", towpilot=True)
    volunteer = _make_member(django_user_model, "tp_vol1", towpilot=True)
    assignment = _make_assignment(primary, date_offset=60)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Surge Tow Pilot" in content or "surge" in content.lower()


@pytest.mark.django_db
def test_get_confirmation_page_shows_date_and_primary(client, django_user_model):
    """The confirmation page renders the assignment date and primary tow pilot name."""
    _make_site_config()
    primary = _make_member(django_user_model, "tp_primary2", towpilot=True)
    volunteer = _make_member(django_user_model, "tp_vol2", towpilot=True)
    assignment = _make_assignment(primary, date_offset=61)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    formatted = assignment.date.strftime("%B")
    assert formatted in content


@pytest.mark.django_db
def test_get_rejected_for_non_tow_pilot(client, django_user_model):
    """A non-tow-pilot member GETting the URL is redirected with an error message."""
    primary = _make_member(django_user_model, "tp_primary3", towpilot=True)
    non_tp = _make_member(django_user_model, "tp_nottp3", towpilot=False)
    assignment = _make_assignment(primary, date_offset=62)

    client.force_login(non_tp)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "duty_calendar" in response["Location"] or response["Location"].endswith("/")


@pytest.mark.django_db
def test_get_rejected_for_past_duty_day(client, django_user_model):
    """A tow pilot cannot volunteer for a duty day that is already past."""
    primary = _make_member(django_user_model, "tp_past_primary", towpilot=True)
    volunteer = _make_member(django_user_model, "tp_past_vol", towpilot=True)
    # Create assignment in the past (negative offset)
    past_date = date.today() - timedelta(days=1)
    assignment = DutyAssignment.objects.create(date=past_date, tow_pilot=primary)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_tow_pilot is None  # not assigned


@pytest.mark.django_db
def test_get_rejected_when_no_primary_tow_pilot(client, django_user_model):
    """Cannot volunteer as surge when there is no primary tow pilot on the assignment."""
    volunteer = _make_member(django_user_model, "tp_noprimary_vol", towpilot=True)
    # Assignment with no tow pilot set
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=30), tow_pilot=None
    )

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_tow_pilot is None


@pytest.mark.django_db
def test_get_rejected_when_volunteer_is_the_primary(client, django_user_model):
    """The primary tow pilot cannot volunteer as their own surge."""
    primary = _make_member(django_user_model, "tp_selfprimary", towpilot=True)
    assignment = _make_assignment(primary, date_offset=50)

    client.force_login(primary)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_tow_pilot is None


@pytest.mark.django_db
def test_get_redirects_if_surge_already_assigned_by_other(client, django_user_model):
    """If a surge tow pilot is already assigned, GET shows an informational redirect."""
    primary = _make_member(django_user_model, "tp_primary4", towpilot=True)
    existing_surge = _make_member(django_user_model, "tp_existing4", towpilot=True)
    volunteer = _make_member(django_user_model, "tp_late4", towpilot=True)

    assignment = _make_assignment(primary, date_offset=63)
    assignment.surge_tow_pilot = existing_surge
    assignment.save(update_fields=["surge_tow_pilot"])

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302


@pytest.mark.django_db
def test_get_redirects_with_info_if_user_is_already_the_surge(
    client, django_user_model
):
    """If the requesting user is already the surge tow pilot, GET redirects with info."""
    primary = _make_member(django_user_model, "tp_primary5", towpilot=True)
    surge = _make_member(django_user_model, "tp_surge5", towpilot=True)

    assignment = _make_assignment(primary, date_offset=64)
    assignment.surge_tow_pilot = surge
    assignment.save(update_fields=["surge_tow_pilot"])

    client.force_login(surge)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# POST — success path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_assigns_surge_tow_pilot(client, django_user_model):
    """A valid POST assigns the volunteering tow pilot as surge_tow_pilot."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_post_primary1", towpilot=True, email="tp_prim1@sky.org"
    )
    volunteer = _make_member(django_user_model, "tp_post_vol1", towpilot=True)
    assignment = _make_assignment(primary, date_offset=65)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_tow_pilot == volunteer


@pytest.mark.django_db
def test_post_redirects_to_duty_calendar(client, django_user_model):
    """A successful POST redirects to the duty calendar."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_post_primary2", towpilot=True, email="tp_prim2@sky.org"
    )
    volunteer = _make_member(django_user_model, "tp_post_vol2", towpilot=True)
    assignment = _make_assignment(primary, date_offset=66)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url)

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:duty_calendar"))


@pytest.mark.django_db
def test_post_notifies_primary_tow_pilot_by_email(client, django_user_model):
    """After a successful POST, the primary tow pilot receives an HTML email."""
    _make_site_config()
    primary = _make_member(
        django_user_model,
        "tp_post_primary3",
        towpilot=True,
        email="tp_primary3@sky.org",
    )
    volunteer = _make_member(django_user_model, "tp_post_vol3", towpilot=True)
    assignment = _make_assignment(primary, date_offset=67)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        client.post(url)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert primary.email in call_kwargs[0][3]  # recipient list


@pytest.mark.django_db
def test_post_success_message_mentions_primary_notified(client, django_user_model):
    """Success flash message mentions that the primary tow pilot was notified."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_post_primary4", towpilot=True, email="tp_p4@sky.org"
    )
    volunteer = _make_member(django_user_model, "tp_post_vol4", towpilot=True)
    assignment = _make_assignment(primary, date_offset=68)

    client.force_login(volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, follow=True)

    content = response.content.decode()
    assert "notified" in content.lower() or "surge tow pilot" in content.lower()


# ---------------------------------------------------------------------------
# POST — race condition guard
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_race_condition_guard(client, django_user_model):
    """If someone fills the surge slot between GET and POST, the late POST is rejected."""
    primary = _make_member(django_user_model, "tp_race_primary", towpilot=True)
    first_volunteer = _make_member(django_user_model, "tp_race_first", towpilot=True)
    late_volunteer = _make_member(django_user_model, "tp_race_late", towpilot=True)

    assignment = _make_assignment(primary, date_offset=69)

    # Pre-fill the surge slot so the POST sees it on refresh_from_db
    assignment.surge_tow_pilot = first_volunteer
    assignment.save(update_fields=["surge_tow_pilot"])

    client.force_login(late_volunteer)
    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.post(url)

    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.surge_tow_pilot == first_volunteer  # first volunteer kept


# ---------------------------------------------------------------------------
# Authentication / 404
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_redirects_to_login(client, django_user_model):
    """Unauthenticated user is redirected away from the URL."""
    primary = _make_member(django_user_model, "tp_anon_p", towpilot=True)
    assignment = _make_assignment(primary, date_offset=70)

    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": assignment.id},
    )
    response = client.get(url)

    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_nonexistent_assignment_returns_404(client, django_user_model):
    """A GET for a nonexistent assignment_id returns 404."""
    member = _make_member(django_user_model, "tp_404", towpilot=True)
    client.force_login(member)

    url = reverse(
        "duty_roster:volunteer_surge_tow_pilot",
        kwargs={"assignment_id": 999999},
    )
    response = client.get(url)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# _notify_primary_tow_pilot_surge_filled helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notify_helper_returns_true_on_success(django_user_model):
    """_notify_primary_tow_pilot_surge_filled returns True when mail is sent."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_notify1", towpilot=True, email="tp_notify1@sky.org"
    )
    surge = _make_member(django_user_model, "tp_notify_surge1", towpilot=True)
    assignment = _make_assignment(primary, date_offset=71)
    assignment.surge_tow_pilot = surge
    assignment.save(update_fields=["surge_tow_pilot"])

    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        result = _notify_primary_tow_pilot_surge_filled(assignment)

    assert result is True
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_notify_helper_returns_false_when_no_primary_email(django_user_model):
    """Returns False when the primary tow pilot has no email address."""
    _make_site_config()
    primary = _make_member(django_user_model, "tp_notify2", towpilot=True, email="")
    surge = _make_member(django_user_model, "tp_notify_surge2", towpilot=True)
    assignment = _make_assignment(primary, date_offset=72)
    assignment.surge_tow_pilot = surge
    assignment.save(update_fields=["surge_tow_pilot"])

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_primary_tow_pilot_surge_filled(assignment)

    assert result is False
    mock_send.assert_not_called()


@pytest.mark.django_db
def test_notify_helper_returns_false_on_smtp_error(django_user_model):
    """Returns False (and logs) when send_mail raises an exception."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_notify3", towpilot=True, email="tp_notify3@sky.org"
    )
    surge = _make_member(django_user_model, "tp_notify_surge3", towpilot=True)
    assignment = _make_assignment(primary, date_offset=73)
    assignment.surge_tow_pilot = surge
    assignment.save(update_fields=["surge_tow_pilot"])

    with patch("duty_roster.views.send_mail", side_effect=Exception("SMTP error")):
        result = _notify_primary_tow_pilot_surge_filled(assignment)

    assert result is False


@pytest.mark.django_db
def test_notify_helper_returns_false_when_surge_not_set(django_user_model):
    """Returns False when surge_tow_pilot is not yet set on the assignment."""
    _make_site_config()
    primary = _make_member(
        django_user_model, "tp_notify4", towpilot=True, email="tp_notify4@sky.org"
    )
    assignment = _make_assignment(primary, date_offset=74)
    # surge_tow_pilot intentionally left unset

    with patch("duty_roster.views.send_mail") as mock_send:
        result = _notify_primary_tow_pilot_surge_filled(assignment)

    assert result is False
    mock_send.assert_not_called()
