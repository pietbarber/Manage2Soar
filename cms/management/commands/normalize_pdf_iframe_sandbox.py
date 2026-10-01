"""Normalize legacy PDF embed iframes to use the pdf.js viewer (Issue #1069).

Chrome's built-in PDF viewer refuses to activate inside ANY sandboxed
iframe, regardless of which sandbox tokens are granted, so a plain
``<iframe src="the.pdf" sandbox="...">`` embed can never reliably render
inline in Chrome. Issue #1067's ``sandbox=""`` and Issue #1069's earlier
``sandbox="allow-scripts allow-same-origin"`` both hit this wall.

This command rewrites stored CMS content so that every ``.pdf-container``
iframe instead points at the self-hosted pdf.js viewer
(``settings.PDF_VIEWER_URL``), passing the original PDF URL as a `file`
query parameter. The viewer is same-origin, trusted code, so the iframe can
stay genuinely sandboxed for every embed:

* trusted (``TINYMCE_PDF_TRUSTED_URL_PREFIXES``, e.g. our own
  ``/cms/document-pdf/`` endpoint) and genuinely cross-origin URLs are both
  wrapped in the viewer and sandboxed with
  ``allow-scripts allow-same-origin allow-downloads allow-modals``;
* a same-origin URL that is NOT the trusted endpoint (or anything else
  invalid) is never embedded at all — its ``src`` is stripped and its
  sandbox is fully locked down, since an unsandboxed same-origin fetch
  would otherwise run with the visitor's full session privileges.

The command is idempotent and safe to re-run. It defaults to a dry run;
pass ``--apply`` to persist changes.

Usage::

    python manage.py normalize_pdf_iframe_sandbox          # dry run
    python manage.py normalize_pdf_iframe_sandbox --apply  # apply changes
"""

import html
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cms.models import HomePageContent, Page
from cms.pdf_proxy import sign_external_pdf_url

# Sandbox value used for every pdf.js-viewer-wrapped PDF embed. Safe because
# the sandboxed document is our own viewer code, not the linked PDF itself.
PDF_VIEWER_SANDBOX = "allow-scripts allow-same-origin allow-downloads allow-modals"

