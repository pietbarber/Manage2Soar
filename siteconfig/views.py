# Visiting pilot views moved to members app

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
    """Return True only for http/https URLs with a non-empty host.

    Basic SSRF guard: prevents accidental ``file://`` or other unexpected
    schemes from reaching ``requests.get``.  The URL is admin-configured so
    full IP-range blocking is omitted as an acceptable trade-off.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


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
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Webcam snapshot fetch failed: %s", exc)
        # Return a 503 so the browser <img onerror> handler fires.
        err = HttpResponse(status=503)
        err["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return err

    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"

    response = HttpResponse(resp.content, content_type=content_type)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["X-Robots-Tag"] = "noindex"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    return response
