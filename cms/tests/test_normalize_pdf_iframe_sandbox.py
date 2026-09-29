"""Tests for the normalize_pdf_iframe_sandbox management command (Issue #1069)."""

import pytest
from django.core.management import call_command
from django.test import override_settings

from cms.management.commands.normalize_pdf_iframe_sandbox import (
    PDF_EMBED_SANDBOX,
    normalize_pdf_iframe_sandbox,
)
from cms.models import HomePageContent, Page

UNTRUSTED_GCS_URL = (
    "https://storage.googleapis.com/my-bucket/media/cms-pdfs/club/bylaws.pdf"
)


def make_embed(url, sandbox=None):
    sandbox_attr = f' sandbox="{sandbox}"' if sandbox is not None else ""
    return (
        '<div class="pdf-container">'
        f'<iframe src="{url}"{sandbox_attr} width="100%" height="600" '
        'frameborder="0" loading="lazy" title="Embedded PDF document">'
        "</iframe>"
        '<p><small><a href="'
        f'{url}" target="_blank" rel="noopener noreferrer">'
        "Open PDF in new tab</a></small></p>"
        "</div>"
    )


@pytest.mark.django_db
def test_dry_run_reports_but_changes_nothing(settings, capsys):
    page = Page.objects.create(
        title="Legacy",
        slug="legacy",
        content=make_embed(UNTRUSTED_GCS_URL, sandbox=""),
    )

    call_command("normalize_pdf_iframe_sandbox")

    output = capsys.readouterr().out
    assert "ready to rewrite" in output
    page.refresh_from_db()
    assert 'sandbox=""' in page.content
    assert PDF_EMBED_SANDBOX not in page.content


@pytest.mark.django_db
def test_apply_rewrites_empty_sandbox(settings, capsys):
    page = Page.objects.create(
        title="Legacy",
        slug="legacy",
        content=make_embed(UNTRUSTED_GCS_URL, sandbox=""),
    )

    call_command("normalize_pdf_iframe_sandbox", "--apply")

    output = capsys.readouterr().out
    assert "complete" in output
    page.refresh_from_db()
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in page.content


@pytest.mark.django_db
def test_apply_adds_sandbox_when_absent(settings):
    page = Page.objects.create(
        title="Legacy",
        slug="legacy",
        content=make_embed(UNTRUSTED_GCS_URL),
    )

    call_command("normalize_pdf_iframe_sandbox", "--apply")

    page.refresh_from_db()
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in page.content


@pytest.mark.django_db
def test_idempotent_second_run_reports_zero(settings, capsys):
    page = Page.objects.create(
        title="Legacy",
        slug="legacy",
        content=make_embed(UNTRUSTED_GCS_URL, sandbox=""),
    )

    call_command("normalize_pdf_iframe_sandbox", "--apply")
    capsys.readouterr()
    call_command("normalize_pdf_iframe_sandbox", "--apply")

    output = capsys.readouterr().out
    assert "iframes rewritten: 0" in output
    page.refresh_from_db()
    assert page.content.count(PDF_EMBED_SANDBOX) == 1


@pytest.mark.django_db
def test_trusted_endpoint_stays_unsandboxed(settings):
    trusted = f"http://testserver/cms/document-pdf/"
    page = Page.objects.create(
        title="Trusted",
        slug="trusted",
        content=make_embed(f"{trusted}42/"),
    )

    with override_settings(TINYMCE_PDF_TRUSTED_URL_PREFIXES=[trusted]):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            page.content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 0
    assert new_content == page.content


@pytest.mark.django_db
def test_trusted_embed_with_sandbox_has_it_removed(settings):
    trusted = "http://testserver/cms/document-pdf/"
    content = make_embed(f"{trusted}42/", sandbox="")

    with override_settings(TINYMCE_PDF_TRUSTED_URL_PREFIXES=[trusted]):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert "sandbox" not in new_content


@pytest.mark.django_db
def test_relative_trusted_url_matches_full_url_prefix(settings):
    """Stored content uses relative URLs; config prefixes are full URLs."""
    content = make_embed("/cms/document-pdf/42/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert "sandbox" not in new_content


def test_evil_prefix_path_is_not_trusted(settings):
    """A look-alike prefix (e.g. /cms/document-pdf-evil/) must not match."""
    content = make_embed("/cms/document-pdf-evil/3/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


@pytest.mark.django_db
def test_non_pdf_container_iframes_are_untouched(settings):
    # YouTube-style iframe (not inside .pdf-container) must be ignored.
    content = (
        '<iframe src="https://www.youtube.com/embed/abc123" width="560" '
        'height="315" frameborder="0" allow="autoplay" '
        'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>'
    )

    with override_settings(TINYMCE_PDF_TRUSTED_URL_PREFIXES=[]):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 0
    assert new_content == content


@pytest.mark.django_db
def test_normalizes_homepage_content(settings):
    homepage = HomePageContent.objects.create(
        slug="home",
        content=make_embed(UNTRUSTED_GCS_URL, sandbox=""),
    )

    call_command("normalize_pdf_iframe_sandbox", "--apply")

    homepage.refresh_from_db()
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in homepage.content


def test_normalize_helper_handles_mixed_content(settings):
    untrusted = make_embed(UNTRUSTED_GCS_URL, sandbox="")
    trusted = make_embed("/cms/document-pdf/7/")
    content = untrusted + trusted

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["http://testserver/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content
    assert new_content.count("sandbox") == 1
