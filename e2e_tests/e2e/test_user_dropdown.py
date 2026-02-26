"""
E2E tests for the "Welcome, [Name]" user dropdown in the navbar.

Covers:
- Dropdown opens and closes correctly (Bootstrap JavaScript)
- All expected links are present and reachable
- Conditional solo/checkride links appear for unrated pilots only
"""

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestUserDropdown(DjangoPlaywrightTestCase):
    """E2E tests for the navbar user dropdown (Welcome, [Name])."""

    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_dropdown(self):
        """Click the user dropdown toggle and wait for it to open."""
        self.page.click("#userDropdown")
        self.page.wait_for_selector(
            ".dropdown-menu[aria-labelledby='userDropdown']", state="visible"
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_dropdown_opens_on_click(self):
        """Clicking the welcome toggle opens the dropdown menu."""
        self.create_test_member(
            username="dropdownmember",
            email="dropdown@example.com",
            membership_status="Full Member",
        )
        self.login(username="dropdownmember")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")

        # Dropdown menu should be hidden initially
        menu = self.page.locator(".dropdown-menu[aria-labelledby='userDropdown']")
        assert not menu.is_visible(), "Dropdown menu should be hidden before clicking"

        # Click the toggle button
        self._open_dropdown()
        assert (
            menu.is_visible()
        ), "Dropdown menu should be visible after clicking toggle"

    def test_dropdown_closes_on_escape(self):
        """Pressing Escape closes the dropdown."""
        self.create_test_member(
            username="dropdownmember",
            email="dropdown@example.com",
            membership_status="Full Member",
        )
        self.login(username="dropdownmember")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")
        self._open_dropdown()

        menu = self.page.locator(".dropdown-menu[aria-labelledby='userDropdown']")
        assert menu.is_visible(), "Dropdown should be open"

        # Press Escape to close the dropdown
        self.page.keyboard.press("Escape")
        self.page.wait_for_selector(
            ".dropdown-menu[aria-labelledby='userDropdown']", state="hidden"
        )
        assert not menu.is_visible(), "Dropdown should be closed after Escape"

    def test_dropdown_contains_profile_links(self):
        """Core personal links are present in the dropdown."""
        member = self.create_test_member(
            username="dropdownmember",
            email="dropdown@example.com",
            membership_status="Full Member",
        )
        self.login(username="dropdownmember")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")
        self._open_dropdown()

        menu = self.page.locator(".dropdown-menu[aria-labelledby='userDropdown']")

        # Profile view and biography links should be present with exact hrefs
        profile_view_link = menu.locator(f"a[href='/members/{member.pk}/view/']")
        assert (
            profile_view_link.count() == 1
        ), "View my Profile link should appear in the dropdown with the correct href"

        biography_link = menu.locator(f"a[href='/members/{member.pk}/biography/']")
        assert (
            biography_link.count() == 1
        ), "Edit my Biography link should appear in the dropdown with the correct href"

        # Training grid link
        training_link = menu.locator(
            f"a[href*='/instructors/training-grid/{member.pk}/']"
        )
        assert (
            training_link.count() == 1
        ), "Training grid link should appear in the dropdown"

        # My Logbook
        logbook_link = menu.locator("a[href*='/instructors/logbook/']")
        assert logbook_link.count() == 1, "Logbook link should appear in the dropdown"

    def test_solo_and_checkride_links_hidden_for_rated_pilot(self):
        """Solo/checkride progress links are NOT shown to pilots with a private rating."""
        self.create_test_member(
            username="ratedpilot",
            email="rated@example.com",
            membership_status="Full Member",
            glider_rating="private",
        )
        self.login(username="ratedpilot")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")
        self._open_dropdown()

        menu = self.page.locator(".dropdown-menu[aria-labelledby='userDropdown']")

        solo_link = menu.locator("a[href*='needed-for-solo']")
        checkride_link = menu.locator("a[href*='needed-for-checkride']")

        assert (
            solo_link.count() == 0
        ), "Solo link should not appear for a rated (private-certificate) pilot"
        assert (
            checkride_link.count() == 0
        ), "Checkride link should not appear for a rated pilot"

    def test_solo_and_checkride_links_shown_for_unrated_pilot(self):
        """Solo/checkride progress links ARE shown to pilots without a glider rating."""
        member = self.create_test_member(
            username="studentpilot",
            email="student@example.com",
            membership_status="Full Member",
            glider_rating="none",
        )
        self.login(username="studentpilot")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")
        self._open_dropdown()

        menu = self.page.locator(".dropdown-menu[aria-labelledby='userDropdown']")

        solo_link = menu.locator(
            f"a[href='/instructors/students/{member.pk}/needed-for-solo/']"
        )
        checkride_link = menu.locator(
            f"a[href='/instructors/students/{member.pk}/needed-for-checkride/']"
        )

        assert (
            solo_link.count() == 1
        ), "Solo progress link should appear for a student pilot"
        assert (
            checkride_link.count() == 1
        ), "Checkride progress link should appear for a student pilot"

    def test_welcome_text_shows_member_name(self):
        """The dropdown toggle shows 'Welcome, [First Name]'."""
        self.create_test_member(
            username="namedpilot",
            first_name="Alice",
            last_name="Soarer",
            email="alice@example.com",
            membership_status="Full Member",
        )
        self.login(username="namedpilot")

        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_selector("#userDropdown")

        toggle_text = self.page.locator("#userDropdown").inner_text()
        assert (
            "Welcome" in toggle_text
        ), f"Dropdown toggle should contain 'Welcome', got: {toggle_text!r}"
        assert (
            "Alice" in toggle_text
        ), f"Dropdown toggle should contain the member's first name, got: {toggle_text!r}"
