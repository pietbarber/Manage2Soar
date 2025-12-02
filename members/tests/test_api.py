"""Tests for the email lists API endpoint."""

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.fixture
def membership_statuses(db):
    """Create required membership statuses for testing."""
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True, "sort_order": 1}
    )
    MembershipStatus.objects.get_or_create(
        name="Non-Member", defaults={"is_active": False, "sort_order": 100}
    )


@pytest.fixture
def api_client():
    """Return a Django test client."""
    return Client()


@pytest.fixture
def active_member(db, membership_statuses):
    """Create an active member for testing."""
    return Member.objects.create_user(
        username="testmember",
        email="testmember@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_active=True,
    )


@pytest.fixture
def instructor_member(db, membership_statuses):
    """Create an instructor for testing."""
    return Member.objects.create_user(
        username="testinstructor",
        email="instructor@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_active=True,
        instructor=True,
    )


@pytest.fixture
def towpilot_member(db, membership_statuses):
    """Create a towpilot for testing."""
    return Member.objects.create_user(
        username="testtowpilot",
        email="towpilot@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_active=True,
        towpilot=True,
    )


@pytest.fixture
def board_member(db, membership_statuses):
    """Create a board member (treasurer) for testing."""
    return Member.objects.create_user(
        username="testtreasurer",
        email="treasurer@example.com",
        password="testpass123",
        membership_status="Full Member",
        is_active=True,
        treasurer=True,
    )


@pytest.fixture
def inactive_member(db, membership_statuses):
    """Create an inactive member for testing."""
    return Member.objects.create_user(
        username="inactivemember",
        email="inactive@example.com",
        password="testpass123",
        membership_status="Non-Member",
        is_active=True,
    )


@pytest.mark.django_db
class TestEmailListsAPI:
    """Tests for the /api/email-lists/ endpoint."""

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_requires_api_key(self, api_client):
        """Test that the endpoint requires an API key."""
        url = reverse("api_email_lists")
        response = api_client.get(url)
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid or missing API key"

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_rejects_wrong_api_key(self, api_client):
        """Test that the endpoint rejects wrong API keys."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="wrong-key")
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid or missing API key"

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_accepts_valid_api_key(self, api_client, active_member):
        """Test that the endpoint accepts a valid API key."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        assert response.status_code == 200
        data = response.json()
        assert "lists" in data
        assert "whitelist" in data

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_active_members(self, api_client, active_member, inactive_member):
        """Test that only active members are included."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert active_member.email in data["lists"]["members"]
        assert inactive_member.email not in data["lists"]["members"]
        assert active_member.email in data["whitelist"]
        assert inactive_member.email not in data["whitelist"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_instructors(self, api_client, active_member, instructor_member):
        """Test that instructors are in the instructors list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert instructor_member.email in data["lists"]["instructors"]
        assert active_member.email not in data["lists"]["instructors"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_towpilots(self, api_client, active_member, towpilot_member):
        """Test that towpilots are in the towpilots list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert towpilot_member.email in data["lists"]["towpilots"]
        assert active_member.email not in data["lists"]["towpilots"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_board_members(self, api_client, active_member, board_member):
        """Test that board members (treasurer) are in the board list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert board_member.email in data["lists"]["board"]
        assert active_member.email not in data["lists"]["board"]

    @override_settings(M2S_MAIL_API_KEY="")
    def test_fails_when_api_key_not_configured(self, api_client):
        """Test that the endpoint fails gracefully when API key is not set."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="any-key")
        assert response.status_code == 500
        assert "not configured" in response.json()["error"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_post_not_allowed(self, api_client):
        """Test that POST requests are not allowed."""
        url = reverse("api_email_lists")
        response = api_client.post(url, HTTP_X_API_KEY="test-api-key-12345")
        assert response.status_code == 405  # Method Not Allowed
