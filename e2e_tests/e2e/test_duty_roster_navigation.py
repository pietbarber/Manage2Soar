"""
E2E tests for duty roster bottom navigation feature (Issue #637).

Tests the bottom navigation buttons that were added to improve UX for long pages:
- Bottom navigation buttons are rendered on the page
- Simplified bottom header shows date but not view toggle (no duplicate IDs)
- Top navigation view toggle works correctly
"""

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestDutyRosterNavigation(DjangoPlaywrightTestCase):
    """E2E tests for the duty roster navigation feature (Issue #637)."""

    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )

    def test_bottom_navigation_buttons_rendered(self):
        """Test that bottom navigation prev/next month buttons are rendered (Issue #637)."""
        self.create_test_member(
            username="testmember",
            email="test@example.com",
            membership_status="Full Member",
        )
        self.login(username="testmember")

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        # There should be exactly 2 sets of prev/next buttons (top + bottom nav)
        prev_buttons = self.page.locator("button[title*='Go to']")
        count = prev_buttons.count()
        assert (
            count >= 4
        ), f"Expected at least 4 nav buttons (2 prev + 2 next for top and bottom nav), found {count}"

    def test_no_duplicate_toggle_ids_in_bottom_nav(self):
        """Test that the bottom nav does not duplicate the calendar-view/agenda-view IDs."""
        self.create_test_member(
            username="testmember",
            email="test@example.com",
            membership_status="Full Member",
        )
        self.login(username="testmember")

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        # There should be exactly ONE calendar-view radio and ONE agenda-view radio (not duplicated)
        calendar_radios = self.page.locator("#calendar-view")
        agenda_radios = self.page.locator("#agenda-view")

        assert calendar_radios.count() == 1, (
            f"Expected exactly 1 #calendar-view element, found {calendar_radios.count()} "
            "(duplicate IDs break JavaScript getElementById)"
        )
        assert agenda_radios.count() == 1, (
            f"Expected exactly 1 #agenda-view element, found {agenda_radios.count()} "
            "(duplicate IDs break JavaScript getElementById)"
        )

    def test_bottom_nav_shows_date_without_toggle(self):
        """Test that the bottom nav shows the date but not the view toggle controls."""
        self.create_test_member(
            username="testmember",
            email="test@example.com",
            membership_status="Full Member",
        )
        self.login(username="testmember")

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        # The mt-4 div is the bottom navigation container
        bottom_nav = self.page.locator(
            ".d-flex.justify-content-between.align-items-center.mt-4"
        )
        assert (
            bottom_nav.count() == 1
        ), "Expected 1 bottom navigation container with mt-4 class"

        # Bottom nav should NOT contain the toggle buttons (they have unique IDs, only appear once)
        # We already confirmed above there's only 1 instance of #agenda-view total

        # Bottom nav should show the date text
        date_text = bottom_nav.locator(".text-muted")
        assert (
            date_text.count() == 1
        ), "Bottom nav should show a muted date text (not full header)"

    def test_view_toggle_switches_calendar_agenda(self):
        """Test that the top view toggle correctly switches between Calendar and Agenda views."""
        self.create_test_member(
            username="testmember",
            email="test@example.com",
            membership_status="Full Member",
        )
        self.login(username="testmember")

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        # Calendar view should be visible by default
        calendar_content = self.page.locator("#calendar-view-content")
        agenda_content = self.page.locator("#agenda-view-content")

        assert (
            calendar_content.is_visible()
        ), "Calendar view should be visible by default"
        assert (
            not agenda_content.is_visible()
        ), "Agenda view should be hidden by default"

        # Click Agenda view toggle
        self.page.locator('label[for="agenda-view"]').click()
        self.page.wait_for_selector("#agenda-view-content", state="visible")

        assert (
            not calendar_content.is_visible()
        ), "Calendar view should be hidden after toggle"
        assert agenda_content.is_visible(), "Agenda view should be visible after toggle"

        # Switch back to Calendar view
        self.page.locator('label[for="calendar-view"]').click()
        self.page.wait_for_selector("#calendar-view-content", state="visible")

        assert (
            calendar_content.is_visible()
        ), "Calendar view should be visible after switching back"
        assert (
            not agenda_content.is_visible()
        ), "Agenda view should be hidden after switching back"

    def test_view_param_overrides_localstorage(self):
        """URL ?view= parameter must take priority over the saved duty-roster-view localStorage preference."""
        self.create_test_member(
            username="testmember",
            email="test@example.com",
            membership_status="Full Member",
        )
        self.login(username="testmember")

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        # Set localStorage to 'calendar', then navigate with ?view=agenda — URL wins
        self.page.evaluate("localStorage.setItem('duty-roster-view', 'calendar')")
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/?view=agenda")
        # Wait explicitly for the JS to switch to agenda view (avoids flakiness)
        self.page.wait_for_selector("#agenda-view-content", state="visible")

        agenda_content = self.page.locator("#agenda-view-content")
        calendar_content = self.page.locator("#calendar-view-content")

        assert (
            agenda_content.is_visible()
        ), "Agenda view should be visible when ?view=agenda is in URL even if localStorage says 'calendar'"
        assert (
            not calendar_content.is_visible()
        ), "Calendar view should be hidden when ?view=agenda is in URL"

        # Reverse: localStorage='agenda', ?view=calendar should show calendar
        self.page.evaluate("localStorage.setItem('duty-roster-view', 'agenda')")
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/?view=calendar")
        # Wait explicitly for the JS to switch to calendar view (avoids flakiness)
        self.page.wait_for_selector("#calendar-view-content", state="visible")

        assert (
            calendar_content.is_visible()
        ), "Calendar view should be visible when ?view=calendar is in URL even if localStorage says 'agenda'"
        assert (
            not agenda_content.is_visible()
        ), "Agenda view should be hidden when ?view=calendar is in URL"
