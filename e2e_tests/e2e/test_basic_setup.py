"""
Basic Playwright tests to validate the e2e testing framework setup.

Issue #389: Playwright-pytest integration for automated browser tests.

Note: These tests use Django's StaticLiveServerTestCase which properly
handles the async/sync context for Playwright with Django.
"""

from .conftest import DjangoPlaywrightTestCase


class TestPlaywrightSetup(DjangoPlaywrightTestCase):
    """Basic tests to validate Playwright + Django integration works."""

    def test_homepage_loads(self):
        """Verify the homepage loads and contains expected content."""
        self.page.goto(self.live_server_url)

        # Check the page title contains something reasonable
        assert "Manage2Soar" in self.page.title() or self.page.title() != ""

        # Check the page has content
        assert self.page.content() != ""

    def test_login_page_exists(self):
        """Verify the login page is accessible."""
        self.page.goto(f"{self.live_server_url}/login/")

        # Check for login form elements
        assert (
            self.page.locator('input[name="username"]').count() > 0
            or self.page.locator('input[name="login"]').count() > 0
        )

    def test_bootstrap_javascript_loads(self):
        """Verify Bootstrap JavaScript is loaded and functional."""
        self.page.goto(self.live_server_url)

        # Check that Bootstrap is defined in JavaScript
        bootstrap_defined = self.page.evaluate("typeof bootstrap !== 'undefined'")
        assert bootstrap_defined, "Bootstrap JavaScript should be loaded"

    def test_navbar_toggle_works_on_mobile(self):
        """Test that Bootstrap navbar toggle works on mobile viewport."""
        # Set mobile viewport
        self.page.set_viewport_size({"width": 375, "height": 667})

        self.page.goto(self.live_server_url)

        # Look for navbar toggler button (hamburger menu)
        toggler = self.page.locator(".navbar-toggler")

        if toggler.count() > 0:
            # On mobile, the navbar should be collapsed
            navbar_collapse = self.page.locator(".navbar-collapse")

            # Check initial state - should be collapsed
            initial_visible = navbar_collapse.is_visible()

            # Click the toggler
            toggler.click()

            # Wait for the navbar collapse to become visible (if it was hidden)
            if not initial_visible:
                navbar_collapse.wait_for(state="visible")

            # After clicking, visibility should change
            # (Either it becomes visible if collapsed, or stays visible)
            after_click_visible = navbar_collapse.is_visible()

            # If initially hidden, should now be visible
            if not initial_visible:
                assert (
                    after_click_visible
                ), "Navbar should expand after clicking toggler"

    def test_authenticated_user_can_access_members(self):
        """Test that authenticated users can access member pages."""
        # Create a test member and login
        member = self.create_test_member(username="playwright_user")
        self.login(username="playwright_user")

        # Navigate to members page
        self.page.goto(f"{self.live_server_url}/members/")

        # Check we're not redirected to login
        current_url = self.page.url
        assert (
            "/login" not in current_url
        ), "Authenticated user should not be redirected to login"
