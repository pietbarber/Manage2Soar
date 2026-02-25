from django import template
from django.core.cache import cache

from siteconfig.models import SiteConfiguration

register = template.Library()

_MISS = object()


@register.simple_tag
def get_siteconfig():
    """Return the SiteConfiguration instance, cached for 60 s.

    Uses its own ``siteconfig_deferred`` cache key (distinct from the
    ``siteconfig_instance`` key used by duty_roster and other callers that
    cache the full non-deferred object).  ``webcam_snapshot_url`` is deferred
    so camera credentials are never serialised into the cache backend.  Any
    template access to that field will trigger a single lazy DB load; use the
    ``webcam_enabled`` tag for the simple boolean nav-visibility check to
    avoid that extra query.
    """
    cfg = cache.get("siteconfig_deferred", _MISS)
    if cfg is _MISS:
        cfg = SiteConfiguration.objects.defer("webcam_snapshot_url").first()
        cache.set("siteconfig_deferred", cfg, timeout=60)
    return cfg


@register.simple_tag
def webcam_enabled():
    """Return True when a webcam snapshot URL is configured (cached boolean, 60 s).

    Stored under a separate ``siteconfig_webcam_enabled`` cache key so the
    credential-bearing URL is never written to the cache backend.  Use this
    tag in nav conditions rather than accessing
    ``siteconfig.webcam_snapshot_url`` directly.
    """
    result = cache.get("siteconfig_webcam_enabled", _MISS)
    if result is _MISS:
        url = SiteConfiguration.objects.values_list(
            "webcam_snapshot_url", flat=True
        ).first()
        result = bool(url)
        cache.set("siteconfig_webcam_enabled", result, timeout=60)
    return result
