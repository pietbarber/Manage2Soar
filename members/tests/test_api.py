"""Tests for the email lists API endpoint."""

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from members.models import Member
from siteconfig.models import MailingList, MailingListCriterion, MembershipStatus


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
def default_mailing_lists(db):
    """Create default mailing lists for API tests."""
    MailingList.objects.get_or_create(
        name="members",
        defaults={
            "criteria": [MailingListCriterion.ACTIVE_MEMBER],
            "is_active": True,
            "sort_order": 10,
        },
    )
    MailingList.objects.get_or_create(
        name="instructors",
        defaults={
            "criteria": [MailingListCriterion.INSTRUCTOR],
            "is_active": True,
            "sort_order": 20,
        },
    )
    MailingList.objects.get_or_create(
        name="towpilots",
        defaults={
            "criteria": [MailingListCriterion.TOWPILOT],
            "is_active": True,
            "sort_order": 30,
        },
    )
    MailingList.objects.get_or_create(
        name="board",
        defaults={
            "criteria": [
                MailingListCriterion.DIRECTOR,
                MailingListCriterion.SECRETARY,
                MailingListCriterion.TREASURER,
            ],
            "is_active": True,
            "sort_order": 40,
        },
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
    def test_requires_api_key(self, api_client, default_mailing_lists):
        """Test that the endpoint requires an API key."""
        url = reverse("api_email_lists")
        response = api_client.get(url)
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid or missing API key"

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_rejects_wrong_api_key(self, api_client, default_mailing_lists):
        """Test that the endpoint rejects wrong API keys."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="wrong-key")
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid or missing API key"

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_accepts_valid_api_key(
        self, api_client, active_member, default_mailing_lists
    ):
        """Test that the endpoint accepts a valid API key."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        assert response.status_code == 200
        data = response.json()
        assert "lists" in data
        assert "whitelist" in data

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_active_members(
        self, api_client, active_member, inactive_member, default_mailing_lists
    ):
        """Test that only active members are included."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert active_member.email in data["lists"]["members"]
        assert inactive_member.email not in data["lists"]["members"]
        assert active_member.email in data["whitelist"]
        assert inactive_member.email not in data["whitelist"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_instructors(
        self, api_client, active_member, instructor_member, default_mailing_lists
    ):
        """Test that instructors are in the instructors list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert instructor_member.email in data["lists"]["instructors"]
        assert active_member.email not in data["lists"]["instructors"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_towpilots(
        self, api_client, active_member, towpilot_member, default_mailing_lists
    ):
        """Test that towpilots are in the towpilots list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert towpilot_member.email in data["lists"]["towpilots"]
        assert active_member.email not in data["lists"]["towpilots"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_returns_board_members(
        self, api_client, active_member, board_member, default_mailing_lists
    ):
        """Test that board members (treasurer) are in the board list."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert board_member.email in data["lists"]["board"]
        assert active_member.email not in data["lists"]["board"]

    @override_settings(M2S_MAIL_API_KEY="")
    def test_fails_when_api_key_not_configured(self, api_client, default_mailing_lists):
        """Test that the endpoint fails gracefully when API key is not set."""
        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="any-key")
        assert response.status_code == 500
        assert "not configured" in response.json()["error"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_post_not_allowed(self, api_client, default_mailing_lists):
        """Test that POST requests are not allowed."""
        url = reverse("api_email_lists")
        response = api_client.post(url, HTTP_X_API_KEY="test-api-key-12345")
        assert response.status_code == 405  # Method Not Allowed

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_members_without_email_excluded(
        self, api_client, active_member, membership_statuses, default_mailing_lists
    ):
        """Test that members with empty email addresses are excluded from all lists."""
        # Create members with no email but various roles
        Member.objects.create_user(
            username="noemail_user",
            email="",  # Empty email
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
        )
        Member.objects.create_user(
            username="noemail_instructor",
            email="",  # Empty email
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
        )
        Member.objects.create_user(
            username="noemail_towpilot",
            email="",  # Empty email
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            towpilot=True,
        )
        Member.objects.create_user(
            username="noemail_board",
            email="",  # Empty email
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            treasurer=True,  # Board member role
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        # No empty strings should appear in any list
        assert all(email != "" for email in data["lists"]["members"])
        assert all(email != "" for email in data["lists"]["instructors"])
        assert all(email != "" for email in data["lists"]["towpilots"])
        assert all(email != "" for email in data["lists"]["board"])
        assert all(email != "" for email in data["whitelist"])

        # Active member with email should still be present
        assert active_member.email in data["lists"]["members"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_inactive_lists_not_returned(
        self, api_client, active_member, membership_statuses
    ):
        """Test that inactive mailing lists are not included in API response."""
        # Create one active and one inactive list
        MailingList.objects.create(
            name="active-list",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
            is_active=True,
        )
        MailingList.objects.create(
            name="inactive-list",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
            is_active=False,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "active-list" in data["lists"]
        assert "inactive-list" not in data["lists"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_custom_mailing_list(self, api_client, membership_statuses):
        """Test that custom mailing lists with multiple criteria work correctly."""
        # Create members
        instructor = Member.objects.create_user(
            username="custom_instructor",
            email="custom_instructor@example.com",
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
        )
        do = Member.objects.create_user(
            username="custom_do",
            email="custom_do@example.com",
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
            duty_officer=True,
        )
        regular = Member.objects.create_user(
            username="custom_regular",
            email="custom_regular@example.com",
            password="testpass123",
            membership_status="Full Member",
            is_active=True,
        )

        # Create a custom list with multiple criteria (OR logic)
        MailingList.objects.create(
            name="operations-team",
            criteria=[
                MailingListCriterion.INSTRUCTOR,
                MailingListCriterion.DUTY_OFFICER,
            ],
            is_active=True,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        # Both instructor and duty officer should be in the custom list
        assert instructor.email in data["lists"]["operations-team"]
        assert do.email in data["lists"]["operations-team"]
        # Regular member should not be
        assert regular.email not in data["lists"]["operations-team"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_bypass_lists_returned(self, api_client, membership_statuses):
        """Test that lists with bypass_whitelist=True are in bypass_lists."""
        # Create a list with bypass_whitelist=True
        MailingList.objects.create(
            name="treasurer",
            criteria=[MailingListCriterion.TREASURER],
            is_active=True,
            bypass_whitelist=True,
        )
        # Create a normal list (bypass_whitelist=False by default)
        MailingList.objects.create(
            name="members",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
            is_active=True,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "bypass_lists" in data
        assert "treasurer" in data["bypass_lists"]
        assert "members" not in data["bypass_lists"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_inactive_bypass_list_not_returned(self, api_client, membership_statuses):
        """Test that inactive lists with bypass_whitelist=True are not returned."""
        MailingList.objects.create(
            name="inactive-bypass",
            criteria=[MailingListCriterion.TREASURER],
            is_active=False,
            bypass_whitelist=True,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "inactive-bypass" not in data["bypass_lists"]
        assert "inactive-bypass" not in data["lists"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_manual_whitelist_included(self, api_client, membership_statuses):
        """Test that manual whitelist entries are included in whitelist."""
        from siteconfig.models import SiteConfiguration

        # Create a SiteConfiguration with manual whitelist
        SiteConfiguration.objects.create(
            club_name="Test Club",
            manual_whitelist="bob@example.com\ncarol@example.com",
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "bob@example.com" in data["whitelist"]
        assert "carol@example.com" in data["whitelist"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_manual_whitelist_handles_empty_lines(
        self, api_client, membership_statuses
    ):
        """Test that manual whitelist handles empty lines and whitespace."""
        from siteconfig.models import SiteConfiguration

        # Create a SiteConfiguration with messy whitelist
        SiteConfiguration.objects.create(
            club_name="Test Club",
            manual_whitelist="""
                bob@example.com

                carol@example.com
                invalid-not-an-email
                  spaced@example.com
            """,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "bob@example.com" in data["whitelist"]
        assert "carol@example.com" in data["whitelist"]
        assert "spaced@example.com" in data["whitelist"]
        # Invalid entries (no @) should be filtered out
        assert "invalid-not-an-email" not in data["whitelist"]
        # Empty strings should not be present
        assert "" not in data["whitelist"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_manual_whitelist_combined_with_members(
        self, api_client, active_member, membership_statuses
    ):
        """Test that manual whitelist is combined with member emails."""
        from siteconfig.models import SiteConfiguration

        SiteConfiguration.objects.create(
            club_name="Test Club",
            manual_whitelist="external@example.com",
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        # Both member and manual whitelist should be present
        assert active_member.email in data["whitelist"]
        assert "external@example.com" in data["whitelist"]

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_manual_whitelist_deduplicates(
        self, api_client, active_member, membership_statuses
    ):
        """Test that duplicate emails in whitelist are deduplicated."""
        from siteconfig.models import SiteConfiguration

        # Add active_member's email to manual whitelist (should dedupe)
        SiteConfiguration.objects.create(
            club_name="Test Club",
            manual_whitelist=f"{active_member.email}\n{active_member.email}",
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        # Should only appear once
        count = data["whitelist"].count(active_member.email.lower())
        assert count == 1

    @override_settings(M2S_MAIL_API_KEY="test-api-key-12345")
    def test_empty_bypass_lists_when_none_enabled(
        self, api_client, membership_statuses
    ):
        """Test that bypass_lists is an empty array when no lists have bypass enabled."""
        # Create normal lists without bypass_whitelist
        MailingList.objects.create(
            name="members",
            criteria=[MailingListCriterion.ACTIVE_MEMBER],
            is_active=True,
        )
        MailingList.objects.create(
            name="instructors",
            criteria=[MailingListCriterion.INSTRUCTOR],
            is_active=True,
        )

        url = reverse("api_email_lists")
        response = api_client.get(url, HTTP_X_API_KEY="test-api-key-12345")
        data = response.json()

        assert "bypass_lists" in data
        assert data["bypass_lists"] == []
        assert isinstance(data["bypass_lists"], list)
