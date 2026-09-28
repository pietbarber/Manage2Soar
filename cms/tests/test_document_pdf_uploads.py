import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

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
