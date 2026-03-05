"""
URL Helper Functions for Canonical URL Management

This module provides centralized functions for building absolute URLs
used in outbound email notifications. All email links should use the
canonical URL from SiteConfiguration to ensure consistency regardless
of which domain users access.

See GitHub Issue #612 for background.
"""

from urllib.parse import urlparse

from django.conf import settings


def _normalize_origin(url_or_domain: str) -> str:
    """Normalize a URL/domain to scheme://host[:port] origin form."""
    raw = (url_or_domain or "").strip()
    if not raw:
        return ""

    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
    else:
        # Treat bare hostnames/domains (and optional ports) as HTTPS.
        parsed = urlparse(f"https://{raw}")

    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"

    return ""


def get_canonical_url(config=None):
    """
    Get the canonical URL for email links.

     Priority:
     1. SiteConfiguration.canonical_url (database - webmaster configurable)
     2. settings.SITE_URL (environment variable - backward compatibility)
     3. If SITE_URL resolves to localhost/127.0.0.1 and SiteConfiguration
         has domain_name set, use that domain for outbound links
     4. 'http://localhost:8001' (development fallback)

    Returns:
        str: Canonical URL without trailing slash

    Examples:
        >>> get_canonical_url()
        'https://www.skylinesoaring.org'
    """
    try:
        from django.db.utils import OperationalError, ProgrammingError

        from siteconfig.models import SiteConfiguration

        if config is None:
            config = SiteConfiguration.objects.first()

        if config:
            canonical_url = (getattr(config, "canonical_url", "") or "").strip()
            if canonical_url:
                normalized = _normalize_origin(canonical_url)
                if normalized:
                    return normalized.rstrip("/")
    except (OperationalError, ProgrammingError):
        # Database not ready (migrations, tests, initial setup)
        pass

    # Fallback to environment variable
    site_url = getattr(settings, "SITE_URL", "").strip()
    normalized_site_url = ""
    if site_url:
        normalized_site_url = _normalize_origin(site_url) or site_url.rstrip("/")
        parsed_site_url = urlparse(normalized_site_url)
        hostname = (parsed_site_url.hostname or "").lower()

        # Respect SITE_URL unless it is a local development address.
        if hostname not in {"localhost", "127.0.0.1"}:
            return normalized_site_url.rstrip("/")

        # SITE_URL points to localhost. If config has a real domain, prefer it
        # for outbound links; otherwise keep the explicit SITE_URL value.
        if config:
            domain_name = (getattr(config, "domain_name", "") or "").strip()
            if domain_name:
                normalized = _normalize_origin(domain_name)
                if normalized:
                    return normalized.rstrip("/")

        return normalized_site_url.rstrip("/")

    # Development fallback
    return "http://localhost:8001"


def build_absolute_url(path, canonical=None):
    """
    Build absolute URL for email links using canonical URL.

    Args:
        path: URL path (e.g., '/members/applications/123/' or 'members/applications/123/')
              Can include leading slash or not - will be normalized.
        canonical: Optional precomputed canonical URL to avoid repeated DB queries.
                   If not provided, will call get_canonical_url().

    Returns:
        str: Full absolute URL

    Examples:
        >>> build_absolute_url('/members/applications/123/')
        'https://www.skylinesoaring.org/members/applications/123/'

        >>> build_absolute_url('duty_roster/calendar/')
        'https://www.skylinesoaring.org/duty_roster/calendar/'

        >>> # Performance: reuse canonical URL for multiple calls
        >>> base = get_canonical_url()
        >>> url1 = build_absolute_url('/path1/', canonical=base)
        >>> url2 = build_absolute_url('/path2/', canonical=base)
    """
    if canonical is None:
        canonical = get_canonical_url()
    # Normalize canonical URL by removing trailing slash to avoid double slashes
    canonical = canonical.rstrip("/")
    path = path.lstrip("/")
    return f"{canonical}/{path}"
