from types import SimpleNamespace

import pytest

from utils.upload_document_obfuscated import upload_document_obfuscated


def make_instance(slug="test-page"):
    return SimpleNamespace(page=SimpleNamespace(slug=slug))


def make_instance_without_page():
    return SimpleNamespace(page=None)


@pytest.fixture
def fixed_token(monkeypatch):
    monkeypatch.setattr(
        "utils.upload_document_obfuscated.secrets.token_urlsafe",
        lambda _length: "xfds3Fj",
    )
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


def test_upload_document_obfuscated_sanitizes_control_chars_and_unicode(
    fixed_token,
):
    instance = make_instance()

    null_byte = upload_document_obfuscated(instance, "Board\x00Agenda.pdf")
    rlo = upload_document_obfuscated(instance, "Board\u202eAgenda.pdf")

    assert null_byte == "cms/test-page/BoardAgenda-xfds3Fj.pdf"
    assert rlo == "cms/test-page/BoardAgenda-xfds3Fj.pdf"


def test_upload_document_obfuscated_handles_absolute_and_windows_paths(
    fixed_token,
):
    """
    Verify os.path.basename() strips absolute and Windows-style paths.

    Note: This function assumes Unix-style path handling. On Windows,
    os.path.basename("C:\\evil\\file.pdf") would correctly extract "file.pdf",
    but on Linux/Unix, backslashes are treated as regular filename characters.
    The regex sanitization removes them regardless of platform.
    """
    instance = make_instance()

    # Unix absolute path
    unix_abs = upload_document_obfuscated(instance, "/etc/passwd.pdf")
    # Windows-style path (note: on Linux, backslash is a valid char, so
    # os.path.basename won't strip it, but the regex sanitization will remove it)
    windows_path = upload_document_obfuscated(instance, "C:\\evil\\file.pdf")

    assert unix_abs == "cms/test-page/passwd-xfds3Fj.pdf"
    assert "/etc" not in unix_abs
    # On Linux, backslashes are kept by basename but stripped by regex sanitization.
    # The entire "C:\evil\file" becomes the base name, and ".pdf" is the extension.
    # After sanitization, "C:\evil\file" becomes "Cevilfile" (backslashes removed).
    assert windows_path == "cms/test-page/Cevilfile-xfds3Fj.pdf"
    assert "\\" not in windows_path


def test_upload_document_obfuscated_trusts_page_slug(fixed_token):
    """
    Verify that page slugs are used as-is in the path.

    Django's SlugField enforces safe characters (letters, numbers, hyphens,
    underscores), so we trust the slug without additional sanitization.
    This test documents that assumption.
    """
    # Standard slug with hyphens (normal case)
    instance = make_instance("board-documents-2025")
    result = upload_document_obfuscated(instance, "agenda.pdf")
    assert result == "cms/board-documents-2025/agenda-xfds3Fj.pdf"

    # Slug with underscores (also valid per SlugField)
    instance_underscore = make_instance("board_docs")
    result_underscore = upload_document_obfuscated(instance_underscore, "notes.pdf")
    assert result_underscore == "cms/board_docs/notes-xfds3Fj.pdf"
