"""
URL Helper Functions for Canonical URL Management

This module provides centralized functions for building absolute URLs
used in outbound email notifications. All email links should use the
canonical URL from SiteConfiguration to ensure consistency regardless
of which domain users access.

See GitHub Issue #612 for background.
"""

import ipaddress
from urllib.parse import urlparse

from django.conf import settings


def _normalize_origin(url_or_domain: str | None) -> str:
    """Normalize a URL/domain to scheme://host[:port] origin form."""
    raw = (url_or_domain or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if not (parsed.scheme and parsed.netloc):
        # Treat bare hostnames/domains (and optional ports) as HTTPS.
        parsed = urlparse(f"https://{raw}")

    if parsed.scheme and (parsed.hostname or parsed.netloc):
        # Reconstruct host[:port] to avoid leaking username/password from netloc.
        host = parsed.hostname or parsed.netloc
        if ":" in host and not host.startswith("["):
            # Preserve valid IPv6 origin formatting when rebuilding netloc.
            host = f"[{host}]"
        try:
            port = parsed.port
        except ValueError:
            # Invalid ports (e.g., :abc) should not crash URL resolution.
            port = None
        if port:
            host = f"{host}:{port}"
        return f"{parsed.scheme}://{host}"

    return ""


def _is_loopback_host(hostname: str) -> bool:
    """Return True for localhost and IP loopback addresses."""
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def get_canonical_url(config=None):
    """
    Get the canonical URL for email links.

    Priority:
    1. SiteConfiguration.canonical_url when it resolves to a non-loopback host
    2. settings.SITE_URL
    3. If SITE_URL resolves to a loopback host and SiteConfiguration has
       domain_name set, use that domain for outbound links
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
                    canonical_host = (urlparse(normalized).hostname or "").lower()
                    if not _is_loopback_host(canonical_host):
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
        if not _is_loopback_host(hostname):
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
