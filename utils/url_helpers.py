"""
URL Helper Functions for Canonical URL Management

This module provides centralized functions for building absolute URLs
used in outbound email notifications. All email links should use the
canonical URL from SiteConfiguration to ensure consistency regardless
of which domain users access.

See GitHub Issue #612 for background.
"""

from django.conf import settings


def get_canonical_url():
    """
    Get the canonical URL for email links.

    Priority:
    1. SiteConfiguration.canonical_url (database - webmaster configurable)
    2. settings.SITE_URL (environment variable - backward compatibility)
    3. 'http://localhost:8001' (development fallback)

    Returns:
        str: Canonical URL without trailing slash

    Examples:
        >>> get_canonical_url()
        'https://www.skylinesoaring.org'
    """
    try:
        from siteconfig.models import SiteConfiguration

        config = SiteConfiguration.objects.first()
        if config and config.canonical_url:
            return config.canonical_url.rstrip("/")
    except Exception:
        # Database not ready (migrations, tests, initial setup)
        pass

    # Fallback to environment variable
    site_url = getattr(settings, "SITE_URL", "").strip()
    if site_url:
        return site_url.rstrip("/")

    # Development fallback
    return "http://localhost:8001"


def build_absolute_url(path):
    """
    Build absolute URL for email links using canonical URL.

    Args:
        path: URL path (e.g., '/members/applications/123/' or 'members/applications/123/')
              Can include leading slash or not - will be normalized.

    Returns:
        str: Full absolute URL

    Examples:
        >>> build_absolute_url('/members/applications/123/')
        'https://www.skylinesoaring.org/members/applications/123/'

        >>> build_absolute_url('duty_roster/calendar/')
        'https://www.skylinesoaring.org/duty_roster/calendar/'
    """
    canonical = get_canonical_url()
    path = path.lstrip("/")
    return f"{canonical}/{path}"
