from types import SimpleNamespace

import pytest

from utils.upload_document_obfuscated import upload_document_obfuscated


def make_instance(slug="test-page"):
    return SimpleNamespace(page=SimpleNamespace(slug=slug))


def make_instance_without_page():
    return SimpleNamespace(page=None)


@pytest.fixture
def fixed_token(monkeypatch):
    monkeypatch.setattr("secrets.token_urlsafe", lambda _length: "xfds3Fj")
    return "xfds3Fj"


def test_upload_document_obfuscated_appends_token_and_preserves_extension(
    fixed_token,
):
    instance = make_instance()
    result = upload_document_obfuscated(instance, "Board-Agenda-2025.pdf")

    assert result == "cms/test-page/Board-Agenda-2025-xfds3Fj.pdf"


def test_upload_document_obfuscated_sanitizes_filename(fixed_token):
    instance = make_instance("restricted")
    filename = "../evil/Board Agenda (final).pdf"

    expected_name = "Board_Agenda_final"
    result = upload_document_obfuscated(instance, filename)

    assert result == f"cms/restricted/{expected_name}-xfds3Fj.pdf"
    assert result.endswith(".pdf")
    assert ".." not in result


def test_upload_document_obfuscated_defaults_uncategorized_without_page(
    fixed_token,
):
    instance = make_instance_without_page()
    result = upload_document_obfuscated(instance, "Board-Agenda-2025.pdf")

    assert result == "cms/uncategorized/Board-Agenda-2025-xfds3Fj.pdf"


def test_upload_document_obfuscated_falls_back_to_file_on_empty_name(
    fixed_token,
):
    instance = make_instance()
    result = upload_document_obfuscated(instance, "   .pdf")

    assert result == "cms/test-page/file-xfds3Fj.pdf"


def test_upload_document_obfuscated_falls_back_on_special_char_name(
    fixed_token,
):
    instance = make_instance()
    result = upload_document_obfuscated(instance, "!@#$.pdf")

    assert result == "cms/test-page/file-xfds3Fj.pdf"


def test_upload_document_obfuscated_handles_multiple_dots(fixed_token):
    instance = make_instance()
    result = upload_document_obfuscated(instance, "Board.Agenda.2025.pdf")

    assert result == "cms/test-page/BoardAgenda2025-xfds3Fj.pdf"


def test_upload_document_obfuscated_handles_extension_edge_cases(
    fixed_token,
):
    instance = make_instance()

    no_extension = upload_document_obfuscated(instance, "README")
    upper_extension = upload_document_obfuscated(instance, "Board.PDF")
    tarball = upload_document_obfuscated(instance, "archive.tar.gz")
    malicious_ext = upload_document_obfuscated(instance, "report.pdf<script>")

    assert no_extension == "cms/test-page/README-xfds3Fj"
    assert upper_extension == "cms/test-page/Board-xfds3Fj.PDF"
    assert tarball == "cms/test-page/archivetar-xfds3Fj.gz"
    assert malicious_ext == "cms/test-page/file-xfds3Fj"
    assert "." not in malicious_ext.rsplit("/", 1)[-1]


def test_upload_document_obfuscated_sanitizes_control_chars_and_unicode(
    fixed_token,
):
    instance = make_instance()

    null_byte = upload_document_obfuscated(instance, "Board\x00Agenda.pdf")
    rlo = upload_document_obfuscated(instance, "Board\u202eAgenda.pdf")

    assert null_byte == "cms/test-page/BoardAgenda-xfds3Fj.pdf"
    assert rlo == "cms/test-page/BoardAgenda-xfds3Fj.pdf"
