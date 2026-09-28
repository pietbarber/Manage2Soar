from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings

from cms.models import Document, Page, upload_document_to
from cms.views import DocumentForm


@pytest.mark.django_db
def test_pdf_upload_requires_pdf_content():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile(
        "report.pdf", b"<html>not a PDF</html>", content_type="application/pdf"
    )
    form = DocumentForm(files={"file": upload}, instance=Document(page=page))

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_pdf_upload_without_content_type_still_requires_pdf_signature():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile(
        "report.pdf", b"<html>not a PDF</html>", content_type=None
    )
    form = DocumentForm(files={"file": upload}, instance=Document(page=page))

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_document_form_without_file_returns_required_error():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    form = DocumentForm(data={}, files={}, instance=Document(page=page))

    assert not form.is_valid()
    assert "file" in form.errors


@pytest.mark.django_db
def test_valid_pdf_upload_uses_dedicated_path():
    page = Page.objects.create(title="PDF uploads", slug="pdf-uploads")
    upload = SimpleUploadedFile(
        "report.pdf", b"%PDF-1.7\ncontent", content_type="application/pdf"
    )
    document = Document(page=page, file=upload)
    form = DocumentForm(files={"file": upload}, instance=document)

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
def test_legacy_pdf_command_dry_run_does_not_move_files(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, _ = create_legacy_document(tmp_path, b"%PDF-1.7\ncontent")
        output = StringIO()

        call_command("migrate_legacy_pdf_documents", stdout=output)

        document.refresh_from_db()
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
        assert (tmp_path / document.file.name).exists()
        assert "ready to migrate: 1" in output.getvalue()


@pytest.mark.django_db
def test_legacy_pdf_command_apply_rewrites_url_and_deletes_old_file(
    tmp_path, django_capture_on_commit_callbacks
):
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

        with django_capture_on_commit_callbacks(execute=True):
            call_command("migrate_legacy_pdf_documents", "--apply")

        document.refresh_from_db()
        page.refresh_from_db()
        assert document.file.name == "cms-pdfs/legacy-pdfs/legacy.pdf"
        assert (tmp_path / document.file.name).exists()
        assert not (tmp_path / "cms/legacy-pdfs/legacy.pdf").exists()
        assert old_url not in page.content
        assert document.file.url in page.content


@pytest.mark.django_db
def test_legacy_pdf_command_skips_invalid_signature(tmp_path):
    with override_settings(
        MEDIA_ROOT=str(tmp_path),
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        },
    ):
        document, _ = create_legacy_document(tmp_path, b"<html>not a PDF</html>")
        output = StringIO()

        call_command("migrate_legacy_pdf_documents", stdout=output)

        document.refresh_from_db()
        assert document.file.name == "cms/legacy-pdfs/legacy.pdf"
        assert "invalid: 1" in output.getvalue()
