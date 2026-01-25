"""
E2E tests for navbar-spacer dynamic height adjustment.

Issue #567: Fixed navbar clipping page content

These tests verify that the JavaScript in navbar-enhanced.js correctly:
- Sets .navbar-spacer height to match actual navbar height on page load
- Updates spacer height when viewport is resized (zoom, window size)
- Prevents content from being hidden under the fixed-top navbar
"""

from .conftest import DjangoPlaywrightTestCase


class TestNavbarSpacerDynamicHeight(DjangoPlaywrightTestCase):
    """
    Tests for navbar spacer dynamic height calculation.

    Feature: Navbar spacer height matches actual navbar height to prevent content clipping
    File: static/js/navbar-enhanced.js (updateNavbarSpacerHeight function)
    """

    def setUp(self):
        super().setUp()
        # Create and login test member for all tests
        self.create_test_member(username="spacer_test_user", is_superuser=False)
        self.login(username="spacer_test_user")

    def test_spacer_height_matches_navbar_height_on_load(self):
        """
        Verify that navbar-spacer height equals navbar height after page load.

        This ensures the JavaScript correctly measures the navbar and sets
        the spacer to prevent content clipping.
        """
        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_load_state("networkidle")

        # Get actual navbar height
        navbar_height = self.page.locator("#main-navbar").evaluate(
            "el => el.offsetHeight"
        )

        # Get spacer computed height
        spacer_height = self.page.locator(".navbar-spacer").evaluate(
            "el => parseFloat(window.getComputedStyle(el).height)"
        )

        # They should match (within 1px for rounding)
        self.assertAlmostEqual(
            navbar_height,
            spacer_height,
            delta=1,
            msg=f"Navbar spacer height ({spacer_height}px) should match navbar height ({navbar_height}px)",
        )

    def test_spacer_height_updates_on_viewport_resize(self):
        """
        Verify that navbar-spacer height updates when viewport is resized.

        This ensures the resize event listener works and the spacer adjusts
        to handle navbar height changes (e.g., from text wrapping).
        """
        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_load_state("networkidle")

        # Get initial heights
        initial_navbar_height = self.page.locator("#main-navbar").evaluate(
            "el => el.offsetHeight"
        )
        initial_spacer_height = self.page.locator(".navbar-spacer").evaluate(
            "el => parseFloat(window.getComputedStyle(el).height)"
        )

        # Verify initial state matches
        self.assertAlmostEqual(
            initial_navbar_height,
            initial_spacer_height,
            delta=1,
            msg="Initial spacer height should match navbar height",
        )

        # Resize viewport to a narrower width that might cause navbar wrapping
        # Standard Bootstrap navbar breakpoint is 992px (lg)
        self.page.set_viewport_size({"width": 800, "height": 600})
        self.page.wait_for_timeout(300)  # Allow time for resize handler

        # Get new heights after resize
        new_navbar_height = self.page.locator("#main-navbar").evaluate(
            "el => el.offsetHeight"
        )
        new_spacer_height = self.page.locator(".navbar-spacer").evaluate(
            "el => parseFloat(window.getComputedStyle(el).height)"
        )

        # Spacer should still match navbar height after resize
        self.assertAlmostEqual(
            new_navbar_height,
            new_spacer_height,
            delta=1,
            msg=f"After resize, spacer height ({new_spacer_height}px) should match navbar height ({new_navbar_height}px)",
        )

    def test_spacer_prevents_content_clipping(self):
        """
        Verify that page content is not hidden under the fixed navbar.

        This is the core issue from #567 - content should start below the navbar,
        not underneath it.
        """
        self.page.goto(f"{self.live_server_url}/")
        self.page.wait_for_load_state("networkidle")

        # Get navbar bottom position
        navbar_bottom = self.page.locator("#main-navbar").evaluate(
            "el => el.getBoundingClientRect().bottom"
        )

        # Get spacer bottom position (top of main content)
        spacer_bottom = self.page.locator(".navbar-spacer").evaluate(
            "el => el.getBoundingClientRect().bottom"
        )

        # Spacer bottom should be at or below navbar bottom
        # (spacer creates the offset, so content starts after both navbar and spacer)
        self.assertGreaterEqual(
            spacer_bottom,
            navbar_bottom - 1,  # Allow 1px tolerance for rounding
            msg=f"Spacer bottom ({spacer_bottom}px) should be at or below navbar bottom ({navbar_bottom}px) to prevent content clipping",
        )

    def test_spacer_exists_on_all_pages(self):
        """
        Verify that navbar-spacer element exists on pages with navbar.

        This ensures the spacer is present in the base template for all pages
        that render the navbar.
        """
        test_urls = [
            "/",
            "/members/",
            "/duty_roster/calendar/",
            "/logsheet/",
        ]

        for url in test_urls:
            with self.subTest(url=url):
                self.page.goto(f"{self.live_server_url}{url}")
                self.page.wait_for_load_state("networkidle")

                # Check navbar exists
                navbar_count = self.page.locator("#main-navbar").count()
                self.assertEqual(
                    navbar_count,
                    1,
                    msg=f"Page {url} should have navbar",
                )

                # Check spacer exists
                spacer_count = self.page.locator(".navbar-spacer").count()
                self.assertEqual(
                    spacer_count,
                    1,
                    msg=f"Page {url} should have navbar-spacer",
                )

                # Verify spacer height matches navbar
                navbar_height = self.page.locator("#main-navbar").evaluate(
                    "el => el.offsetHeight"
                )
                spacer_height = self.page.locator(".navbar-spacer").evaluate(
                    "el => parseFloat(window.getComputedStyle(el).height)"
                )

                self.assertAlmostEqual(
                    navbar_height,
                    spacer_height,
                    delta=1,
                    msg=f"On {url}, spacer height should match navbar height",
                )
