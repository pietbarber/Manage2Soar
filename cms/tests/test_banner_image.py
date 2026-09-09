"""
Tests for the CMS banner_image form field on the create/edit page forms.

Issue #1047: Banner image should be settable from the site-UI create and edit
forms (not just Django admin), with parity between the two.
"""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cms.models import Page
from cms.views import CmsPageForm

User = get_user_model()

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="test_media_cms_banner_")


def tearDownModule():
    """Remove uploaded banner files created during this test module."""
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


def _make_banner_upload(name="banner.png", size=(400, 60), color=(20, 40, 80)):
    """Build a valid PNG SimpleUploadedFile (PIL-verified for ImageField)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    buf.seek(0)
    return SimpleUploadedFile(name=name, content=buf.read(), content_type="image/png")


def _base_form_data(page_id=None, parent_id=None):
    data = {
        "title": "Banner Page",
        "slug": f"banner-{page_id or parent_id or 'x'}",
        "content": "<p>Content</p>",
        "is_public": "on",
        "documents-TOTAL_FORMS": "0",
        "documents-INITIAL_FORMS": "0",
        "documents-MIN_NUM_FORMS": "0",
        "documents-MAX_NUM_FORMS": "1000",
    }
    if parent_id is not None:
        data["parent"] = parent_id
    return data


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CmsPageFormBannerFieldTests(TestCase):
    """Direct ModelForm tests: banner_image is exposed and optional."""

    def test_form_exposes_banner_image(self):
        """banner_image is in the form's fields (added by #1047)."""
        self.assertIn("banner_image", CmsPageForm().fields)

    def test_form_is_valid_without_banner(self):
        """Form is valid without a banner (blank/null field)."""
        form = CmsPageForm(
            data={
                "title": "T",
                "slug": "s",
                "content": "<p>x</p>",
                "is_public": True,
            },
            files={},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_persists_uploaded_banner(self):
        """An uploaded banner is saved onto the new page instance."""
        page = Page.objects.create(title="Seed", slug="seed", is_public=False)
        form = CmsPageForm(
            data={
                "title": "T",
                "slug": "s",
                "content": "<p>x</p>",
                "is_public": True,
            },
            files={"banner_image": _make_banner_upload()},
            instance=page,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertTrue(saved.banner_image)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CreatePageBannerFormTests(TestCase):
    """Create page view: banner field present on GET and persisted on POST."""

    def setUp(self):
        self.client = Client()
        self.webmaster = User.objects.create_user(
            username="webmaster",
            email="webmaster@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.webmaster.webmaster = True
        self.webmaster.save()

    def test_create_get_shows_banner_field(self):
        self.client.force_login(self.webmaster)
        response = self.client.get(reverse("cms:create_page"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("banner_image", response.context["form"].fields)
        self.assertContains(response, 'name="banner_image"')

    def test_create_post_persists_banner(self):
        self.client.force_login(self.webmaster)
        data = _base_form_data()
        data["slug"] = "created-with-banner"
        data["banner_image"] = _make_banner_upload()

        response = self.client.post(reverse("cms:create_page"), data, follow=False)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))

        page = Page.objects.get(slug="created-with-banner")
        self.assertTrue(page.banner_image)

    def test_create_post_without_banner_still_saves(self):
        self.client.force_login(self.webmaster)
        data = _base_form_data()
        data["slug"] = "created-no-banner"
        response = self.client.post(reverse("cms:create_page"), data, follow=False)
        self.assertEqual(response.status_code, 302)
        page = Page.objects.get(slug="created-no-banner")
        self.assertFalse(page.banner_image)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class EditPageBannerFormTests(TestCase):
    """Edit page view: banner field present on GET, persists on POST."""

    def setUp(self):
        self.client = Client()
        self.page = Page.objects.create(
            title="Test Page",
            slug="test-banner-page",
            content="<p>Original</p>",
            is_public=False,
        )
        self.director = User.objects.create_user(
            username="director",
            email="director@test.com",
            password="testpass123",
            membership_status="Full Member",
        )
        self.director.director = True
        self.director.save()

    def test_edit_get_shows_banner_field(self):
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("banner_image", response.context["form"].fields)
        self.assertContains(response, 'name="banner_image"')

    def test_edit_get_with_existing_banner_shows_clear(self):
        """When a banner is set, the ClearableFileInput 'Clear' checkbox appears."""
        self.page.banner_image = _make_banner_upload(name="existing.png")
        self.page.save()
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # ClearableFileInput renders a checkbox named "banner_image-clear"
        self.assertContains(response, "banner_image-clear")

    def test_edit_post_persists_banner(self):
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        data = _base_form_data(page_id=self.page.id)
        data["banner_image"] = _make_banner_upload(name="new.png")

        response = self.client.post(url, data, follow=False)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        self.page.refresh_from_db()
        self.assertTrue(self.page.banner_image)

    def test_edit_post_without_banner_clears_existing(self):
        """Clearing via the clear-checkbox leaves banner_image empty."""
        self.page.banner_image = _make_banner_upload(name="existing.png")
        self.page.save()
        self.client.force_login(self.director)
        url = reverse("cms:edit_page", kwargs={"page_id": self.page.id})
        data = _base_form_data(page_id=self.page.id)
        data["banner_image-clear"] = "on"  # simulate the ClearableFileInput checkbox

        response = self.client.post(url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.page.refresh_from_db()
        self.assertFalse(self.page.banner_image)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CreateEditBannerParityTests(TestCase):
    """Create and edit forms expose the banner field identically (Issue #1047)."""

    def test_field_order_and_label_parity(self):
        """Both forms derive from the same CmsPageForm; banner is present on each."""
        create_form = CmsPageForm()
        edit_form = CmsPageForm(
            instance=Page.objects.create(
                title="Seed", slug="seed-parity", is_public=False
            )
        )
        self.assertIn("banner_image", create_form.fields)
        self.assertIn("banner_image", edit_form.fields)
        # Both use the same Meta, so the field ordering is identical
        self.assertEqual(list(create_form.fields.keys()), list(edit_form.fields.keys()))
