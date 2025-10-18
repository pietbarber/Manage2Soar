import pytest
from django.urls import reverse

from cms.models import Document, Page


@pytest.mark.django_db
def test_public_page_and_document_accessible_anonymous(client, settings, tmp_path):
    # Use local filesystem storage for the test so template file lookups work
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.MEDIA_ROOT = str(tmp_path)

    # Create a public top-level page with a document. Ensure the backing file exists.
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "public.pdf").write_bytes(b"%PDF-1.4 test")

    page = Page.objects.create(title="Public Page", slug="public-page", is_public=True)
    Document.objects.create(page=page, title="Public Doc", file="docs/public.pdf")

    # Prevent tests from attempting to contact GCS for file size lookups
    try:
        from storages.backends.gcloud import GoogleCloudStorage

        def _fake_size(self, name):
            return 123

        GoogleCloudStorage.size = _fake_size
    except Exception:
        pass

    # Visiting the page should be allowed without login
    url = reverse("cms_page", kwargs={"slug1": page.slug})
    resp = client.get(url)
    assert resp.status_code == 200

    # The page should include the document title
    assert b"Public Doc" in resp.content


@pytest.mark.django_db
def test_restricted_page_and_document_redirects_anonymous(client, settings, tmp_path):
    # Use filesystem storage so template file size won't hit GCS
    settings.DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
    settings.MEDIA_ROOT = str(tmp_path)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "private.pdf").write_bytes(b"%PDF-1.4 test")

    # Create a restricted page and document
    page = Page.objects.create(
        title="Private Page", slug="private-page", is_public=False
    )
    Document.objects.create(page=page, title="Private Doc", file="docs/private.pdf")

    # Prevent tests from attempting to contact GCS for file size lookups
    try:
        from storages.backends.gcloud import GoogleCloudStorage

        def _fake_size(self, name):
            return 123

        GoogleCloudStorage.size = _fake_size
    except Exception:
        pass

    # Visiting the page should redirect to login for anonymous user
    url = reverse("cms_page", kwargs={"slug1": page.slug})
    resp = client.get(url)
    # Expect redirect to login (302) or login page rendered
    assert resp.status_code in (302, 303)
    assert settings.LOGIN_URL in resp["Location"]
