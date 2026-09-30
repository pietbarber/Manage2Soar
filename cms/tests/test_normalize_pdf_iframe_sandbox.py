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


def test_dot_segment_escaping_trusted_prefix_is_not_trusted(settings):
    """A dot-segment that resolves outside the prefix must not be trusted.

    urlparse leaves ``..`` intact, but the browser's new URL() (used by the
    client check) resolves ``/cms/document-pdf/../admin/`` to ``/cms/admin/``.
    The server must normalize dot segments before matching, so such a URL is
    untrusted and keeps its sandbox.
    """
    # Resolves to /cms/admin/ — outside the trusted prefix.
    content = make_embed("https://example.com/cms/document-pdf/../admin/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_dot_segment_staying_within_prefix_is_trusted(settings):
    """A dot-segment that resolves back inside the prefix stays trusted.

    /cms/document-pdf/42/../53/ resolves to /cms/document-pdf/53/, which is
    still under the trusted prefix, so it must remain unsandboxed.
    """
    content = make_embed("/cms/document-pdf/42/../53/")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    # Trusted: no rewrite, no sandbox added.
    assert rewritten == 0
    assert "sandbox" not in new_content


def test_encoded_dot_segment_escaping_prefix_is_not_trusted(settings):
    """Percent-encoded dot segments must be resolved like the browser.

    new URL() resolves /cms/document-pdf/%2e%2e/admin/ to /cms/admin/, so a
    URL that percent-encodes its .. to escape the prefix must be untrusted
    and keep its sandbox.
    """
    content = make_embed(
        "https://example.com/cms/document-pdf/%2e%2e/admin/", sandbox=""
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_encoded_dot_segment_staying_within_prefix_is_trusted(settings):
    """An encoded .. that resolves back inside the prefix stays trusted.

    /cms/document-pdf/42/%2e%2e/53/ resolves to /cms/document-pdf/53/, still
    under the trusted prefix, so it must remain unsandboxed.
    """
    content = make_embed("/cms/document-pdf/42/%2e%2e/53/")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 0
    assert "sandbox" not in new_content


def test_backslash_separator_stays_within_prefix_is_trusted(settings):
    """For special schemes, a backslash is a path separator like the browser.

    new URL() treats /cms/document-pdf/42\\admin\\x.pdf as
    /cms/document-pdf/42/admin/x.pdf, which is under the prefix, so it stays
    trusted. A single encoded 4-dot segment is a literal filename (not ..
    navigation) and likewise stays within the prefix.
    """
    content = make_embed("https://example.com/cms/document-pdf/42\\admin\\x.pdf")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 0
    assert "sandbox" not in new_content


def test_legit_percent_encoded_filename_stays_trusted(settings):
    """Legitimate percent-encoding (%20 for a space) must not affect matching."""
    content = make_embed("https://example.com/cms/document-pdf/my%20bylaws.pdf")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 0
    assert "sandbox" not in new_content


def test_encoded_slash_is_not_decoded_to_separator(settings):
    """Encoded slashes (%2F) must not collapse into real path separators.

    new URL() keeps /cms%2Fdocument-pdf/42/ as-is (it does NOT become
    /cms/document-pdf/42/), so it does not sit under the /cms/document-pdf/
    prefix and must be untrusted. Blanket percent-decoding would wrongly
    broaden the allowlist here.
    """
    content = make_embed("https://example.com/cms%2Fdocument-pdf/42/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_encoded_backslash_is_not_decoded_to_separator(settings):
    """Encoded backslashes (%5C) stay literal, not path separators.

    new URL() keeps /cms/document-pdf/%5Cadmin%5Cx.pdf as-is, so it stays
    under the prefix (trusted). Only a raw backslash is a separator for the
    browser; percent-encoded backslashes must not be decoded into one.
    """
    content = make_embed("https://example.com/cms/document-pdf/%5Cadmin%5Cx.pdf")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    # %5C is not a real separator, so the path stays within the prefix and
    # the embed remains trusted (no sandbox added).
    assert rewritten == 0
    assert "sandbox" not in new_content


def test_self_closing_iframe_is_validated(settings):
    """A self-closing <iframe .../> must not produce malformed markup.

    The sandbox must be appended before the closing '/>' rather than after
    the '/', which would break the tag.
    """
    content = (
        '<div class="pdf-container">'
        '<iframe src="https://attacker.example/evil.pdf" width="100%"/>'
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"/>' in new_content
    # The broken form (slash followed by the attribute) must not appear.
    assert "/ sandbox=" not in new_content
    # Still idempotent.
    assert normalize_pdf_iframe_sandbox(new_content, [])[1] == 0


def test_greater_than_inside_quoted_attribute_does_not_truncate_iframe(settings):
    content = (
        '<div class="pdf-container">'
        '<iframe src="https://attacker.example/evil.pdf" title="A > B" '
        'width="100%"></iframe>'
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert (
        '<iframe src="https://attacker.example/evil.pdf" title="A > B" '
        f'width="100%" sandbox="{PDF_EMBED_SANDBOX}"></iframe>'
    ) in new_content


def test_trusted_removal_leaves_no_double_space(settings):
    """Removing a sandbox from a trusted embed must not leave a double space."""
    content = (
        '<div class="pdf-container">'
        '<iframe src="https://example.com/cms/document-pdf/42/" sandbox="" '
        'width="100%"></iframe>'
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert "sandbox" not in new_content
    assert "  " not in new_content


def test_nested_div_inside_container_is_sandboxed(settings):
    """An iframe nested one level deeper in a .pdf-container is still handled.

    The client-side closest('.pdf-container') matches any ancestor, so the
    server must sandbox an iframe inside a nested <div> too.
    """
    content = (
        '<div class="pdf-container">'
        '<div class="inner">'
        '<iframe src="https://attacker.example/evil.pdf" sandbox="" width="100%">'
        "</iframe>"
        "</div>"
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_sibling_div_after_closed_container_is_untouched(settings):
    """An iframe in a sibling div (after the container closed) is untouched."""
    content = (
        '<div class="pdf-container"></div>'
        '<div class="other">'
        '<iframe src="https://attacker.example/evil.pdf" sandbox="" width="100%">'
        "</iframe>"
        "</div>"
    )

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    # The iframe is not inside any .pdf-container, so it must not be touched.
    assert rewritten == 0
    assert new_content == content


def test_non_http_scheme_is_not_trusted(settings):
    """file:// and other non-HTTP schemes must never be trusted."""
    content = make_embed("file:///cms/document-pdf/42/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_protocol_relative_url_is_not_trusted(settings):
    """Protocol-relative URLs (//host/path) are cross-origin → untrusted."""
    content = make_embed("//attacker.example/cms/document-pdf/42/", sandbox="")

    with override_settings(
        TINYMCE_PDF_TRUSTED_URL_PREFIXES=["https://example.com/cms/document-pdf/"]
    ):
        new_content, rewritten = normalize_pdf_iframe_sandbox(
            content, settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES
        )

    assert rewritten == 1
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content


def test_single_quoted_sandbox_is_recognized(settings):
    """A single-quoted sandbox='' must be upgraded, not duplicated."""
    import re as _re

    content = (
        '<div class="pdf-container">'
        "<iframe src=\"https://attacker.example/evil.pdf\" sandbox='' "
        'width="100%" height="600">'
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
    assert f'sandbox="{PDF_EMBED_SANDBOX}"' in new_content
    # Exactly one sandbox attribute — the single-quoted one was replaced,
    # not left in place with a second attribute appended.
    assert len(_re.findall(r"sandbox=", new_content, _re.IGNORECASE)) == 1


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