IFRAME_TAG_RE = re.compile(r"<iframe\b(?:[^\"'>]|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE)
# Enforce true attribute boundaries so the regex does not match the substring
# "src" inside a different attribute name (e.g. data-src, x-src).
ATTR_SRC_RE = re.compile(r"(?<![0-9A-Za-z_-])src=[\"']([^\"']*)[\"']", re.IGNORECASE)
ATTR_SANDBOX_RE = re.compile(r"\s+sandbox=(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
PDF_CONTAINER_OPEN = '<div class="pdf-container">'


def _url_origin(parsed):
    """Return the origin (scheme://netloc) of a parsed URL."""
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_path(path):
    """Resolve dot segments the way a browser's WHATWG URL parser does.

    ``urllib.parse.urlparse`` leaves dot segments and percent-encodings
    intact, so e.g. ``/cms/document-pdf/../admin/`` or
    ``/cms/document-pdf/%2e%2e/admin/`` would otherwise appear to sit under
    the ``/cms/document-pdf/`` prefix even though the browser actually
    loads ``/cms/admin/``.

    For special-scheme URLs (http/https) the WHATWG parser resolves each
    path segment whose *decoded* value is ``.`` or ``..`` as
    navigation, but leaves every other segment in its original
    (percent-encoded) form. That means:

    * ``%2e%2e`` / ``%2E%2E`` decode to ``..`` and move one level up;
    * a *literal* ``\\`` is a path separator, so it is split on;
    * encoded separators and ordinary characters stay literal — ``%2F``,
      ``%5C``, ``%20`` are NOT decoded, so e.g. ``cms%2Fdocument-pdf``
      does not collapse to ``cms/document-pdf`` and repeated slashes are
      not collapsed;
    * a single encoded 4-dot segment (``%2e%2e%2e%2e``) decodes to the
      literal name ``....`` (no dot *boundary*), so it is a filename, not
      two levels of ``..``.

    This mirrors what the browser actually loads, so the trust decision
    matches the client-side ``isTrustedPdfUrl`` check.
    """
    if not path or path == "/":
        return path
    had_trailing_slash = path.endswith("/")
    # WHATWG special-scheme parser treats a literal backslash as "/".
    segments = path.replace("\\", "/").split("/")
    resolved: list[str] = []
    for segment in segments:
        if segment == "":
            resolved.append(segment)
        elif unquote(segment) == ".":
            # Current-directory marker: dropped, matching the browser.
            continue
        elif unquote(segment) == "..":
            if resolved and resolved[-1] != "":
                resolved.pop()
            # A leading ".." (or one with nothing to pop) is a no-op.
        else:
            resolved.append(segment)
    if not resolved:
        resolved = [""]
    elif had_trailing_slash and resolved[-1] != "":
        resolved.append("")
    normalized = "/".join(resolved)
    if not normalized:
        normalized = "/"
    return normalized


def _is_trusted_pdf_url(url, trusted_prefixes):
    """Server-side mirror of the TinyMCE ``isTrustedPdfUrl`` check.

    A URL is trusted when it is a segment-safe path-prefix match under a
    configured prefix. Mirroring the client-side check:

    * absolute stored URLs must additionally match the configured prefix
      origin, so e.g. ``https://attacker.example/cms/document-pdf/42/``
      never matches a ``https://example.com/cms/document-pdf/`` prefix;
    * relative stored URLs (``/cms/document-pdf/42/``) are resolved against
      the page origin by the browser, so only the path is compared here;
    * non-HTTP schemes (``file://``, ``data:``, etc.) and protocol-relative
      URLs (``//host/path``) are always untrusted — they cannot resolve to
      a same-origin web PDF.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    # Non-HTTP/HTTPS schemes (file://, data:, javascript:, etc.) are never
    # trusted — they cannot resolve to a same-origin web PDF.
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False

    # Protocol-relative URLs (//host/path) always carry a host but no
    # scheme; they are cross-origin by nature and must not be trusted.
    if not parsed.scheme and parsed.netloc:
        return False

    is_absolute = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    url_path = _normalize_path(parsed.path)
    for prefix in trusted_prefixes:
        try:
            parsed_prefix = urlparse(prefix)
        except ValueError:
            continue
        if parsed_prefix.scheme not in ("http", "https") or not parsed_prefix.netloc:
            continue
        if is_absolute and _url_origin(parsed) != _url_origin(parsed_prefix):
            continue
        prefix_path = _normalize_path(parsed_prefix.path)
        if not prefix_path:
            continue
        if url_path == prefix_path or url_path.startswith(
            prefix_path if prefix_path.endswith("/") else prefix_path + "/"
        ):
            return True
    return False


def _extract_wrapped_target(src, wrapper_url, param_name):
    """If `src` already points at `wrapper_url`, return its `param_name`
    query value; otherwise None. Shared by the pdf.js-viewer and external-
    proxy unwrap steps to keep re-normalization idempotent.
    """
    if not src or not wrapper_url:
        return None
    try:
        parsed = urlparse(src)
        parsed_wrapper = urlparse(wrapper_url)
    except ValueError:
        return None
    is_legacy_viewer = parsed.path.endswith("/static/pdfjs-viewer/viewer.html")
    if not is_legacy_viewer and parsed.path != parsed_wrapper.path:
        return None
    if (
        parsed_wrapper.netloc
        and parsed.netloc
        and parsed_wrapper.netloc != parsed.netloc
    ):
        return None
    values = parse_qs(parsed.query).get(param_name)
    return values[0] if values else None


def _resolve_original_url(src, viewer_url, proxy_url):
    """Recover the original PDF URL from a (possibly viewer- and/or
    proxy-wrapped) iframe src, for idempotent re-normalization.
    """
    viewer_target = _extract_wrapped_target(src, viewer_url, "file") or src
    return _extract_wrapped_target(viewer_target, proxy_url, "url") or viewer_target


def _resolve_embed_target(url, classification, proxy_url, proxy_hosts):
    """Given the *original* PDF URL and its classification, return the value
    that should be passed to the viewer as `file`: cross-origin URLs route
    through the external proxy when one is configured (Issue #1069 Phase 3),
    everything else embeds directly.
    """
    parsed = urlparse(url)
    if (
        classification == "cross-origin"
        and proxy_url
        and parsed.hostname
        and parsed.hostname.lower() in proxy_hosts
    ):
        signature = sign_external_pdf_url(url)
        return f"{proxy_url}?url={quote(url, safe='')}&signature={quote(signature, safe='')}"
    return url


def _classify_pdf_url(url, trusted_prefixes):
    """Classify a candidate PDF URL, mirroring the client-side check in
    ``static/js/tinymce-youtube-fix.js``'s ``classifyPdfUrl``.

    Returns one of ``"trusted"``, ``"cross-origin"``,
    ``"same-origin-blocked"``, or ``"invalid"``. Unlike the browser, this
    command has no single "current origin" to compare against, so an
    absolute URL is treated as same-origin only when its origin matches one
    of the configured trusted-prefix origins (i.e. a known deployment
    domain). The authoritative, always-correct check still happens
    client-side at save time; this is a best-effort mirror for migrating
    stored content.
    """
    if not url:
        return "invalid"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid"
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return "invalid"
    if not parsed.scheme and parsed.netloc:
        return "invalid"  # protocol-relative URLs are never trusted/safe
    if _is_trusted_pdf_url(url, trusted_prefixes):
        return "trusted"

    is_absolute = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    if not is_absolute:
        # Relative URL: resolves to our own origin but isn't the trusted path.
        return "same-origin-blocked"

    known_origins = set()
    for prefix in trusted_prefixes:
        try:
            parsed_prefix = urlparse(prefix)
        except ValueError:
            continue
        if parsed_prefix.scheme in ("http", "https") and parsed_prefix.netloc:
            known_origins.add(_url_origin(parsed_prefix))
    if _url_origin(parsed) in known_origins:
        return "same-origin-blocked"
    return "cross-origin"


def _set_sandbox(tag, value):
    """Return `tag` with its sandbox attribute set to `value` (added if absent)."""
    if ATTR_SANDBOX_RE.search(tag):
        return ATTR_SANDBOX_RE.sub(f' sandbox="{value}"', tag, count=1)
    if tag.endswith("/>"):
        return tag[:-2] + f' sandbox="{value}"/>'
    return tag[:-1] + f' sandbox="{value}">'


def _remove_src(tag):
    """Return `tag` with its src attribute removed entirely."""
    return ATTR_SRC_RE.sub("", tag, count=1)


def _set_src(tag, value):
    """Return `tag` with its src attribute set to `value` (added if absent)."""
    escaped = value.replace('"', "&quot;")
    if ATTR_SRC_RE.search(tag):
        return ATTR_SRC_RE.sub(f'src="{escaped}"', tag, count=1)
    if tag.endswith("/>"):
        return tag[:-2] + f' src="{escaped}"/>'
    return tag[:-1] + f' src="{escaped}">'


def _is_inside_pdf_container(content, iframe_start):
    """Return True if the iframe is inside a .pdf-container div (any depth).

    This mirrors the client-side ``closest('.pdf-container')`` check that
    matches any ancestor with that class, not just a direct child.
    YouTube iframes are never inside a ``.pdf-container`` and are left
    untouched.
    """
    container_start = content.rfind(PDF_CONTAINER_OPEN, 0, iframe_start)
    if container_start == -1:
        return False
    # Walk the div open/close tags between the container and the iframe,
    # tracking nesting depth. The container's own <div> opens depth to 1;
    # if we return to 0 (the container closed) before reaching the iframe,
    # the iframe is a sibling, not a descendant.
    segment = content[container_start:iframe_start]
    depth = 0
    for tag_match in re.finditer(r"<div\b|</div\s*>", segment, re.IGNORECASE):
        if tag_match.group(0).startswith("</"):
            depth -= 1
            if depth <= 0:
                return False
        else:
            depth += 1
    return depth > 0


def normalize_pdf_iframe_sandbox(content, trusted_prefixes, viewer_url, proxy_url=""):
    """Return (new_content, rewritten_count) for a CMS content string."""
    replacements = []  # (start, end, new_tag) collected in reverse order

    for match in IFRAME_TAG_RE.finditer(content):
        tag = match.group(0)
        if not _is_inside_pdf_container(content, match.start()):
            continue

        src_match = ATTR_SRC_RE.search(tag)
        src = html.unescape(src_match.group(1)) if src_match else ""
        original_url = _resolve_original_url(src, viewer_url, proxy_url)
        classification = _classify_pdf_url(original_url, trusted_prefixes)

        sandbox_match = ATTR_SANDBOX_RE.search(tag)
        sandbox_value = sandbox_match.group(1)[1:-1] if sandbox_match else None

        if classification in ("invalid", "same-origin-blocked"):
            if not src and sandbox_value == "":
                continue  # already fully blocked — idempotent
            new_tag = _set_sandbox(_remove_src(tag), "")
            replacements.append((match.start(), match.end(), new_tag))
            continue

        embed_target = _resolve_embed_target(
            original_url,
            classification,
            proxy_url,
            settings.CMS_EXTERNAL_PDF_PROXY_ALLOWED_HOSTS,
        )
        new_src = f"{viewer_url}?file={quote(embed_target, safe='')}"
        if src == new_src and sandbox_value == PDF_VIEWER_SANDBOX:
            continue  # already correct — idempotent

        new_tag = _set_sandbox(_set_src(tag, new_src), PDF_VIEWER_SANDBOX)
        replacements.append((match.start(), match.end(), new_tag))

    # Apply replacements in reverse so offsets stay valid.
    new_content = content
    for start, end, new_tag in sorted(replacements, key=lambda r: r[0], reverse=True):
        new_content = new_content[:start] + new_tag + new_content[end:]

    return new_content, len(replacements)


class Command(BaseCommand):
    help = (
        "Normalize legacy .pdf-container iframes to route through the "
        "self-hosted pdf.js viewer with a fixed sandbox, instead of relying "
        "on Chrome's native (sandbox-incompatible) PDF viewer."
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
        viewer_url = settings.PDF_VIEWER_URL
        proxy_url = settings.CMS_EXTERNAL_PDF_PROXY_URL

        scanned = inspected = rewritten = skipped_conflicts = 0

        for model, label in ((Page, "page"), (HomePageContent, "homepage")):
            rows = list(model.objects.only("id", "content"))
            for row in rows:
                scanned += 1
                content = row.content or ""
                if "pdf-container" not in content:
                    continue

                new_content, row_rewrites = normalize_pdf_iframe_sandbox(
                    content, trusted_prefixes, viewer_url, proxy_url
                )
                if not row_rewrites:
                    continue
                inspected += 1

                # In apply mode the authoritative rewrite count is the one
                # computed on the locked, fresh content — a concurrent edit may
                # have changed the row since our initial read, and the stale
                # pre-lock count would otherwise mis-report the summary.
                reported_rewrites = row_rewrites

                if apply_changes:
                    # Re-read and lock the row inside the atomic block, then
                    # normalize the fresh content. This ensures a concurrent
                    # editor save is not clobbered by this stale snapshot.
                    with transaction.atomic():
                        locked_row = (
                            model.objects.select_for_update()
                            .filter(pk=row.pk)
                            .only("id", "content")
                            .get()
                        )
                        fresh_content = locked_row.content or ""
                        locked_new, locked_rewrites = normalize_pdf_iframe_sandbox(
                            fresh_content, trusted_prefixes, viewer_url, proxy_url
                        )
                        if not locked_rewrites:
                            skipped_conflicts += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f"{label} id={row.id}: skipped, content "
                                    f"changed after this run started "
                                    f"(concurrent edit). Re-run to normalize it."
                                )
                            )
                            continue
                        model.objects.filter(pk=row.pk).update(
                            content=locked_new, updated_at=timezone.now()
                        )
                    reported_rewrites = locked_rewrites

                rewritten += reported_rewrites
                self.stdout.write(
                    f"{label} id={row.id}: {reported_rewrites} iframe(s) "
                    f"{'rewritten' if apply_changes else 'would be rewritten'}"
                )

        action = "rewritten" if apply_changes else "ready to rewrite"
        self.stdout.write(
            self.style.SUCCESS(
                f"PDF sandbox normalization {'complete' if apply_changes else 'dry run'}. "
                f"Objects scanned: {scanned}; iframes {action}: {rewritten}; "
                f"conflicts skipped: {skipped_conflicts}."
            )
        )
