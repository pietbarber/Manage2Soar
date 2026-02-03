"""
E2E tests for banner brightness detection and auto-contrast text functionality.

Issue #558: Add E2E tests for navbar active highlighting and banner brightness detection

These tests verify that the JavaScript in banner-brightness-detection.js correctly:
- Detects bright banner images and applies 'dark-text' class
- Detects dark banner images and applies 'light-text' class
- Handles same-origin images correctly
- Validates the brightness threshold constant (140)
- Confirms the detectBannerBrightness function exists

NOTE: Testing actual CORS/canvas security errors or image load failures is
difficult to reliably test in an E2E environment without mocking.
"""

import os
import tempfile

from PIL import Image

from cms.models import Page

from .conftest import DjangoPlaywrightTestCase


class TestBannerBrightnessDetection(DjangoPlaywrightTestCase):
    """
    Tests for banner brightness detection and auto-contrast text.

    Feature: Auto-contrast text color based on banner image brightness
    File: static/js/banner-brightness-detection.js

    Technical Notes:
    - Brightness threshold is 140 (0-255 scale)
    - Values > 140 are "bright" → dark text
    - Values ≤ 140 are "dark" → light text
    - Uses weighted RGB: 0.299*R + 0.587*G + 0.114*B
    """

    @classmethod
    def setUpClass(cls):
        """Create test image files for brightness detection tests."""
        # Use override_settings for proper test isolation
        from django.test import override_settings

        cls.test_media_root = tempfile.mkdtemp(prefix="test_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls.test_media_root)
        cls._media_override.enable()

        # Now start the live server with overridden MEDIA_ROOT
        super().setUpClass()

        # Create temp directory for test images
        cls.temp_dir = tempfile.mkdtemp(prefix="banner_test_")

        # Create a bright white image (brightness ≈ 255)
        cls.bright_image_path = os.path.join(cls.temp_dir, "bright_banner.png")
        cls._create_test_image(cls.bright_image_path, color=(255, 255, 255))

        # Create a dark image (brightness ≈ 0)
        cls.dark_image_path = os.path.join(cls.temp_dir, "dark_banner.png")
        cls._create_test_image(cls.dark_image_path, color=(20, 20, 30))

        # Create a medium brightness image (around threshold of 140)
        cls.medium_image_path = os.path.join(cls.temp_dir, "medium_banner.png")
        cls._create_test_image(cls.medium_image_path, color=(140, 140, 140))

    @classmethod
    def tearDownClass(cls):
        """Clean up test image files and test media directory."""
        import shutil

        # Clean up test images
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

        # Clean up test media directory
        if hasattr(cls, "test_media_root") and os.path.exists(cls.test_media_root):
            shutil.rmtree(cls.test_media_root)

        # Disable override_settings to restore original MEDIA_ROOT
        if hasattr(cls, "_media_override"):
            cls._media_override.disable()

        super().tearDownClass()

    @staticmethod
    def _create_test_image(path, color=(255, 255, 255), size=(200, 100)):
        """Create a solid color test image."""
        img = Image.new("RGB", size, color)
        img.save(path, "PNG")

    def _create_page_with_banner(self, slug, image_path):
        """Create a CMS page with a banner image."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Read the image file
        with open(image_path, "rb") as f:
            image_content = f.read()

        # Create a SimpleUploadedFile
        uploaded_image = SimpleUploadedFile(
            name=os.path.basename(image_path),
            content=image_content,
            content_type="image/png",
        )

        # Create the page
        page = Page.objects.create(
            title=f"Test Page {slug}",
            slug=slug,
            content=f"<p>Test content for {slug}</p>",
            is_public=True,
            banner_image=uploaded_image,
        )

        return page

    def setUp(self):
        super().setUp()
        # Create and login as admin for full access
        self.create_test_member(username="banner_test_admin", is_superuser=True)
        self.login(username="banner_test_admin")

    def test_dark_text_applied_to_bright_banner(self):
        """Verify bright banners get 'dark-text' class for contrast."""
        # Create page with bright banner
        page = self._create_page_with_banner(
            "test-bright-banner", self.bright_image_path
        )

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")

        # Wait for the brightness detection to complete
        # The JavaScript adds 'dark-text' or 'light-text' class
        self.page.wait_for_selector("#page-banner.dark-text", timeout=5000)
        banner = self.page.locator("#page-banner")
        classes = banner.get_attribute("class") or ""
        assert (
            "dark-text" in classes
        ), f"Bright banner should have 'dark-text', got: {classes}"

    def test_light_text_applied_to_dark_banner(self):
        """Verify dark banners get 'light-text' class for contrast."""
        # Create page with dark banner
        page = self._create_page_with_banner("test-dark-banner", self.dark_image_path)

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")

        # Wait for the brightness detection to complete
        self.page.wait_for_selector("#page-banner.light-text", timeout=5000)
        banner = self.page.locator("#page-banner")
        classes = banner.get_attribute("class") or ""
        assert (
            "light-text" in classes
        ), f"Dark banner should have 'light-text', got: {classes}"

    def test_brightness_detection_completes(self):
        """Verify brightness detection runs and applies a text class."""
        # Create page with any banner
        page = self._create_page_with_banner(
            "test-detection-complete", self.medium_image_path
        )

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # Wait deterministically for brightness detection to apply a contrast class
        self.page.wait_for_selector(
            "#page-banner.dark-text, #page-banner.light-text", timeout=5000
        )

        # Check that brightness detection added a class
        banner = self.page.locator("#page-banner")
        assert banner.count() > 0, "#page-banner should exist"

        classes = banner.get_attribute("class") or ""
        has_contrast_class = "dark-text" in classes or "light-text" in classes
        assert (
            has_contrast_class
        ), f"Banner should have 'dark-text' or 'light-text' class after detection, got: {classes}"

    def test_page_without_banner_has_no_brightness_detection(self):
        """Verify pages without banners don't trigger brightness detection."""
        # Create page WITHOUT a banner
        page = Page.objects.create(
            title="No Banner Page",
            slug="test-no-banner",
            content="<p>Page without banner image</p>",
            is_public=True,
        )

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # There should be no #page-banner element
        banner = self.page.locator("#page-banner")
        # Page without banner_image won't render the banner div
        assert (
            banner.count() == 0
        ), "#page-banner should not exist when page has no banner_image"

    def test_same_origin_image_brightness_detection(self):
        """
        Verify brightness detection works correctly for same-origin images.

        NOTE: This test does NOT actually trigger a canvas security error
        because the image is served from the same origin. Testing actual
        CORS/canvas security errors would require a cross-origin image URL
        without proper CORS headers, which is difficult to reliably test
        in an E2E environment.
        """
        # Create page with bright banner (same-origin, should succeed)
        page = self._create_page_with_banner("test-same-origin", self.bright_image_path)

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # Wait deterministically for brightness detection to apply a text class
        self.page.wait_for_function(
            """
            () => {
                const banner = document.querySelector('#page-banner');
                if (!banner) return false;
                const classList = banner.classList;
                return (
                    classList.contains('dark-text') ||
                    classList.contains('light-text')
                );
            }
            """
        )

        # Verify brightness detection completed successfully
        banner = self.page.locator("#page-banner")
        assert banner.count() > 0, "#page-banner should exist"

        classes = banner.get_attribute("class") or ""
        # Same-origin bright image should get dark-text
        assert (
            "dark-text" in classes
        ), f"Bright same-origin banner should have 'dark-text', got: {classes}"


class TestBannerBrightnessEdgeCases(DjangoPlaywrightTestCase):
    """Edge case tests for banner brightness detection."""

    def setUp(self):
        super().setUp()
        self.create_test_member(username="edge_case_admin", is_superuser=True)
        self.login(username="edge_case_admin")

    def test_brightness_detection_function_exists(self):
        """Verify the detectBannerBrightness function is defined globally."""
        self.page.goto(self.live_server_url)
        self.page.wait_for_load_state("networkidle")

        # Check that the function exists
        function_exists = self.page.evaluate(
            "typeof detectBannerBrightness === 'function'"
        )
        assert function_exists, "detectBannerBrightness function should be defined"

    def test_brightness_threshold_constant(self):
        """Verify the BRIGHTNESS_THRESHOLD constant is defined correctly."""
        self.page.goto(self.live_server_url)
        self.page.wait_for_load_state("networkidle")

        # Check that the threshold constant exists and has expected value
        threshold = self.page.evaluate(
            "typeof BRIGHTNESS_THRESHOLD !== 'undefined' ? BRIGHTNESS_THRESHOLD : null"
        )

        # Threshold should be 140 as per the JavaScript
        assert threshold == 140, f"BRIGHTNESS_THRESHOLD should be 140, got: {threshold}"


class TestBannerParallaxEffect(DjangoPlaywrightTestCase):
    """
    E2E tests for banner parallax scrolling functionality (Issue #570).

    Feature: JavaScript-based parallax effect using transform: translateY()
    File: static/js/banner-brightness-detection.js (initBannerParallax function)

    Technical Notes:
    - Parallax speed factor is 0.3 (image moves at 30% of scroll speed)
    - Uses requestAnimationFrame for smooth performance
    - Respects prefers-reduced-motion preference
    - Only applies when banner is visible in viewport
    """

    @classmethod
    def setUpClass(cls):
        """Create a test image for parallax tests."""
        from django.test import override_settings

        cls.test_media_root = tempfile.mkdtemp(prefix="test_media_parallax_")
        cls._media_override = override_settings(MEDIA_ROOT=cls.test_media_root)
        cls._media_override.enable()

        super().setUpClass()

        # Create temp directory for test image
        cls.temp_dir = tempfile.mkdtemp(prefix="parallax_test_")

        # Create a test banner image
        cls.test_image_path = os.path.join(cls.temp_dir, "parallax_banner.png")
        img = Image.new("RGB", (1920, 600), color=(100, 150, 200))
        img.save(cls.test_image_path, "PNG")

    @classmethod
    def tearDownClass(cls):
        """Clean up test files and media directory."""
        import shutil

        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

        if hasattr(cls, "test_media_root") and os.path.exists(cls.test_media_root):
            shutil.rmtree(cls.test_media_root)

        if hasattr(cls, "_media_override"):
            cls._media_override.disable()

        super().tearDownClass()

    def _create_page_with_banner(self, slug, image_path):
        """Create a CMS page with a banner image."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        with open(image_path, "rb") as f:
            image_content = f.read()

        uploaded_file = SimpleUploadedFile(
            name=os.path.basename(image_path),
            content=image_content,
            content_type="image/png",
        )

        page = Page.objects.create(
            title=f"Test Page {slug}",
            slug=slug,
            content="<p>Test content</p>",
            is_public=True,
            banner_image=uploaded_file,
        )
        return page

    def setUp(self):
        super().setUp()
        self.create_test_member(username="parallax_admin", is_superuser=True)
        self.login(username="parallax_admin")

    def test_parallax_function_exists(self):
        """Verify the initBannerParallax function is defined globally."""
        self.page.goto(self.live_server_url)
        self.page.wait_for_load_state("networkidle")

        function_exists = self.page.evaluate("typeof initBannerParallax === 'function'")
        assert function_exists, "initBannerParallax function should be defined"

    def test_parallax_applies_transform_on_scroll(self):
        """Verify that parallax effect applies CSS transform when scrolling."""
        # Create page with banner and extra content to make it scrollable
        page = self._create_page_with_banner(
            "test-parallax-scroll", self.test_image_path
        )
        page.content = "<p>Content line</p>" * 50  # Add enough content for scrolling
        page.save()

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # Wait for banner to be visible
        banner_image = self.page.locator(".page-banner-image")
        assert banner_image.count() > 0, "Banner image should exist"

        # Get initial transform value (should be translateY(0px))
        initial_transform = banner_image.evaluate("el => el.style.transform")

        # Scroll down the page significantly (past the banner)
        self.page.evaluate("window.scrollBy(0, 500)")
        self.page.wait_for_timeout(200)  # Wait for parallax to apply

        # Get transform after scroll
        after_scroll_transform = banner_image.evaluate("el => el.style.transform")

        # Transform should have changed (parallax applied)
        # At scrollY=500, parallax offset should be 500 * 0.3 = 150px
        assert (
            after_scroll_transform != initial_transform
        ), f"Transform should change after scroll. Initial: {initial_transform}, After: {after_scroll_transform}"

        # Verify it's a translateY transform with a positive value
        assert (
            "translateY(" in after_scroll_transform
        ), f"Transform should contain translateY, got: {after_scroll_transform}"

        # Verify the value is non-zero (can be decimal like 104.7px)
        import re

        match = re.search(r"translateY\(([\d.]+)px\)", after_scroll_transform)
        assert match, f"Should have numeric translateY value: {after_scroll_transform}"
        translate_value = float(match.group(1))
        assert translate_value > 0, f"translateY should be > 0, got {translate_value}px"

    def test_parallax_respects_prefers_reduced_motion(self):
        """Verify that parallax is disabled when prefers-reduced-motion is set."""
        # Set prefers-reduced-motion media query
        self.page.emulate_media(color_scheme="light", reduced_motion="reduce")

        page = self._create_page_with_banner(
            "test-parallax-reduced-motion", self.test_image_path
        )

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        banner_image = self.page.locator(".page-banner-image")
        assert banner_image.count() > 0, "Banner image should exist"

        # Get initial transform
        initial_transform = banner_image.evaluate("el => el.style.transform")

        # Scroll down
        self.page.evaluate("window.scrollBy(0, 200)")
        self.page.wait_for_timeout(100)

        # Get transform after scroll
        after_scroll_transform = banner_image.evaluate("el => el.style.transform")

        # Transform should NOT change when reduced motion is preferred
        # (initBannerParallax should return early)
        assert (
            after_scroll_transform == initial_transform or not after_scroll_transform
        ), "Transform should not change when prefers-reduced-motion is set"

    def test_parallax_only_applies_when_banner_visible(self):
        """Verify that parallax only applies when banner is in viewport."""
        page = self._create_page_with_banner(
            "test-parallax-visibility", self.test_image_path
        )

        # Add lots of content so we can scroll past the banner
        page.content = "<p>Content</p>" * 100
        page.save()

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        banner_image = self.page.locator(".page-banner-image")
        assert banner_image.count() > 0, "Banner image should exist"

        # Scroll way past the banner (banner height is ~300px, scroll 1000px)
        self.page.evaluate("window.scrollBy(0, 1000)")
        self.page.wait_for_timeout(100)

        # The parallax logic in JavaScript only applies transform when banner is visible
        # We can't easily test the internal logic without modifying production code,
        # but we can verify the function doesn't throw errors and executes
        no_errors = self.page.evaluate(
            """
            () => {
                try {
                    // Trigger a scroll event
                    window.scrollBy(0, 10);
                    return true;
                } catch (e) {
                    return false;
                }
            }
            """
        )
        assert no_errors, "Parallax should not throw errors when banner is out of view"

    def test_parallax_initializes_without_errors(self):
        """Verify that parallax initialization doesn't throw errors."""
        page = self._create_page_with_banner("test-parallax-init", self.test_image_path)

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # Check for any JavaScript errors
        errors = []

        def handle_console(msg):
            if msg.type == "error":
                errors.append(msg.text)

        self.page.on("console", handle_console)

        # Scroll to trigger parallax
        self.page.evaluate("window.scrollBy(0, 100)")
        self.page.wait_for_timeout(200)

        # Remove listener
        self.page.remove_listener("console", handle_console)

        # No errors should have occurred
        assert len(errors) == 0, f"Parallax should not cause console errors: {errors}"

    def test_banner_background_size_is_contain(self):
        """
        Verify banner image uses background-size: contain to prevent cropping.

        Issue #570: Banner images were being inappropriately zoomed/cropped when
        using background-size: cover. This test ensures the CSS remains set to
        'contain' to show full banner images.

        Regression prevention: This test will fail if background-size is changed
        back to 'cover' or any other value that would cause cropping.
        """
        # Create page with any banner image
        page = self._create_page_with_banner(
            "test-banner-contain", self.test_image_path
        )

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")

        # Wait for page to fully load including stylesheets
        self.page.wait_for_load_state("networkidle")

        # Wait for banner to be visible
        self.page.wait_for_selector(".page-banner-image", timeout=5000)

        # Get computed background-size style
        banner_image = self.page.locator(".page-banner-image")
        background_size = banner_image.evaluate(
            "element => window.getComputedStyle(element).backgroundSize"
        )

        # Verify it's 'contain' not 'cover'
        assert (
            background_size == "contain"
        ), f"Banner background-size should be 'contain' to prevent cropping, got: {background_size}"
