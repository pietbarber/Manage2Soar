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

import re

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
        """Server-rendered HTML sets the error div to display:none.

        This is a template/server-rendering concern rather than browser-JS
        behaviour, so we verify it via Django's test client (available on
        StaticLiveServerTestCase) instead of fighting Playwright route
        interception timing issues.
        """
        self.client.force_login(self.member)
        response = self.client.get("/webcam/")
        assert response.status_code == 200
        content = response.content.decode()

        # Locate the opening tag of #webcam-error specifically, so we don't
        # accidentally match the display:none on the <img> or other elements.
        match = re.search(r"<[^>]+id=[\"']webcam-error[\"'][^>]*>", content)
        assert match, "webcam-error element missing from HTML"
        element_tag = match.group(0)
        assert (
            "display:none" in element_tag
        ), f"Error div opening tag should contain display:none, got: {element_tag!r}"

    def test_auto_refresh_timer_is_running(self):
        """JS sets up the interval timer; the status span confirms auto-refresh."""
        self.page.goto(f"{self.live_server_url}/webcam/")
        # Give JS a moment to execute.
        self.page.wait_for_timeout(200)

        status_text = self.page.locator("#webcam-status").text_content() or ""
        assert (
            "refresh" in status_text.lower()
        ), f"Status span should mention refresh, got: {status_text!r}"

    def test_js_updates_status_span(self):
        """JS writes an interval description into the status span.

        The static HTML does NOT contain "every 10" — only the JavaScript
        fills this in after the IIFE runs.  This test would fail if the
        ``{% block extra_scripts %}`` block were misnamed and the JS never
        loaded (the original bug in issue #694).
        """
        self.page.goto(f"{self.live_server_url}/webcam/")
        # Give the IIFE a moment to execute and update the DOM.
        self.page.wait_for_timeout(500)

        status_text = self.page.locator("#webcam-status").text_content() or ""
        assert "every 10" in status_text.lower(), (
            f"JS should write 'every 10' into the status span, got: {status_text!r}. "
            "This likely means the extra_scripts block is misnamed and JS never loaded."
        )

    def test_img_src_changes_after_interval(self):
        """After the refresh interval fires the img src gains a cache-buster param.

        Uses Playwright's fake clock to advance time by 11 seconds without
        actually waiting, then checks that the JS added ``?t=<timestamp>`` to
        the image src — proof that setInterval() fired and refreshImage() ran.
        """
        # Install fake clock *before* navigating so setInterval uses it.
        self.page.clock.install()

        self.page.goto(f"{self.live_server_url}/webcam/")
        # Give JS time to execute and register the interval.
        self.page.wait_for_timeout(200)

        original_src = self.page.locator("#webcam-img").get_attribute("src") or ""

        # Advance past the 10-second interval.
        self.page.clock.fast_forward(11000)
        self.page.wait_for_timeout(200)

        new_src = self.page.locator("#webcam-img").get_attribute("src") or ""
        assert "?t=" in new_src, (
            f"After interval fires the img src should contain '?t=' cache-buster, "
            f"got: {new_src!r}. This likely means setInterval was never registered."
        )
        assert new_src != original_src, (
            f"img src should change after the interval fires; "
            f"original={original_src!r}, new={new_src!r}"
        )


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
