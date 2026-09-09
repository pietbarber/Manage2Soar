"""
Playwright E2E test for the CMS banner image upload on the create page form.

Issue #1047: The banner image field should be available on the create page
form (parity with the edit form). This test verifies that:
  1. The banner_image file input is present on the create page form.
  2. A user can select a file via the input.
  3. Submitting the form persists the banner (the page renders with a
     banner element after creation).
"""

import os
import shutil
import tempfile

from PIL import Image

from .conftest import DjangoPlaywrightTestCase


class TestBannerImageOnCreatePageForm(DjangoPlaywrightTestCase):
    """E2E coverage for Issue #1047 (create page form banner upload)."""

    @classmethod
    def setUpClass(cls):
        cls.test_media_root = tempfile.mkdtemp(prefix="test_media_banner_")
        from django.test import override_settings

        cls._media_override = override_settings(MEDIA_ROOT=cls.test_media_root)
        cls._media_override.enable()

        super().setUpClass()

        cls.temp_dir = tempfile.mkdtemp(prefix="banner_e2e_")
        cls.banner_path = os.path.join(cls.temp_dir, "banner.png")
        img = Image.new("RGB", (800, 120), (30, 60, 120))
        img.save(cls.banner_path, "PNG")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp_dir") and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)
        if hasattr(cls, "test_media_root") and os.path.exists(cls.test_media_root):
            shutil.rmtree(cls.test_media_root)
        if hasattr(cls, "_media_override"):
            cls._media_override.disable()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.create_test_member(username="banner_e2e_admin", is_superuser=True)
        self.login(username="banner_e2e_admin")

    def test_banner_field_present_on_create_form(self):
        """The create page form exposes the banner_image file input."""
        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_load_state("networkidle")

        # The banner file input should be present in the form.
        banner_input = self.page.locator('input[type="file"][name="banner_image"]')
        self.assertTrue(banner_input.is_visible(), "banner_image input not visible")

    def test_upload_banner_on_create_form_persists(self):
        """Selecting a file in the banner input and submitting saves it."""
        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_load_state("networkidle")

        # Fill in required fields (content is optional - skip TinyMCE which hides its textarea)
        self.page.fill('input[name="title"]', "Banner E2E Page")
        self.page.fill('input[name="slug"]', "banner-e2e-page")

        # Select the banner file
        self.page.set_input_files('input[name="banner_image"]', self.banner_path)

        # Verify the file input shows the selected filename
        value = self.page.input_value('input[name="banner_image"]')
        self.assertIn("banner.png", value.replace("\\", "/"))

        # Submit (target the form's "Create Page" button, not the navbar Logout)
        self.page.click('button.btn-success[type="submit"]')
        self.page.wait_for_load_state("networkidle")

        # Should land on the new page; it should contain the banner element
        self.assertTrue(
            self.page.url.endswith("/banner-e2e-page/")
            or "banner-e2e-page" in self.page.url,
            f"Unexpected final URL: {self.page.url}",
        )
        banner = self.page.locator("#page-banner")
        self.assertTrue(banner.count() > 0, "banner element not rendered after create")
