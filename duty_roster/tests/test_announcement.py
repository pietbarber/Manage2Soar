"""Tests for Duty Roster announcement feature (Issue #333)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus, SiteConfiguration

User = get_user_model()


@pytest.fixture
def membership_statuses(db):
    """Create necessary membership statuses."""
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True, "sort_order": 10}
    )


@pytest.fixture
def siteconfig(db):
    """Get or create SiteConfiguration for testing."""
    config, _ = SiteConfiguration.objects.get_or_create(
        defaults={
            "club_name": "Test Club",
            "domain_name": "test.org",
            "club_abbreviation": "TC",
            "duty_roster_announcement": "",
        }
    )
    # Always reset announcement to blank for test isolation
    config.duty_roster_announcement = ""
    config.save()
    return config


@pytest.fixture
def active_member(db, membership_statuses, siteconfig):
    """Create an active member user."""
    user = Member.objects.create_user(
        username="testmember",
        email="member@test.org",
        password="testpass123",
        first_name="Test",
        last_name="Member",
        membership_status="Full Member",
    )
    return user


@pytest.mark.django_db
class TestDutyRosterAnnouncement:
    """Tests for duty roster announcement model field."""

    def test_announcement_field_exists(self, siteconfig):
        """Test that duty_roster_announcement field exists on SiteConfiguration."""
        assert hasattr(siteconfig, "duty_roster_announcement")
        assert siteconfig.duty_roster_announcement == ""

    def test_announcement_can_be_saved(self, siteconfig):
        """Test that announcement can be saved and retrieved."""
        siteconfig.duty_roster_announcement = "Test announcement message"
        siteconfig.save()
        siteconfig.refresh_from_db()
        assert siteconfig.duty_roster_announcement == "Test announcement message"

    def test_announcement_allows_blank(self, siteconfig):
        """Test that announcement field can be blank."""
        siteconfig.duty_roster_announcement = ""
        siteconfig.full_clean()  # Should not raise
        siteconfig.save()
        assert siteconfig.duty_roster_announcement == ""

    def test_announcement_supports_multiline(self, siteconfig):
        """Test that announcement supports multiline text."""
        multiline = "Line 1\nLine 2\nLine 3"
        siteconfig.duty_roster_announcement = multiline
        siteconfig.save()
        siteconfig.refresh_from_db()
        assert siteconfig.duty_roster_announcement == multiline


@pytest.mark.django_db
class TestDutyRosterCalendarWithAnnouncement:
    """Tests for duty roster calendar view with announcements.

    Note: As of Issue #551, the calendar uses DutyRosterMessage model
    instead of the deprecated siteconfig.duty_roster_announcement field.
    """

    def test_calendar_loads_without_announcement(
        self, client, active_member, siteconfig
    ):
        """Test that calendar loads when there's no announcement."""
        # Ensure no DutyRosterMessage exists
        from duty_roster.models import DutyRosterMessage

        DutyRosterMessage.objects.all().delete()

        client.force_login(active_member)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)
        assert response.status_code == 200
        # Should NOT contain announcement alert when empty
        assert b"Roster Manager Announcement" not in response.content

    def test_calendar_displays_announcement(
        self, client, membership_statuses, siteconfig
    ):
        """Test that calendar displays announcement when set (Issue #551)."""
        from duty_roster.models import DutyRosterMessage

        # Create announcement using new DutyRosterMessage model
        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="<p>Important: Schedule change for next weekend!</p>",
            is_active=True,
        )

        # Create active member
        user = Member.objects.create_user(
            username="testmember2",
            email="member2@test.org",
            password="testpass123",
            first_name="Test",
            last_name="Member2",
            membership_status="Full Member",
        )

        client.force_login(user)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)
        assert response.status_code == 200
        # Should contain the announcement text
        assert b"Important: Schedule change for next weekend!" in response.content
        # Should contain megaphone icon
        assert b"bi-megaphone" in response.content

    def test_announcement_has_roster_manager_label(
        self, client, membership_statuses, siteconfig
    ):
        """Test that announcement shows 'Roster Manager Announcement' label (Issue #551)."""
        from duty_roster.models import DutyRosterMessage

        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="<p>Test announcement</p>",
            is_active=True,
        )

        user = Member.objects.create_user(
            username="testmember3",
            email="member3@test.org",
            password="testpass123",
            first_name="Test",
            last_name="Member3",
            membership_status="Full Member",
        )

        client.force_login(user)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Roster Manager Announcement" in response.content

    def test_rich_html_announcement_renders_correctly(
        self, client, membership_statuses, siteconfig
    ):
        """Test that rich HTML announcements render correctly (Issue #551)."""
        from duty_roster.models import DutyRosterMessage

        DutyRosterMessage.objects.all().delete()
        # Set HTML content with formatting
        DutyRosterMessage.objects.create(
            content="<p><strong>Line 1</strong></p><p>Line 2</p><p>Line 3</p>",
            is_active=True,
        )

        user = Member.objects.create_user(
            username="testmember_multiline",
            email="multiline@test.org",
            password="testpass123",
            first_name="Test",
            last_name="Multiline",
            membership_status="Full Member",
        )

        client.force_login(user)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # Should contain the HTML rendered
        assert "<strong>Line 1</strong>" in content
        assert "Line 2" in content
        assert "Line 3" in content

    def test_announcement_inactive_not_displayed(
        self, client, membership_statuses, siteconfig
    ):
        """Test that inactive announcements are not displayed (Issue #551)."""
        from duty_roster.models import DutyRosterMessage

        DutyRosterMessage.objects.all().delete()
        DutyRosterMessage.objects.create(
            content="<p>This should be hidden</p>",
            is_active=False,
        )

        user = Member.objects.create_user(
            username="testmember_inactive",
            email="inactive@test.org",
            password="testpass123",
            first_name="Test",
            last_name="Inactive",
            membership_status="Full Member",
        )

        client.force_login(user)
        url = reverse("duty_roster:duty_calendar")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # Should NOT contain the hidden message
        assert "This should be hidden" not in content


@pytest.mark.django_db
class TestCalendarDayModal:
    """Tests for the Bootstrap 5 styled calendar day modal."""

    def test_modal_uses_bootstrap_icons(self, client, membership_statuses, siteconfig):
        """Test that modal uses Bootstrap icons instead of emojis."""
        user = Member.objects.create_user(
            username="testmember4",
            email="member4@test.org",
            password="testpass123",
            first_name="Test",
            last_name="Member4",
            membership_status="Full Member",
        )

        client.force_login(user)

        # Get today's date for the modal URL
        from datetime import date

        today = date.today()
        url = reverse(
            "duty_roster:calendar_day_detail",
            kwargs={"year": today.year, "month": today.month, "day": today.day},
        )
        response = client.get(url)
        assert response.status_code == 200
        # Should contain Bootstrap icons (bi- prefix)
        content = response.content.decode("utf-8")
        assert "bi-" in content
        # Should NOT contain emoji characters (checking common ones used before)
        assert "✈️" not in content
        assert "📋" not in content
        assert "🎓" not in content
