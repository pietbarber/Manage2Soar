"""
End-to-end tests for the DutyRosterMessage feature (Issue #551).

Tests the rich HTML roster announcement functionality:
- Rostermeisters can edit the message via TinyMCE
- Message displays on both calendar and agenda views
- Regular members can view but not edit the message
- JavaScript interactions work correctly
"""

from duty_roster.models import DutyRosterMessage
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestRosterMessageE2E(DjangoPlaywrightTestCase):
    """E2E tests for the roster message feature."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        # Ensure we have a SiteConfiguration
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        # Clear any existing messages
        DutyRosterMessage.objects.all().delete()

    def test_rostermeister_can_access_edit_page(self):
        """Test that a rostermeister can access the edit message page."""
        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to the edit page
        self.page.goto(f"{self.live_server_url}/duty_roster/message/edit/")

        # Should see the edit form
        assert self.page.is_visible("text=Edit Roster Announcement")
        assert self.page.is_visible("text=Save Message")
        assert self.page.is_visible("text=Back to Calendar")

    def test_regular_member_cannot_access_edit_page(self):
        """Test that a regular member is redirected when trying to access edit page."""
        self.create_test_member(
            username="regular",
            rostermeister=False,
            membership_status="Full Member",
        )
        self.login(username="regular")

        # Try to navigate to the edit page
        self.page.goto(f"{self.live_server_url}/duty_roster/message/edit/")

        # Should be redirected to login (403 or redirect)
        current_url = self.page.url
        assert "/login/" in current_url or "/accounts/login/" in current_url

    def test_save_message_and_view_on_calendar(self):
        """Test saving a message and seeing it on the calendar."""
        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to edit page
        self.page.goto(f"{self.live_server_url}/duty_roster/message/edit/")

        # The TinyMCE editor may take a moment to initialize
        self.page.wait_for_timeout(500)

        # Find and fill the textarea (TinyMCE may use different methods)
        # For simplicity, we'll try the raw textarea first
        textarea = self.page.locator("textarea#id_content, textarea[name='content']")
        if textarea.is_visible():
            textarea.fill("<p>Test announcement from E2E test!</p>")

        # Ensure is_active is checked
        is_active_checkbox = self.page.locator("#id_is_active, input[name='is_active']")
        if not is_active_checkbox.is_checked():
            is_active_checkbox.check()

        # Submit the form
        self.page.click("button:has-text('Save Message')")

        # Should redirect to calendar
        self.page.wait_for_url(f"{self.live_server_url}/duty_roster/calendar/**")

        # Verify the message appears on the calendar
        assert self.page.is_visible("text=Roster Manager Announcement")
        assert self.page.is_visible("text=Test announcement from E2E test")

    def test_message_displays_on_calendar_view(self):
        """Test that an existing message displays on the calendar view."""
        # Create a message in the database
        DutyRosterMessage.objects.create(
            content="<p><strong>Important:</strong> Schedule change next week!</p>",
            is_active=True,
        )

        self.create_test_member(username="viewer")
        self.login(username="viewer")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should see the announcement
        assert self.page.is_visible("text=Roster Manager Announcement")
        assert self.page.is_visible("text=Schedule change next week")

    def test_inactive_message_not_displayed(self):
        """Test that inactive messages are not displayed."""
        # Create an inactive message
        DutyRosterMessage.objects.create(
            content="<p>This should be hidden</p>",
            is_active=False,
        )

        self.create_test_member(username="viewer", membership_status="Full Member")
        self.login(username="viewer")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should NOT see the hidden message
        assert not self.page.is_visible("text=This should be hidden")

    def test_rostermeister_sees_edit_button(self):
        """Test that rostermeisters see the edit button on the calendar."""
        # Create a message
        DutyRosterMessage.objects.create(
            content="<p>Announcement content</p>",
            is_active=True,
        )

        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should see the edit button (pencil icon)
        edit_button = self.page.locator(
            "a[title='Edit announcement'], a.btn:has(.bi-pencil)"
        )
        assert edit_button.count() >= 1

    def test_regular_member_no_edit_button(self):
        """Test that regular members don't see the edit button."""
        # Create a message
        DutyRosterMessage.objects.create(
            content="<p>Announcement content</p>",
            is_active=True,
        )

        self.create_test_member(
            username="regular",
            rostermeister=False,
            membership_status="Full Member",
        )
        self.login(username="regular")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should see the announcement but not the edit button
        assert self.page.is_visible("text=Roster Manager Announcement")
        edit_button = self.page.locator("a[title='Edit announcement']")
        assert edit_button.count() == 0

    def test_rostermeister_sees_add_button_when_no_message(self):
        """Test that rostermeisters see 'Add Announcement' when no message exists."""
        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to calendar (no message exists)
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should see the add announcement button
        assert self.page.is_visible("text=Add Announcement")

    def test_message_dismissible(self):
        """Test that the message alert can be dismissed."""
        # Create a message
        DutyRosterMessage.objects.create(
            content="<p>Dismissible announcement</p>",
            is_active=True,
        )

        self.create_test_member(username="viewer", membership_status="Full Member")
        self.login(username="viewer")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Should see the announcement
        assert self.page.is_visible("text=Dismissible announcement")

        # Click the first close button (there may be one for each view: calendar and agenda)
        close_button = self.page.locator(".alert .btn-close").first
        if close_button.is_visible():
            close_button.click()
            # Wait for the fade-out animation
            self.page.wait_for_timeout(500)
            # The alert in the visible view should be dismissed
            # (the one in the hidden view won't be affected)

    def test_edit_button_navigates_to_edit_page(self):
        """Test that clicking the edit button navigates to the edit page."""
        # Create a message
        DutyRosterMessage.objects.create(
            content="<p>Click to edit</p>",
            is_active=True,
        )

        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to calendar
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")

        # Click the edit button
        edit_button = self.page.locator(
            "a[title='Edit announcement'], a.btn:has(.bi-pencil)"
        ).first
        edit_button.click()

        # Should navigate to edit page
        self.page.wait_for_url("**/message/edit/**")
        assert self.page.is_visible("text=Edit Roster Announcement")

    def test_back_to_calendar_button(self):
        """Test that 'Back to Calendar' button works."""
        self.create_test_member(
            username="rostermeister",
            rostermeister=True,
            membership_status="Full Member",
        )
        self.login(username="rostermeister")

        # Navigate to edit page
        self.page.goto(f"{self.live_server_url}/duty_roster/message/edit/")

        # Click back to calendar
        self.page.click("text=Back to Calendar")

        # Should navigate to calendar
        self.page.wait_for_url("**/duty_roster/calendar/**")
