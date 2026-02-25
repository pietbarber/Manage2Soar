# Visiting pilot views moved to members app

import ipaddress
import logging
from urllib.parse import urlparse

import requests
from django.http import Http404, HttpResponse
from django.shortcuts import render

from members.decorators import active_member_required
from siteconfig.models import SiteConfiguration

logger = logging.getLogger(__name__)


def _get_webcam_url() -> str:
    """Fetch *only* webcam_snapshot_url from the DB without caching.

    Credentials in the URL are intentionally never written to the cache
    backend.  Returns an empty string when no SiteConfiguration row exists
    or the field is blank.
    """
    row = SiteConfiguration.objects.values_list(
        "webcam_snapshot_url", flat=True
    ).first()
    return row or ""


def _validate_webcam_url(url: str) -> bool:
    """Return True only for http/https URLs that do not point at internal networks.

    SSRF guard: blocks non-http/https schemes, empty hosts, ``localhost`` by
    name, IPv4/IPv6 loopback (127.0.0.0/8, ::1), private ranges
    (10/8, 172.16/12, 192.168/16), and link-local (169.254/16, fe80::/10).

    Hostname-based addresses that resolve to private IPs at DNS time are
    *not* blocked here (no live DNS lookup) because the configured URL is
    expected to be an admin-supplied camera endpoint, not arbitrary user
    input.  Direct IP literals and "localhost" are always blocked.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        # Block 'localhost' by name.
        if host == "localhost":
            return False
        # If the host is an IP literal, reject private/loopback/link-local ranges.
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_private or ip.is_link_local:
                return False
        except ValueError:
            pass  # not an IP literal — hostname accepted as-is
        return True
    except Exception:
        return False


# Allowed image MIME types forwarded to the browser.  Any other Content-Type
# returned by the camera is coerced to image/jpeg rather than forwarded
# verbatim, preventing a content-sniffing attack via an unusual type string.
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
}

# Maximum response body size accepted from the camera (10 MB).  Cameras that
# return larger payloads are rejected with 503 to prevent memory exhaustion.
_MAX_WEBCAM_BYTES = 10 * 1024 * 1024


@active_member_required
def webcam_page(request):
    """Member-only webcam viewer page (Issue #625)."""
    if not _get_webcam_url():
        raise Http404("Webcam not configured")
    return render(request, "siteconfig/webcam.html")


@active_member_required
def webcam_snapshot(request):
    """
    Server-side proxy that fetches a JPEG snapshot from the configured webcam
    URL and returns the raw image bytes to the browser (Issue #625).

    This solves the mixed-content problem: the camera endpoint may be plain
    HTTP, but the browser only ever talks HTTPS to Django.  The camera
    credentials in ``webcam_snapshot_url`` are fetched fresh from the DB on
    every request and are never written to the cache backend.

    The server only contacts the camera when a browser requests this URL, so
    there is zero background polling when no one is on the webcam page.
    """
    url = _get_webcam_url()
    if not url:
        raise Http404("Webcam not configured")

    if not _validate_webcam_url(url):
        logger.error("Webcam URL has an invalid/unsafe scheme; request blocked.")
        resp = HttpResponse(status=503)
        resp["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

    try:
        # Timeout of 8 s balances responsiveness against slow cameras.
        # stream=False (the default) loads the full JPEG into memory before
        # forwarding — appropriate for webcam snapshots (typically < 1 MB).
        # allow_redirects=False prevents a redirect chain from bypassing the
        # scheme/host validation above (redirect-based SSRF).
        resp = requests.get(url, timeout=8, allow_redirects=False)
        # raise_for_status() only raises for 4xx/5xx; 3xx responses are
        # silently passed through without it.  Treat any redirect as an error
        # so a compromised camera cannot redirect us to an internal endpoint.
        if 300 <= resp.status_code < 400:
            logger.warning(
                "Webcam returned redirect (status=%s), which is blocked for security",
                resp.status_code,
            )
            err = HttpResponse(status=503)
            err["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return err
        resp.raise_for_status()
        # Reject oversized responses before reading the body into memory.
        # Cameras should never return multi-megabyte snapshots, but a
        # misconfigured or malicious endpoint could exhaust Django worker RAM.
        content_length = resp.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > _MAX_WEBCAM_BYTES:
                    logger.warning(
                        "Webcam response too large (%s bytes), rejecting",
                        content_length,
                    )
                    err = HttpResponse(status=503)
                    err["Cache-Control"] = "no-store, no-cache, must-revalidate"
                    return err
            except ValueError:
                pass  # malformed Content-Length — proceed and let the read fail
    except requests.RequestException as exc:
        # Log only the exception class and HTTP status to avoid leaking the
        # camera URL (which may contain embedded credentials) into logs/Sentry.
        status_code = getattr(getattr(exc, "response", None), "status_code", "unknown")
        logger.warning(
            "Webcam snapshot fetch failed (%s, status=%s)",
            exc.__class__.__name__,
            status_code,
        )
        # Return a 503 so the browser <img onerror> handler fires.
        err = HttpResponse(status=503)
        err["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return err

    content_type = (
        resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip().lower()
    )
    if content_type not in _ALLOWED_IMAGE_TYPES:
        content_type = "image/jpeg"

    response = HttpResponse(resp.content, content_type=content_type)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["X-Robots-Tag"] = "noindex"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    return response
