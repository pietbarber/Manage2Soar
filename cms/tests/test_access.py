import logging

import pytest
from django.test import override_settings
from django.urls import reverse

from cms.models import Document, Page


@pytest.mark.django_db
def test_controlled_pdf_endpoint_sets_safe_inline_headers(client, tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        file_path = tmp_path / "cms" / "public-page" / "public.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"%PDF-1.7 test")
        page = Page.objects.create(title="Public Page", slug="public-page")
        document = Document.objects.create(
            page=page,
            title="Public Doc",
            file="cms/public-page/public.pdf",
        )

        response = client.get(reverse("cms:document_pdf", args=[document.id]))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "SAMEORIGIN"
        assert response["Content-Security-Policy"] == "frame-ancestors 'self'"
        assert b"".join(response.streaming_content) == b"%PDF-1.7 test"


def test_pdf_viewer_assets_are_same_origin_and_traversal_safe(client):
    viewer = client.get("/cms/pdf-viewer/pdfjs-viewer/viewer.html")
    module = client.get("/cms/pdf-viewer/vendor/pdfjs/build/pdf.mjs")
    traversal = client.get("/cms/pdf-viewer/../manage2soar/settings.py")

    assert viewer.status_code == 200
    assert viewer["Content-Type"].startswith("text/html")
    assert viewer["X-Frame-Options"] == "SAMEORIGIN"
    assert viewer["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert module.status_code == 200
    assert module["Content-Type"].startswith("text/javascript")
    assert traversal.status_code == 404


@pytest.mark.django_db
def test_controlled_pdf_endpoint_requires_page_access(client, tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        file_path = tmp_path / "cms" / "private-page" / "private.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"%PDF-1.7 test")
        page = Page.objects.create(
            title="Private Page", slug="private-page", is_public=False
        )
        document = Document.objects.create(
            page=page,
            title="Private Doc",
            file="cms/private-page/private.pdf",
        )

        response = client.get(reverse("cms:document_pdf", args=[document.id]))

        assert response.status_code == 302
        assert "next=/cms/document-pdf/" in response["Location"]


@pytest.mark.django_db
def test_controlled_pdf_endpoint_requires_ancestor_access(client, tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        file_path = tmp_path / "cms" / "child-page" / "child.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"%PDF-1.7 test")
        parent = Page.objects.create(
            title="Private Parent", slug="private-parent", is_public=False
        )
        child = Page.objects.create(
            title="Public Child", slug="public-child", parent=parent, is_public=True
        )
        document = Document.objects.create(page=child, file="cms/child-page/child.pdf")

        response = client.get(reverse("cms:document_pdf", args=[document.id]))

        assert response.status_code == 302
        assert "next=/cms/document-pdf/" in response["Location"]


@pytest.mark.django_db
def test_controlled_pdf_endpoint_rejects_invalid_pdf_signature(client, tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        file_path = tmp_path / "cms" / "public-page" / "invalid.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"not a PDF")
        page = Page.objects.create(title="Public Page", slug="public-page")
        document = Document.objects.create(
            page=page, file="cms/public-page/invalid.pdf"
        )

        response = client.get(reverse("cms:document_pdf", args=[document.id]))

        assert response.status_code == 403


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
    document = Document.objects.create(
        page=page,
        title="Public Doc",
        file="docs/public.pdf",
    )

    # Prevent tests from attempting to contact GCS for file size lookups
    try:
        from storages.backends.gcloud import GoogleCloudStorage

        def _fake_size(self, name):
            return 123

        GoogleCloudStorage.size = _fake_size
    except (ImportError, AttributeError) as e:
        logging.info(f"GoogleCloudStorage not available in test environment: {e}")

    # Visiting the page should be allowed without login
    url = reverse("cms:cms_page", kwargs={"path": page.slug})
    resp = client.get(url)
    assert resp.status_code == 200

    # The page should include the document title
    assert b"Public Doc" in resp.content
    assert reverse("cms:document_pdf", args=[document.id]).encode() in resp.content


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
    except (ImportError, AttributeError) as e:
        logging.info(f"GoogleCloudStorage not available in test environment: {e}")

    # Visiting the page should redirect to login for anonymous user
    url = reverse("cms:cms_page", kwargs={"path": page.slug})
    resp = client.get(url)
    # Expect redirect to login (302) or login page rendered
    assert resp.status_code in (302, 303)
    assert settings.LOGIN_URL in resp["Location"]
