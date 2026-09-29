"""Normalize the sandbox attribute on legacy PDF embed iframes (Issue #1069).

Issue #1067 hardened CMS PDF embeds by saving an empty ``sandbox=""``
attribute on ``.pdf-container`` iframes whose URL is not on the trusted
prefix allowlist. An empty sandbox is the most restrictive value and
breaks Chrome's built-in PDF viewer ("This page has been blocked by
Chrome").

This command rewrites stored CMS content so that:

* untrusted ``.pdf-container`` iframes carry
  ``sandbox="allow-scripts allow-same-origin"`` (the value required for
  the PDF viewer to work), and
* iframes pointing at a trusted prefix
  (``TINYMCE_PDF_TRUSTED_URL_PREFIXES``, e.g. ``/cms/document-pdf/``)
  remain unsandboxed, as intended by Issue #1067.

The command is idempotent and safe to re-run. It defaults to a dry run;
pass ``--apply`` to persist changes.

Usage::

    python manage.py normalize_pdf_iframe_sandbox          # dry run
    python manage.py normalize_pdf_iframe_sandbox --apply  # apply changes
"""

import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cms.models import HomePageContent, Page

# Sandbox value required for Chrome's built-in PDF viewer (PDFium).
PDF_EMBED_SANDBOX = "allow-scripts allow-same-origin"

IFRAME_TAG_RE = re.compile(r"<iframe\b[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r"""src=["']([^"']*)["']""", re.IGNORECASE)
SANDBOX_RE = re.compile(r"""\s+sandbox=["'][^"']*["']""", re.IGNORECASE)
PDF_CONTAINER_OPEN = '<div class="pdf-container">'


def _is_trusted_pdf_url(url, trusted_prefixes):
    """Server-side mirror of the TinyMCE ``isTrustedPdfUrl`` check.

    A URL is trusted when its pathname equals a configured prefix path or
    starts with it (segment-safe). Matching is done on the path component
    only: stored content commonly uses relative URLs
    (e.g. ``/cms/document-pdf/42/``) while configured prefixes are full
    URLs (e.g. ``https://example.com/cms/document-pdf/``), so a strict
    origin comparison would mis-classify trusted embeds.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    for prefix in trusted_prefixes:
        try:
            parsed_prefix = urlparse(prefix)
        except ValueError:
            continue
        prefix_path = parsed_prefix.path
        if not prefix_path:
            continue
        if parsed.path == prefix_path or parsed.path.startswith(
            prefix_path if prefix_path.endswith("/") else prefix_path + "/"
        ):
            return True
    return False


def _is_direct_child_of_pdf_container(content, iframe_start):
    """Return True if the iframe starts right after a .pdf-container div.

    This mirrors the client-side ``closest('.pdf-container')`` check that
    only targets the PDF embed iframes (YouTube iframes are never inside a
    ``.pdf-container`` and are left untouched).
    """
    container_start = content.rfind(PDF_CONTAINER_OPEN, 0, iframe_start)
    if container_start == -1:
        return False
    return "</div>" not in content[container_start:iframe_start]


def normalize_pdf_iframe_sandbox(content, trusted_prefixes):
    """Return (new_content, rewritten_count) for a CMS content string."""
    rewritten = 0
    replacements = []  # (start, end, new_tag) collected in reverse order

    for match in IFRAME_TAG_RE.finditer(content):
        tag = match.group(0)
        if not _is_direct_child_of_pdf_container(content, match.start()):
            continue

        src_match = SRC_RE.search(tag)
        src = src_match.group(1) if src_match else ""

        has_sandbox = SANDBOX_RE.search(tag) is not None
        sandbox_value = None
        if has_sandbox:
            sandbox_match = re.search(
                r"""sandbox=["']([^"']*)["']""", tag, re.IGNORECASE
            )
            sandbox_value = sandbox_match.group(1) if sandbox_match else None

        if _is_trusted_pdf_url(src, trusted_prefixes):
            # Trusted embeds stay unsandboxed (Issue #1067 behavior).
            if has_sandbox:
                replacements.append(
                    (
                        match.start(),
                        match.end(),
                        SANDBOX_RE.sub("", tag),
                    )
                )
        else:
            if sandbox_value == PDF_EMBED_SANDBOX:
                continue  # already correct — idempotent
            if has_sandbox:
                new_tag = SANDBOX_RE.sub(f' sandbox="{PDF_EMBED_SANDBOX}"', tag)
            else:
                new_tag = tag[:-1] + f' sandbox="{PDF_EMBED_SANDBOX}">'
            replacements.append((match.start(), match.end(), new_tag))

    # Apply replacements in reverse so offsets stay valid.
    new_content = content
    for start, end, new_tag in sorted(replacements, key=lambda r: r[0], reverse=True):
        new_content = new_content[:start] + new_tag + new_content[end:]

    return new_content, len(replacements)


class Command(BaseCommand):
    help = (
        "Normalize the sandbox attribute on legacy .pdf-container iframes: "
        "untrusted embeds get 'allow-scripts allow-same-origin' so the "
        "browser PDF viewer works; trusted embeds stay unsandboxed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist rewrites. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        trusted_prefixes = list(settings.TINYMCE_PDF_TRUSTED_URL_PREFIXES)

        scanned = inspected = rewritten = 0

        for model, label in ((Page, "page"), (HomePageContent, "homepage")):
            rows = list(model.objects.only("id", "content"))
            for row in rows:
                scanned += 1
                content = row.content or ""
                if "pdf-container" not in content:
                    continue

                new_content, row_rewrites = normalize_pdf_iframe_sandbox(
                    content, trusted_prefixes
                )
                if not row_rewrites:
                    continue
                inspected += 1
                rewritten += row_rewrites
                if apply_changes:
                    now = timezone.now()
                    with transaction.atomic():
                        model.objects.filter(pk=row.pk).update(
                            content=new_content, updated_at=now
                        )
                self.stdout.write(
                    f"{label} id={row.id}: {row_rewrites} iframe(s) "
                    f"{'rewritten' if apply_changes else 'would be rewritten'}"
                )

        action = "rewritten" if apply_changes else "ready to rewrite"
        self.stdout.write(
            self.style.SUCCESS(
                f"PDF sandbox normalization {'complete' if apply_changes else 'dry run'}. "
                f"Objects scanned: {scanned}; iframes {action}: {rewritten}."
            )
        )
