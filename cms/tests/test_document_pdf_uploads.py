from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models.query import QuerySet
from django.test import override_settings
from django.urls import reverse
from django.utils.datastructures import MultiValueDict

from cms.models import Document, HomePageContent, Page, upload_document_to
from cms.views import DocumentForm


@pytest.mark.django_db
def test_pdf_upload_requires_pdf_content():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile(
        "report.pdf", b"<html>not a PDF</html>", content_type="application/pdf"
    )
    form = DocumentForm(
        files=MultiValueDict({"file": [upload]}),
        instance=Document(page=page),
    )

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_pdf_upload_without_content_type_still_requires_pdf_signature():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile("report.pdf", b"<html>not a PDF</html>")
    setattr(upload, "content_type", None)
    form = DocumentForm(
        files=MultiValueDict({"file": [upload]}),
        instance=Document(page=page),
    )

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_document_form_without_file_returns_required_error():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    form = DocumentForm(
        data={},
        files=MultiValueDict(),
        instance=Document(page=page),
    )

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_valid_pdf_upload_uses_dedicated_path():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile(
        "report.pdf", b"%PDF-1.7\ncontent", content_type="application/octet-stream"
    )
    document = Document(page=page, file=upload)
    form = DocumentForm(files=MultiValueDict({"file": [upload]}), instance=document)

    assert form.is_valid(), form.errors
    assert upload_document_to(document, "report.pdf") == (
        "cms-pdfs/pdf-uploads/report.pdf"
    )


def create_legacy_document(tmp_path, content, page_content=""):
    page = Page.objects.create(
        title="Legacy PDFs", slug="legacy-pdfs", content=page_content
    )
    legacy_path = tmp_path / "cms" / "legacy-pdfs" / "legacy.pdf"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_bytes(content)
    document = Document.objects.create(page=page, file="cms/legacy-pdfs/legacy.pdf")
    return document, page


@pytest.mark.django_db
def test_legacy_pdf_command_includes_private_pages(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, page = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        page.is_public = False
        page.content = f'<a href="{document.file.url}">PDF</a>'
        page.save(update_fields=["is_public", "content", "updated_at"])

        call_command("migrate_legacy_pdf_documents", "--apply")

        page.refresh_from_db()
        assert reverse("cms:document_pdf", args=[document.id]) in page.content


@pytest.mark.django_db
def test_legacy_pdf_command_dry_run_does_not_move_files(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, page = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        old_url = document.file.url
        page.content = f'<a href="https://club.example{old_url}">PDF</a>'
        page.save(update_fields=["content", "updated_at"])
        output = StringIO()

        call_command("migrate_legacy_pdf_documents", stdout=output)

        document.refresh_from_db()
        page.refresh_from_db()
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
        assert (tmp_path / document.file.name).exists()
        assert f"https://club.example{old_url}" in page.content
        assert "references ready to rewrite: 1" in output.getvalue()


@pytest.mark.django_db
def test_legacy_pdf_command_apply_rewrites_page_url_without_moving_file(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, page = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        old_url = document.file.url
        page.content = f'<a href="https://club.example{old_url}">PDF</a>'
        page.save(update_fields=["content", "updated_at"])

        call_command("migrate_legacy_pdf_documents", "--apply")

        document.refresh_from_db()
        page.refresh_from_db()
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
        assert (tmp_path / document.file.name).exists()
        assert old_url not in page.content
        assert (
            f"https://club.example{reverse('cms:document_pdf', args=[document.id])}"
            in page.content
        )


@pytest.mark.django_db
def test_legacy_pdf_command_rewrites_homepage_url(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, _ = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        old_url = document.file.url
        homepage = HomePageContent.objects.create(
            title="Home", slug="legacy-home", content=f'<a href="{old_url}">PDF</a>'
        )

        call_command("migrate_legacy_pdf_documents", "--apply")

        homepage.refresh_from_db()
        assert old_url not in homepage.content
        assert reverse("cms:document_pdf", args=[document.id]) in homepage.content


@pytest.mark.django_db
def test_legacy_pdf_command_skips_invalid_signature(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, page = create_legacy_document(tmp_path, b"<html>not a PDF</html>")
        old_url = document.file.url
        page.content = f'<a href="{old_url}">PDF</a>'
        page.save(update_fields=["content", "updated_at"])
        output = StringIO()

        call_command("migrate_legacy_pdf_documents", "--apply", stdout=output)

        document.refresh_from_db()
        page.refresh_from_db()
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
        assert old_url not in page.content
        assert reverse("cms:document_pdf", args=[document.id]) in page.content
        assert "invalid: 1" in output.getvalue()


@pytest.mark.django_db
def test_legacy_pdf_command_keeps_references_when_rewrite_fails(tmp_path, monkeypatch):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, page = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        old_url = document.file.url
        page.content = f'<a href="{old_url}">PDF</a>'
        page.save(update_fields=["content", "updated_at"])
        original_update = QuerySet.update

        def fail_page_content_update(queryset, **kwargs):
            if queryset.model is Page and "content" in kwargs:
                raise RuntimeError("database write failed")
            return original_update(queryset, **kwargs)

        monkeypatch.setattr(QuerySet, "update", fail_page_content_update)

        call_command("migrate_legacy_pdf_documents", "--apply")

        page.refresh_from_db()
        assert old_url in page.content
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
