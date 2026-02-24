# Visiting pilot views moved to members app

import logging

import requests
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import render

from members.decorators import active_member_required
from siteconfig.models import SiteConfiguration

logger = logging.getLogger(__name__)

_SITECONFIG_CACHE_MISS = object()


def _get_cached_siteconfig():
    """Return the SiteConfiguration instance, using the shared 60-second cache."""
    cfg = cache.get("siteconfig_instance", _SITECONFIG_CACHE_MISS)
    if cfg is _SITECONFIG_CACHE_MISS:
        cfg = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", cfg, timeout=60)
    return cfg


@active_member_required
def webcam_page(request):
    """Member-only webcam viewer page (Issue #625)."""
    cfg = _get_cached_siteconfig()
    if not cfg or not cfg.webcam_snapshot_url:
        raise Http404("Webcam not configured")
    return render(request, "siteconfig/webcam.html", {"siteconfig": cfg})


@active_member_required
def webcam_snapshot(request):
    """
    Server-side proxy that fetches a JPEG snapshot from the configured webcam URL
    and streams the raw image bytes back to the browser (Issue #625).

    This solves the mixed-content problem: the camera endpoint may be plain HTTP,
    but the browser only ever talks HTTPS to Django.  The camera credentials in
    ``webcam_snapshot_url`` are never sent to the client.

    The server only fetches from the camera when a browser requests this URL, so
    there is zero background polling when no one is on the webcam page.
    """
    cfg = _get_cached_siteconfig()
    if not cfg or not cfg.webcam_snapshot_url:
        raise Http404("Webcam not configured")

    try:
        resp = requests.get(cfg.webcam_snapshot_url, timeout=8, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Webcam snapshot fetch failed: %s", exc)
        # Return a 503 so the browser <img onerror> handler fires
        return HttpResponse(status=503)

    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"

    response = HttpResponse(resp.content, content_type=content_type)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["X-Robots-Tag"] = "noindex"
    return response
