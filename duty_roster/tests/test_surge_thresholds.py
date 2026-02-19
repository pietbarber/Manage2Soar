"""
Tests for configurable surge thresholds (Issue #403).
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot, OpsIntent
from duty_roster.views import (
    _check_surge_instructor_needed,
    _notify_surge_instructor_needed,
    get_surge_thresholds,
    maybe_notify_surge_instructor,
    maybe_notify_surge_towpilot,
)
from siteconfig.models import SiteConfiguration


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache before each test to prevent test contamination."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_get_surge_thresholds_defaults():
    """Test get_surge_thresholds returns defaults when no config exists."""
    SiteConfiguration.objects.all().delete()
    tow_threshold, instruction_threshold = get_surge_thresholds()
    assert tow_threshold == 6
    assert instruction_threshold == 4


@pytest.mark.django_db
def test_get_surge_thresholds_from_config():
    """Test get_surge_thresholds uses values from SiteConfiguration."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=10,
        instruction_surge_threshold=5,
    )
    tow_threshold, instruction_threshold = get_surge_thresholds()
    assert tow_threshold == 10
    assert instruction_threshold == 5


@pytest.mark.django_db
def test_calendar_view_uses_custom_thresholds(client, django_user_model):
    """Test that calendar view uses custom surge thresholds in context."""
    # Create config with custom thresholds
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=8,
        instruction_surge_threshold=3,
    )

    # Create an active member
    user = django_user_model.objects.create_user(
        username="testmember",
        email="test@example.com",
        password="password",
        membership_status="Full Member",
    )
    client.force_login(user)

    # Request calendar view
    url = reverse("duty_roster:duty_calendar")
    response = client.get(url)

    assert response.status_code == 200
    assert response.context["tow_surge_threshold"] == 8
    assert response.context["instruction_surge_threshold"] == 3


@pytest.mark.django_db
def test_surge_alert_with_custom_instruction_threshold(client, django_user_model):
    """Test that surge alerts trigger at custom instruction threshold."""
    # Create config with lower instruction threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instruction_surge_threshold=2,  # Lower threshold for testing
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    user1 = django_user_model.objects.create_user(
        username="student1",
        email="student1@example.com",
        password="password",
        membership_status="Full Member",
    )
    user2 = django_user_model.objects.create_user(
        username="student2",
        email="student2@example.com",
        password="password",
        membership_status="Full Member",
    )

    # Create instruction intents (2 should trigger alert with threshold=2)
    OpsIntent.objects.create(
        member=user1,
        date=test_date,
        available_as=["instruction"],
        notes="Test 1",
    )
    OpsIntent.objects.create(
        member=user2,
        date=test_date,
        available_as=["instruction"],
        notes="Test 2",
    )

    # Login as user and check day detail
    client.force_login(user1)
    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={"year": test_date.year, "month": test_date.month, "day": test_date.day},
    )
    response = client.get(url)

    assert response.status_code == 200
    # Should show surge alert because we have 2 instruction requests and threshold is 2
    assert response.context["show_surge_alert"] is True


@pytest.mark.django_db
def test_tow_surge_alert_with_custom_threshold(client, django_user_model):
    """Test that tow surge alerts trigger at custom threshold."""
    # Create config with lower tow threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=3,  # Lower threshold for testing
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    users = []
    for i in range(3):
        user = django_user_model.objects.create_user(
            username=f"pilot{i}",
            email=f"pilot{i}@example.com",
            password="password",
            membership_status="Full Member",
        )
        users.append(user)
        # Create tow intent (club or private)
        OpsIntent.objects.create(
            member=user, date=test_date, available_as=["club"], notes=f"Tow {i}"
        )

    # Login and check day detail
    client.force_login(users[0])
    url = reverse(
        "duty_roster:calendar_day_detail",
        kwargs={"year": test_date.year, "month": test_date.month, "day": test_date.day},
    )
    response = client.get(url)

    assert response.status_code == 200
    # Should show tow surge alert because we have 3 tow requests and threshold is 3
    assert response.context["show_tow_surge_alert"] is True


@pytest.mark.django_db
def test_calendar_view_surge_indicator_respects_threshold(client, django_user_model):
    """Test that calendar view marks days with surge when threshold is met."""
    # Create config with custom threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instruction_surge_threshold=2,
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    user1 = django_user_model.objects.create_user(
        username="student1",
        email="student1@example.com",
        password="password",
        membership_status="Full Member",
    )
    user2 = django_user_model.objects.create_user(
        username="student2",
        email="student2@example.com",
        password="password",
        membership_status="Full Member",
    )

    # Create exactly 2 instruction intents (meets threshold)
    OpsIntent.objects.create(
        member=user1, date=test_date, available_as=["instruction"], notes="Test 1"
    )
    OpsIntent.objects.create(
        member=user2, date=test_date, available_as=["instruction"], notes="Test 2"
    )

    # Login and request calendar for that month
    client.force_login(user1)
    url = reverse(
        "duty_roster:duty_calendar_month",
        kwargs={"year": test_date.year, "month": test_date.month},
    )
    response = client.get(url)

    assert response.status_code == 200
    # Check surge_needed_by_date context
    surge_data = response.context["surge_needed_by_date"]
    # Should show instruction surge on test_date
    assert surge_data[test_date]["instructor"] is True


