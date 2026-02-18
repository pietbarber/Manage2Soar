"""
E2E tests for duty roster calendar announcement display.

Issue #638: Verify announcement renders exactly once when toggling between
Calendar and Agenda views, and that it is dismissible.
"""

from datetime import date

from duty_roster.models import DutyAssignment, DutyRosterMessage

from .conftest import DjangoPlaywrightTestCase


class TestDutyRosterAnnouncement(DjangoPlaywrightTestCase):
    """Test announcement display in duty roster calendar."""

    def test_announcement_appears_once_in_calendar_view(self):
        """Test that announcement appears exactly once in calendar view."""
        # Create rostermeister to create announcement
        rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            rostermeister=True,
        )

        # Get or create announcement (singleton model)
        message = DutyRosterMessage.get_or_create_message()
        message.content = "<p>Test announcement content</p>"
        message.is_active = True
        message.updated_by = rostermeister
        message.save()

        # Login as regular member
        _ = self.create_test_member(username="testmember", email="test@example.com")
        self.login(username="testmember")

        # Navigate to duty roster calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Wait for page to load
        self.page.wait_for_selector(".alert.alert-info")

        # Count announcement blocks
        announcements = self.page.locator(
            ".alert.alert-info:has-text('Roster Manager Announcement')"
        )
        count = announcements.count()

        assert (
            count == 1
        ), f"Expected exactly 1 announcement in calendar view, found {count}"

    def test_announcement_appears_once_in_agenda_view(self):
        """Test that announcement appears exactly once in agenda view (Issue #638)."""
        # Create rostermeister to create announcement
        rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            rostermeister=True,
        )

        # Get or create announcement (singleton model)
        message = DutyRosterMessage.get_or_create_message()
        message.content = "<p>Important roster update</p>"
        message.is_active = True
        message.updated_by = rostermeister
        message.save()

        # Create a duty assignment so agenda view has content
        today = date.today()
        instructor = self.create_test_member(
            username="instructor",
            email="instructor@example.com",
            instructor=True,
        )
        DutyAssignment.objects.create(
            date=today,
            instructor=instructor,
        )

        # Login as regular member
        _ = self.create_test_member(username="testmember", email="test@example.com")
        self.login(username="testmember")

        # Navigate to duty roster calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Wait for page to load
        self.page.wait_for_selector('label[for="agenda-view"]')

        # Switch to Agenda view by clicking the label
        agenda_label = self.page.locator('label[for="agenda-view"]')
        agenda_label.click()

        # Wait for agenda view to be visible
        self.page.wait_for_selector("#agenda-view-content", state="visible")

        # Count announcement blocks (should be exactly 1, not duplicated)
        announcements = self.page.locator(
            ".alert.alert-info:has-text('Roster Manager Announcement')"
        )
        count = announcements.count()

        assert (
            count == 1
        ), f"Expected exactly 1 announcement in agenda view, found {count} (Issue #638: duplicate removed)"

    def test_announcement_is_dismissible(self):
        """Test that announcement can be dismissed via close button."""
        # Create rostermeister to create announcement
        rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            rostermeister=True,
        )

        # Get or create announcement (singleton model)
        message = DutyRosterMessage.get_or_create_message()
        message.content = "<p>Dismissible announcement</p>"
        message.is_active = True
        message.updated_by = rostermeister
        message.save()

        # Login as regular member
        _ = self.create_test_member(username="testmember", email="test@example.com")
        self.login(username="testmember")

        # Navigate to duty roster calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Wait for announcement to appear
        announcement = self.page.locator(
            ".alert.alert-info:has-text('Roster Manager Announcement')"
        )
        announcement.wait_for(state="visible")

        # Verify announcement is visible
        assert announcement.is_visible(), "Announcement should be visible initially"

        # Click the close button
        close_button = announcement.locator(".btn-close")
        close_button.click()

        # Wait for dismissal animation
        self.page.wait_for_timeout(500)

        # Verify announcement is no longer visible
        assert not announcement.is_visible(), "Announcement should be dismissed"

    def test_no_announcement_when_inactive(self):
        """Test that inactive announcements are not displayed."""
        # Create rostermeister to create announcement
        rostermeister = self.create_test_member(
            username="rostermeister",
            email="roster@example.com",
            rostermeister=True,
        )

        # Get or create INACTIVE announcement (singleton model)
        message = DutyRosterMessage.get_or_create_message()
        message.content = "<p>Inactive announcement</p>"
        message.is_active = False
        message.updated_by = rostermeister
        message.save()

        # Login as regular member
        _ = self.create_test_member(username="testmember", email="test@example.com")
        self.login(username="testmember")

        # Navigate to duty roster calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Wait for page to load
        self.page.wait_for_selector("h3:has-text('📅')")

        # Count announcement blocks (should be 0)
        announcements = self.page.locator(
            ".alert.alert-info:has-text('Roster Manager Announcement')"
        )
        count = announcements.count()

        assert count == 0, f"Expected 0 announcements when inactive, found {count}"
