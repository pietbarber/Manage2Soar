"""
Tests for configurable surge thresholds (Issue #403).
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, OpsIntent
from duty_roster.views import get_surge_thresholds
from siteconfig.models import SiteConfiguration


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
    config = SiteConfiguration.objects.create(
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
    config = SiteConfiguration.objects.create(
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
    config = SiteConfiguration.objects.create(
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
    config = SiteConfiguration.objects.create(
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
    config = SiteConfiguration.objects.create(
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