@pytest.mark.django_db
def test_maybe_notify_surge_instructor_respects_custom_threshold(django_user_model):
    """Test that maybe_notify_surge_instructor uses custom threshold (Issue #403)."""
    # Create config with custom instruction threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instruction_surge_threshold=2,  # Lower threshold for testing
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    user1 = django_user_model.objects.create_user(
        username="student1",
        email="student1@example.com",
        password="password",
        membership_status="Full Member",
    )
    user2 = django_user_model.objects.create_user(
        username="student2",
        email="student2@example.com",
        password="password",
        membership_status="Full Member",
    )

    # Create exactly 2 instruction intents (meets custom threshold=2)
    OpsIntent.objects.create(
        member=user1, date=test_date, available_as=["instruction"], notes="Test 1"
    )
    OpsIntent.objects.create(
        member=user2, date=test_date, available_as=["instruction"], notes="Test 2"
    )

    # Mock send_mail to verify it's called
    with patch("duty_roster.views.send_mail") as mock_send_mail:
        maybe_notify_surge_instructor(test_date)

        # Email should be sent because we met the custom threshold of 2
        mock_send_mail.assert_called_once()

        # Verify subject contains surge alert
        call_kwargs = mock_send_mail.call_args[1]
        assert "Surge Instructor May Be Needed" in call_kwargs["subject"]

        # Verify assignment is marked as notified
        assignment = DutyAssignment.objects.get(date=test_date)
        assert assignment.surge_notified is True


@pytest.mark.django_db
def test_maybe_notify_surge_instructor_does_not_send_below_threshold(
    django_user_model,
):
    """Test that surge instructor notification isn't sent below threshold."""
    # Create config with custom instruction threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instruction_surge_threshold=5,  # Higher threshold
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    user1 = django_user_model.objects.create_user(
        username="student1",
        email="student1@example.com",
        password="password",
        membership_status="Full Member",
    )

    # Create only 1 instruction intent (below threshold=5)
    OpsIntent.objects.create(
        member=user1, date=test_date, available_as=["instruction"], notes="Test 1"
    )

    # Mock send_mail to verify it's NOT called
    with patch("duty_roster.views.send_mail") as mock_send_mail:
        maybe_notify_surge_instructor(test_date)

        # Email should NOT be sent because we're below threshold
        mock_send_mail.assert_not_called()

        # Assignment should not be marked as notified
        assignment = DutyAssignment.objects.get(date=test_date)
        assert assignment.surge_notified is False


@pytest.mark.django_db
def test_maybe_notify_surge_towpilot_respects_custom_threshold(django_user_model):
    """Test that maybe_notify_surge_towpilot uses custom threshold (Issue #403)."""
    # Create config with custom tow threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=3,  # Lower threshold for testing
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    users = []
    for i in range(3):
        user = django_user_model.objects.create_user(
            username=f"pilot{i}",
            email=f"pilot{i}@example.com",
            password="password",
            membership_status="Full Member",
        )
        users.append(user)
        # Create tow intent (club or private)
        OpsIntent.objects.create(
            member=user, date=test_date, available_as=["club"], notes=f"Tow {i}"
        )

    # Mock send_mail to verify it's called
    with patch("duty_roster.views.send_mail") as mock_send_mail:
        maybe_notify_surge_towpilot(test_date)

        # Email should be sent because we met the custom threshold of 3
        mock_send_mail.assert_called_once()

        # Verify subject contains surge alert
        call_kwargs = mock_send_mail.call_args[1]
        assert "Surge Tow Pilot May Be Needed" in call_kwargs["subject"]

        # Verify assignment is marked as notified
        assignment = DutyAssignment.objects.get(date=test_date)
        assert assignment.tow_surge_notified is True


@pytest.mark.django_db
def test_maybe_notify_surge_towpilot_does_not_send_below_threshold(django_user_model):
    """Test that surge towpilot notification isn't sent below threshold."""
    # Create config with custom tow threshold
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        tow_surge_threshold=10,  # High threshold
    )

    # Create test date and users
    test_date = date.today() + timedelta(days=7)
    user1 = django_user_model.objects.create_user(
        username="pilot1",
        email="pilot1@example.com",
        password="password",
        membership_status="Full Member",
    )

    # Create only 1 tow intent (below threshold=10)
    OpsIntent.objects.create(
        member=user1, date=test_date, available_as=["club"], notes="Tow 1"
    )

    # Mock send_mail to verify it's NOT called
    with patch("duty_roster.views.send_mail") as mock_send_mail:
        maybe_notify_surge_towpilot(test_date)

        # Email should NOT be sent because we're below threshold
        mock_send_mail.assert_not_called()

        # Assignment should not be marked as notified
        assignment = DutyAssignment.objects.get(date=test_date)
        assert assignment.tow_surge_notified is False


