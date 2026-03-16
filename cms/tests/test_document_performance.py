from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse

from cms.models import Document, Page


def _use_filesystem_storage(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {},
        },
    }


@pytest.mark.django_db
def test_document_save_populates_file_size_bytes(settings, tmp_path):
    _use_filesystem_storage(settings)
    settings.MEDIA_ROOT = str(tmp_path)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    content = b"%PDF-1.4 test file"
    (docs_dir / "sample.pdf").write_bytes(content)

    page = Page.objects.create(title="Docs", slug="docs-page", is_public=True)
    doc = Document.objects.create(page=page, title="Sample", file="docs/sample.pdf")

    assert doc.file_size_bytes == len(content)


@pytest.mark.django_db
def test_cms_page_does_not_call_storage_size_when_file_size_cached(
    client, settings, tmp_path
):
    _use_filesystem_storage(settings)
    settings.MEDIA_ROOT = str(tmp_path)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "cached.pdf").write_bytes(b"%PDF-1.4 cached")

    page = Page.objects.create(title="Newsletter", slug="newsletter", is_public=True)
    doc = Document.objects.create(page=page, title="Cached", file="docs/cached.pdf")
    assert doc.file_size_bytes is not None

    with patch(
        "django.core.files.storage.FileSystemStorage.size",
        side_effect=AssertionError,
    ):
        response = client.get(reverse("cms:cms_page", kwargs={"path": page.slug}))

    assert response.status_code == 200
    assert b"Cached" in response.content


@pytest.mark.django_db
def test_backfill_document_sizes_command_updates_missing_sizes(settings, tmp_path):
    _use_filesystem_storage(settings)
    settings.MEDIA_ROOT = str(tmp_path)

    docs_dir = Path(tmp_path) / "docs"
    docs_dir.mkdir()
    payload = b"%PDF-1.4 backfill"
    (docs_dir / "backfill.pdf").write_bytes(payload)

    page = Page.objects.create(title="Backfill", slug="backfill-page", is_public=True)
    doc = Document.objects.create(page=page, title="Backfill", file="docs/backfill.pdf")

    Document.objects.filter(pk=doc.pk).update(file_size_bytes=None)
    doc.refresh_from_db()
    assert doc.file_size_bytes is None

    call_command("backfill_document_sizes", "--only-missing", "--batch-size", "1")

    doc.refresh_from_db()
    assert doc.file_size_bytes == len(payload)
