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


def test_cross_origin_same_path_is_not_trusted(settings):
    """An absolute URL on a different origin must never be trusted."""
    content = make_embed("https://attacker.example/cms/document-pdf/42/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_data_src_does_not_mask_untrusted_src(settings):
    """data-src must not be confused with the real src attribute.

    A trusted data-src followed by an untrusted real src is untrusted —
    the real src is what the browser loads, and it must be sandboxed.
    """
    content = (
        '<div class="pdf-container">'
        f'<iframe data-src="https://example.com/cms/document-pdf/42/" '
        'src="https://attacker.example/evil.pdf" sandbox="" '
        'width="100%" height="600" loading="lazy">'
        "</iframe>"
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    # The untrusted real src must be upgraded to the controlled sandbox.
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content
    assert 'sandbox=""' not in new_content


@pytest.mark.django_db
def test_apply_skips_rows_changed_concurrently(settings, capsys):
    """A concurrent editor save must not be clobbered by a stale snapshot."""
    original = make_embed(UNTRUSTED_GCS_URL, sandbox="")
    page = Page.objects.create(title="Legacy", slug="legacy", content=original)

    # The editor concurrently swaps the PDF URL and saves an already
    # normalized embed for the new URL, after the command read the old row.
    new_pdf_url = (
        "https://storage.googleapis.com/my-bucket/media/cms-pdfs/club/fresh.pdf"
    )
    concurrent_save = make_embed(new_pdf_url, sandbox=PDF_EMBED_SANDBOX)

    from cms.management.commands import normalize_pdf_iframe_sandbox as mod

    real_normalize = mod.normalize_pdf_iframe_sandbox
    calls = {"count": 0}

    def racing_normalize(content, prefixes):
        calls["count"] += 1
        # First call is the command's initial read (stale content). The
        # concurrent editor save lands right after that read, so the in-lock
        # re-read will see the fresh, already-normalized content.
        if calls["count"] == 1:
            Page.objects.filter(pk=page.pk).update(content=concurrent_save)
        return real_normalize(content, prefixes)

    mod.normalize_pdf_iframe_sandbox = racing_normalize
    try:
        call_command("normalize_pdf_iframe_sandbox", "--apply")
    finally:
        mod.normalize_pdf_iframe_sandbox = real_normalize

    output = capsys.readouterr().out
    assert "skipped, content changed" in output
    assert "conflicts skipped: 1" in output

    page.refresh_from_db()
    # The concurrent save (new URL) wins; the stale normalization that would
    # have rewritten the old URL was not applied.
    assert page.content == concurrent_save
    assert new_pdf_url in page.content
    assert UNTRUSTED_GCS_URL not in page.content


@pytest.mark.django_db
def test_apply_reports_fresh_rewrites_when_concurrent_edit_changes_count(
    settings, capsys
):
    """Apply-mode summary must use the locked re-read's rewrite count.

    If a concurrent edit adds a new untrusted iframe after the command's
    initial read, the locked re-read will see more rewrites than the
    initial count. The reported and total rewrite counts must reflect the
    fresh (locked) value, not the stale pre-lock value.
    """
    # Initial read sees 1 untrusted iframe to rewrite.
    initial_content = make_embed(UNTRUSTED_GCS_URL, sandbox="")
    page = Page.objects.create(title="Legacy", slug="legacy", content=initial_content)

    # Concurrent edit adds a SECOND untrusted iframe (already in
    # .pdf-container form) right after the initial read, so the locked
    # re-read sees 2 rewrites.
    concurrent_save = (
        initial_content[: -len("</div>")]
        + make_embed(
            "https://storage.googleapis.com/my-bucket/media/cms-pdfs/club/second.pdf",
            sandbox="",
        )
        + "</div>"
    )

    from cms.management.commands import normalize_pdf_iframe_sandbox as mod

    real_normalize = mod.normalize_pdf_iframe_sandbox
    calls = {"count": 0}

    def racing_normalize(content, prefixes):
        calls["count"] += 1
        # First call is the command's initial read. Swap in the fresh
        # content so the locked re-read sees it.
        if calls["count"] == 1:
            Page.objects.filter(pk=page.pk).update(content=concurrent_save)
        return real_normalize(content, prefixes)

    mod.normalize_pdf_iframe_sandbox = racing_normalize
    try:
        call_command("normalize_pdf_iframe_sandbox", "--apply")
    finally:
        mod.normalize_pdf_iframe_sandbox = real_normalize

    output = capsys.readouterr().out
    # The reported per-row count and the total must both be 2 (fresh),
    # not 1 (the stale pre-lock value).
    assert "2 iframe(s) rewritten" in output
    assert "iframes rewritten: 2" in output
    # Verify the applied content reflects the locked re-read's output.
    page.refresh_from_db()
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in page.content
    assert 'sandbox=""' not in page.content


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