# ---------------------------------------------------------------------------
# Tests for _check_surge_instructor_needed / _notify_surge_instructor_needed
# (Issue #646 – surge instructor email bug)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_surge_sends_email_with_three_or_more_accepted_students(
    django_user_model,
):
    """_check_surge_instructor_needed sends email when ≥3 students are accepted."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instructors_email="instructors@test.org",
    )

    test_date = date.today() + timedelta(days=14)
    instructor = django_user_model.objects.create_user(
        username="instr1",
        email="instr1@example.com",
        password="password",
        membership_status="Full Member",
    )
    assignment = DutyAssignment.objects.create(date=test_date, instructor=instructor)

    for i in range(3):
        student = django_user_model.objects.create_user(
            username=f"student_surge_{i}",
            email=f"student_surge_{i}@example.com",
            password="password",
            membership_status="Full Member",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student,
            instructor_response="accepted",
            status="confirmed",
        )

    with patch("duty_roster.views.send_mail") as mock_send_mail:
        mock_send_mail.return_value = 1  # send_mail returns count of messages sent
        _check_surge_instructor_needed(assignment)

        mock_send_mail.assert_called_once()
        assignment.refresh_from_db()
        assert assignment.surge_notified is True


@pytest.mark.django_db
def test_check_surge_does_not_send_when_instructors_email_blank(django_user_model):
    """_check_surge_instructor_needed skips email and leaves surge_notified=False when
    instructors_email is empty."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instructors_email="",  # Blank – misconfigured
    )

    test_date = date.today() + timedelta(days=15)
    instructor = django_user_model.objects.create_user(
        username="instr_blank",
        email="instr_blank@example.com",
        password="password",
        membership_status="Full Member",
    )
    assignment = DutyAssignment.objects.create(date=test_date, instructor=instructor)

    for i in range(3):
        student = django_user_model.objects.create_user(
            username=f"student_blank_{i}",
            email=f"student_blank_{i}@example.com",
            password="password",
            membership_status="Full Member",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student,
            instructor_response="accepted",
            status="confirmed",
        )

    with patch("duty_roster.views.send_mail") as mock_send_mail:
        _check_surge_instructor_needed(assignment)

        mock_send_mail.assert_not_called()
        assignment.refresh_from_db()
        assert assignment.surge_notified is False


@pytest.mark.django_db
def test_notify_surge_returns_true_on_success(django_user_model):
    """_notify_surge_instructor_needed returns True when send_mail succeeds."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instructors_email="instructors@test.org",
    )

    test_date = date.today() + timedelta(days=16)
    assignment = DutyAssignment.objects.create(date=test_date)

    with patch("duty_roster.views.send_mail") as mock_send_mail:
        mock_send_mail.return_value = 1  # send_mail returns count of messages sent
        result = _notify_surge_instructor_needed(assignment, student_count=3)

        assert result is True
        mock_send_mail.assert_called_once()


@pytest.mark.django_db
def test_notify_surge_returns_false_on_smtp_failure(django_user_model):
    """_notify_surge_instructor_needed returns False when send_mail raises, and
    the caller must NOT set surge_notified=True in that case."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instructors_email="instructors@test.org",
    )

    test_date = date.today() + timedelta(days=17)
    instructor = django_user_model.objects.create_user(
        username="instr_fail",
        email="instr_fail@example.com",
        password="password",
        membership_status="Full Member",
    )
    assignment = DutyAssignment.objects.create(date=test_date, instructor=instructor)

    # Simulate SMTP failure by making send_mail raise
    with patch("duty_roster.views.send_mail", side_effect=Exception("SMTP error")):
        result = _notify_surge_instructor_needed(assignment, student_count=3)

        assert result is False
        assignment.refresh_from_db()
        # Caller should not have set surge_notified; verify the flag is still False
        assert assignment.surge_notified is False


@pytest.mark.django_db
def test_check_surge_does_not_resend_when_already_notified(django_user_model):
    """_check_surge_instructor_needed does not send a second email when
    surge_notified is already True."""
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.org",
        club_abbreviation="TC",
        instructors_email="instructors@test.org",
    )

    test_date = date.today() + timedelta(days=18)
    instructor = django_user_model.objects.create_user(
        username="instr_resend",
        email="instr_resend@example.com",
        password="password",
        membership_status="Full Member",
    )
    # Pre-set surge_notified to True to simulate an already-notified assignment
    assignment = DutyAssignment.objects.create(
        date=test_date, instructor=instructor, surge_notified=True
    )

    for i in range(3):
        student = django_user_model.objects.create_user(
            username=f"student_resend_{i}",
            email=f"student_resend_{i}@example.com",
            password="password",
            membership_status="Full Member",
        )
        InstructionSlot.objects.create(
            assignment=assignment,
            student=student,
            instructor_response="accepted",
            status="confirmed",
        )

    with patch("duty_roster.views.send_mail") as mock_send_mail:
        _check_surge_instructor_needed(assignment)

        mock_send_mail.assert_not_called()
