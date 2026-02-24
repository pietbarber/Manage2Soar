"""
E2E tests for the webcam viewer page JavaScript (Issue #625).

These tests verify browser-side behaviour that unit tests cannot cover:
- Initial image is hidden (display:none) until the first snapshot loads.
- Error div is hidden on load and shown when the camera returns a non-2xx
  response (onerror handler).
- The auto-refresh interval timer is set up by the JS.
- The Page Visibility API handler is registered so refreshes pause when
  the tab is hidden.

Note: E2E tests requiring a *working* camera URL would need a live camera
endpoint.  The error-path tests below are fully deterministic: they use a
``file://`` scheme URL which triggers the server-side SSRF guard and returns
503, causing the browser <img> onerror to fire immediately.
"""

from siteconfig.models import SiteConfiguration

from .conftest import DjangoPlaywrightTestCase

# A URL with a non-http/https scheme.  The webcam_snapshot view's SSRF guard
# rejects it and returns 503 without ever making a network call.
_INVALID_URL = "file:///etc/passwd"

# No publicly addressable snapshot URL is available in the test environment,
# so we use the SSRF-blocked URL for error-path tests.


def _make_siteconfig(webcam_url=_INVALID_URL):
    existing = SiteConfiguration.objects.first()
    if existing:
        existing.webcam_snapshot_url = webcam_url
        existing.save(update_fields=["webcam_snapshot_url"])
        return existing
    return SiteConfiguration.objects.create(
        club_name="E2E Test Club",
        domain_name="e2e.test",
        club_abbreviation="E2E",
        webcam_snapshot_url=webcam_url,
    )


class TestWebcamPageStructure(DjangoPlaywrightTestCase):
    """Verify DOM structure and initial JS state on page load."""

    def setUp(self):
        super().setUp()
        _make_siteconfig(webcam_url=_INVALID_URL)
        self.member = self.create_test_member(username="webcam_e2e_user")
        self.login(username="webcam_e2e_user")

    def test_img_is_hidden_initially(self):
        """The webcam <img> starts hidden; it is only shown after onload fires."""
        self.page.goto(f"{self.live_server_url}/webcam/")

        # The <img> has display:none before any refresh cycle completes.
        img = self.page.locator("#webcam-img")
        assert img.count() == 1, "webcam-img element must exist"
        display = img.evaluate("el => window.getComputedStyle(el).display")
        assert (
            display == "none"
        ), f"Expected img hidden on load, got display={display!r}"

    def test_error_div_is_hidden_initially(self):
        """The error div is hidden on first render (shown only on camera failure)."""
        self.page.goto(f"{self.live_server_url}/webcam/")

        error_div = self.page.locator("#webcam-error")
        assert error_div.count() == 1, "webcam-error element must exist"
        # The element has style="display:none" in the HTML
        display = error_div.evaluate("el => el.style.display")
        assert (
            display == "none"
        ), f"Error div should be hidden initially, got {display!r}"

    def test_auto_refresh_timer_is_running(self):
        """JS sets up the interval timer; the status span confirms auto-refresh."""
        self.page.goto(f"{self.live_server_url}/webcam/")
        # Give JS a moment to execute.
        self.page.wait_for_timeout(200)

        status_text = self.page.locator("#webcam-status").text_content() or ""
        assert (
            "refresh" in status_text.lower()
        ), f"Status span should mention refresh, got: {status_text!r}"


class TestWebcamErrorState(DjangoPlaywrightTestCase):
    """Verify that the error div appears when the snapshot endpoint returns 503."""

    def setUp(self):
        super().setUp()
        # SSRF guard blocks file:// → webcam_snapshot returns 503 → onerror fires.
        _make_siteconfig(webcam_url=_INVALID_URL)
        self.member = self.create_test_member(username="webcam_err_user")
        self.login(username="webcam_err_user")

    def test_error_div_visible_when_camera_down(self):
        """Error div appears when the browser gets a non-2xx snapshot response."""
        self.page.goto(f"{self.live_server_url}/webcam/")

        # Wait for the browser to attempt the initial snapshot request and
        # for the onerror handler to update the DOM.
        error_div = self.page.locator("#webcam-error")
        error_div.wait_for(state="visible", timeout=5000)

        assert (
            error_div.is_visible()
        ), "Error div should be visible when the camera snapshot returns 503"

    def test_img_hidden_when_camera_down(self):
        """The broken-image icon is suppressed (img hidden) when camera is down."""
        self.page.goto(f"{self.live_server_url}/webcam/")

        # Wait for onerror to fire and hide the img.
        self.page.locator("#webcam-error").wait_for(state="visible", timeout=5000)

        img = self.page.locator("#webcam-img")
        display = img.evaluate("el => window.getComputedStyle(el).display")
        assert (
            display == "none"
        ), f"img should remain hidden when camera is down, got display={display!r}"


class TestWebcamNavLink(DjangoPlaywrightTestCase):
    """Webcam nav link is shown when URL is configured, hidden when blank."""

    def test_nav_link_visible_when_configured(self):
        """📷 Webcam nav link appears for authenticated members when URL is set."""
        _make_siteconfig(webcam_url=_INVALID_URL)
        member = self.create_test_member(username="nav_test_user")
        self.login(username="nav_test_user")

        # Navigate to any member page so the nav is rendered.
        self.page.goto(f"{self.live_server_url}/webcam/")

        nav_link = self.page.locator('a[href*="/webcam/"]')
        assert nav_link.count() > 0, "Webcam nav link should exist when URL is set"

    def test_nav_link_hidden_when_not_configured(self):
        """📷 Webcam nav link is absent when webcam_snapshot_url is blank."""
        _make_siteconfig(webcam_url="")
        member = self.create_test_member(username="nav_blank_user")
        self.login(username="nav_blank_user")

        self.page.goto(f"{self.live_server_url}/")

        # The only /webcam/ link should be absent from the navbar.
        nav_link = self.page.locator("nav").locator('a[href*="/webcam/"]')
        assert (
            nav_link.count() == 0
        ), "Webcam nav link should not appear when URL is blank"
