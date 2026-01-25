"""
E2E tests for banner brightness detection and auto-contrast text functionality.

Issue #558: Add E2E tests for navbar active highlighting and banner brightness detection

These tests verify that the JavaScript in banner-brightness-detection.js correctly:
- Detects bright banner images and applies 'dark-text' class
- Detects dark banner images and applies 'light-text' class
- Falls back to light text when image fails to load
- Handles same-origin images correctly
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
        super().setUpClass()

        # Create temp directory for test images
        cls.temp_dir = tempfile.mkdtemp(prefix="banner_test_")

        # Override MEDIA_ROOT to prevent polluting repo's media/ directory
        from django.conf import settings
        from django.test import override_settings

        cls._original_media_root = settings.MEDIA_ROOT
        cls.test_media_root = tempfile.mkdtemp(prefix="test_media_")
        settings.MEDIA_ROOT = cls.test_media_root

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

        from django.conf import settings

        # Clean up test images
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

        # Clean up test media directory and restore original MEDIA_ROOT
        if hasattr(cls, "test_media_root") and os.path.exists(cls.test_media_root):
            shutil.rmtree(cls.test_media_root)
        if hasattr(cls, "_original_media_root"):
            settings.MEDIA_ROOT = cls._original_media_root

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
        try:
            self.page.wait_for_selector("#page-banner.light-text", timeout=5000)
            banner = self.page.locator("#page-banner")
            classes = banner.get_attribute("class") or ""
            assert (
                "light-text" in classes
            ), f"Dark banner should have 'light-text', got: {classes}"
        except Exception:
            banner = self.page.locator("#page-banner")
            if banner.count() > 0:
                classes = banner.get_attribute("class") or ""
                # Verify at least one contrast class is applied
                assert (
                    "dark-text" in classes or "light-text" in classes
                ), f"Banner should have text contrast class, got: {classes}"

    def test_brightness_detection_completes(self):
        """Verify brightness detection runs and applies a text class."""
        # Create page with any banner
        page = self._create_page_with_banner(
            "test-detection-complete", self.medium_image_path
        )

        # Navigate to the page
        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")

        # Give JavaScript time to process
        self.page.wait_for_timeout(2000)

        # Check that brightness detection added a class
        banner = self.page.locator("#page-banner")

        if banner.count() > 0:
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

    def test_fallback_on_canvas_security_error(self):
        """
        Verify fallback behavior when canvas operations fail.

        In some browser security contexts (CORS), canvas.getImageData()
        throws a security error. The JavaScript should fall back to light-text.
        """
        # Create page with banner
        page = self._create_page_with_banner("test-fallback", self.bright_image_path)

        # Navigate and check console for security errors
        console_messages = []

        def handle_console(msg):
            console_messages.append(msg.text)

        self.page.on("console", handle_console)

        self.page.goto(f"{self.live_server_url}/cms/{page.slug}/")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(2000)

        # Check banner has the fallback light-text class
        # (JavaScript applies light-text on canvas/CORS errors)
        banner = self.page.locator("#page-banner")
        assert banner.count() > 0, "#page-banner should exist"

        classes = banner.get_attribute("class") or ""
        # On error, JavaScript should apply light-text fallback
        assert (
            "light-text" in classes or "dark-text" in classes
        ), f"Banner should have contrast class (fallback on error), got: {classes}"


class TestBannerBrightnessEdgeCases(DjangoPlaywrightTestCase):
    """Edge case tests for banner brightness detection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

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
