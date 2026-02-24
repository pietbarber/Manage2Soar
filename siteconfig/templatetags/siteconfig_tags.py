from django import template
from django.core.cache import cache

from siteconfig.models import SiteConfiguration

register = template.Library()

_MISS = object()


@register.simple_tag
def get_siteconfig():
    """Return the SiteConfiguration instance, cached for 60 s.

    Uses the shared ``siteconfig_instance`` cache key so that view requests
    and template-tag lookups benefit from each other's cache warm-ups,
    eliminating per-page DB hits for navbar rendering.
    """
    cfg = cache.get("siteconfig_instance", _MISS)
    if cfg is _MISS:
        cfg = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", cfg, timeout=60)
    return cfg
