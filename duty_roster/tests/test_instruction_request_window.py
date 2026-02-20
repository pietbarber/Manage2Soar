"""
Tests for the instruction request window restriction (Issue #648).

Verifies that:
- The _check_instruction_request_window helper respects the SiteConfiguration
  toggle and max-days-ahead value.
- The request_instruction view enforces the restriction server-side.
- The calendar_day_detail view passes the correct context flags to the template
  so the UI shows/hides the form and info alert correctly.
"""

from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from logsheet.models import Airfield
from members.models import Member
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    """Prevent cache bleed between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def config(db) -> SiteConfiguration:
    """Return (or create) the singleton SiteConfiguration with default values."""
    obj, _ = SiteConfiguration.objects.get_or_create(
        defaults={
            "club_name": "Test Club",
            "domain_name": "test.example.com",
            "club_abbreviation": "TC",
        }
    )
    # Reset restriction fields to defaults so tests start clean.
    obj.restrict_instruction_requests_window = False
    obj.instruction_request_max_days_ahead = 14
    obj.save()
    return obj


@pytest.fixture
def airfield(db) -> Airfield:
    return Airfield.objects.create(name="Window Test Field", identifier="WNDW")


@pytest.fixture
def instructor(db) -> Member:
    m = Member.objects.create(
        username="window_instructor",
        email="window_instructor@test.com",
        first_name="Window",
        last_name="Instructor",
        membership_status="Full Member",
        instructor=True,
    )
    m.set_password("testpass123")
    m.save()
    return m


@pytest.fixture
def student(db) -> Member:
    m = Member.objects.create(
        username="window_student",
        email="window_student@test.com",
        first_name="Window",
        last_name="Student",
        membership_status="Student Member",
    )
    m.set_password("testpass123")
    m.save()
    return m


def make_assignment(days_ahead: int, instructor: Member, airfield: Airfield):
    """Create a DutyAssignment that many days into the future."""
    future_date = date.today() + timedelta(days=days_ahead)
    assignment = DutyAssignment.objects.create(
        date=future_date,
        instructor=instructor,
        location=airfield,
    )
    return assignment, future_date


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_helper_disabled_by_default(config: SiteConfiguration):
    """With restriction off (default), helper always returns (False, None)."""
    from duty_roster.views import _check_instruction_request_window

    assert not config.restrict_instruction_requests_window
    far_date = date.today() + timedelta(days=60)
    too_early, opens_on = _check_instruction_request_window(far_date)
    assert not too_early
    assert opens_on is None


@pytest.mark.django_db
def test_helper_within_window(config: SiteConfiguration):
    """With restriction on but date within window, helper returns (False, None)."""
    from duty_roster.views import _check_instruction_request_window

    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    near_date = date.today() + timedelta(days=10)
    too_early, opens_on = _check_instruction_request_window(near_date)
    assert not too_early
    assert opens_on is None


@pytest.mark.django_db
def test_helper_outside_window(config: SiteConfiguration):
    """With restriction on and date beyond window, helper returns (True, opens_on)."""
    from duty_roster.views import _check_instruction_request_window

    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    far_date = date.today() + timedelta(days=30)
    too_early, opens_on = _check_instruction_request_window(far_date)
    assert too_early
    assert opens_on == far_date - timedelta(days=14)


@pytest.mark.django_db
def test_helper_exactly_at_boundary(config: SiteConfiguration):
    """Date exactly at max_days_ahead is within the window (not too early)."""
    from duty_roster.views import _check_instruction_request_window

    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    boundary_date = date.today() + timedelta(days=14)
    too_early, opens_on = _check_instruction_request_window(boundary_date)
    assert not too_early
    assert opens_on is None


@pytest.mark.django_db
def test_helper_past_date_never_too_early(config: SiteConfiguration):
    """Past dates are never blocked by the window restriction."""
    from duty_roster.views import _check_instruction_request_window

    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    past_date = date.today() - timedelta(days=1)
    too_early, opens_on = _check_instruction_request_window(past_date)
    assert not too_early
    assert opens_on is None


# ---------------------------------------------------------------------------
# Server-side enforcement tests (request_instruction view)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_post_blocked_outside_window(
    client,
    config: SiteConfiguration,
    instructor: Member,
    airfield: Airfield,
    student: Member,
):
    """POST to request_instruction is rejected when date is past the window."""
    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    assignment, future_date = make_assignment(30, instructor, airfield)
    client.login(username="window_student", password="testpass123")

    url = reverse(
        "duty_roster:request_instruction",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    response = client.post(url, follow=True)

    assert response.status_code == 200
    assert not InstructionSlot.objects.filter(
        assignment=assignment, student=student
    ).exists()
    opens_on = future_date - timedelta(days=14)
    assert opens_on.strftime("%B") in response.content.decode()


@pytest.mark.django_db
def test_post_allowed_within_window(
    client,
    config: SiteConfiguration,
    instructor: Member,
    airfield: Airfield,
    student: Member,
):
    """POST to request_instruction succeeds when date is within the window."""
    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    assignment, future_date = make_assignment(7, instructor, airfield)
    client.login(username="window_student", password="testpass123")

    url = reverse(
        "duty_roster:request_instruction",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    response = client.post(url)

    assert response.status_code == 302
    assert InstructionSlot.objects.filter(
        assignment=assignment, student=student
    ).exists()


@pytest.mark.django_db
def test_post_allowed_when_restriction_disabled(
    client,
    config: SiteConfiguration,
    instructor: Member,
    airfield: Airfield,
    student: Member,
):
    """POST succeeds for a far-future date when restriction is disabled."""
    assert not config.restrict_instruction_requests_window

    assignment, future_date = make_assignment(60, instructor, airfield)
    client.login(username="window_student", password="testpass123")

    url = reverse(
        "duty_roster:request_instruction",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    response = client.post(url)

    assert response.status_code == 302
    assert InstructionSlot.objects.filter(
        assignment=assignment, student=student
    ).exists()


# ---------------------------------------------------------------------------
# SiteConfiguration model field defaults
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_siteconfig_defaults():
    """New fields have correct default values."""
    field_window = SiteConfiguration._meta.get_field(
        "restrict_instruction_requests_window"
    )
    field_days = SiteConfiguration._meta.get_field("instruction_request_max_days_ahead")
    assert field_window.default is False
    assert field_days.default == 14


# ---------------------------------------------------------------------------
# UI / calendar_day_detail integration tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_calendar_day_detail_shows_info_alert_when_too_early(
    client,
    config: SiteConfiguration,
    instructor: Member,
    airfield: Airfield,
    student: Member,
):
    """When restriction is active and date is outside window, the day modal shows
    the 'not yet open' info alert and does NOT render the instruction request form."""
    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    assignment, future_date = make_assignment(30, instructor, airfield)
    client.login(username="window_student", password="testpass123")

    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Instruction requests not yet open" in content

    opens_on = future_date - timedelta(days=14)
    assert str(opens_on.day) in content

    form_action = reverse(
        "duty_roster:request_instruction",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    assert form_action not in content


@pytest.mark.django_db
def test_calendar_day_detail_shows_form_when_within_window(
    client,
    config: SiteConfiguration,
    instructor: Member,
    airfield: Airfield,
    student: Member,
):
    """When restriction is active but date is within the window, the request form
    is rendered and the info alert is absent."""
    config.restrict_instruction_requests_window = True
    config.instruction_request_max_days_ahead = 14
    config.save()

    assignment, future_date = make_assignment(7, instructor, airfield)
    client.login(username="window_student", password="testpass123")

    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Instruction requests not yet open" not in content

    form_action = reverse(
        "duty_roster:request_instruction",
        kwargs={
            "year": future_date.year,
            "month": future_date.month,
            "day": future_date.day,
        },
    )
    assert form_action in content
