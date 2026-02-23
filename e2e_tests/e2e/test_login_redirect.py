"""
E2E tests for login redirect behavior (Issue #674).

Verifies that after visiting a deep link requiring authentication,
the user is taken back to the original URL after successful login —
not dropped on the homepage.
"""

from django.urls import reverse

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestLoginRedirect(DjangoPlaywrightTestCase):
    """
    Full browser test: fresh session → deep link → login page → back to deep link.

    Scenario:
      1. Open a protected URL in a fresh browser (no cookies/session)
      2. Should be redirected to /login/?next=<protected_url>
      3. Submit correct credentials
      4. Should land on the original protected URL, not the homepage
    """

    def test_deep_link_redirects_back_after_login(self):
        """After login, user lands on the originally requested URL."""
        member = self.create_test_member(username="redirecttest")

        # A protected deep-link URL
        deep_url = f"{self.live_server_url}/members/"

        # Fresh browser — no session — navigate directly to protected page
        self.page.goto(deep_url)

        # Should have been redirected to the login page
        self.assertIn("/login/", self.page.url, "Should redirect to login page")
        # The ?next= param should be present
        self.assertIn("next=", self.page.url, "Login URL should contain ?next=")

        # Fill in credentials and submit
        self.page.fill('input[name="username"]', "redirecttest")
        self.page.fill('input[name="password"]', "testpass123")
        self.page.click('button[type="submit"]')

        # Wait for navigation after login
        self.page.wait_for_load_state("networkidle")

        # Should be back at the original deep-link, not the homepage
        self.assertEqual(
            self.page.url,
            deep_url,
            f"Should redirect to original URL after login, got: {self.page.url}",
        )

    def test_login_without_next_goes_to_homepage(self):
        """Direct /login/ visit with no ?next= still lands on homepage (existing behavior)."""
        self.create_test_member(username="directlogin")

        self.page.goto(f"{self.live_server_url}/login/")

        self.page.fill('input[name="username"]', "directlogin")
        self.page.fill('input[name="password"]', "testpass123")
        self.page.click('button[type="submit"]')

        self.page.wait_for_load_state("networkidle")

        # No ?next= → falls back to LOGIN_REDIRECT_URL = "/"
        self.assertEqual(
            self.page.url,
            f"{self.live_server_url}/",
            f"Direct login should go to homepage, got: {self.page.url}",
        )

    def test_next_param_preserved_in_hidden_field(self):
        """The hidden next field in the form is populated from the ?next= query param."""
        self.create_test_member(username="hiddentest")

        self.page.goto(f"{self.live_server_url}/login/?next=/members/")

        # The hidden input must carry the next value
        next_value = self.page.get_attribute('input[name="next"]', "value")
        self.assertEqual(
            next_value, "/members/", "Hidden next field should match ?next= param"
        )
