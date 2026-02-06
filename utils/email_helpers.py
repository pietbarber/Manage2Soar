"""
Utility functions for email generation.
"""

from .url_helpers import get_canonical_url


def get_absolute_club_logo_url(config):
    """
    Build an absolute club logo URL for email templates.

    Email clients require absolute URLs for images to display properly.
    This helper converts relative logo URLs (e.g., /media/logo.png) to
    absolute URLs (e.g., https://site.com/media/logo.png).

    Args:
        config: SiteConfiguration instance or None

    Returns:
        Absolute URL string if logo exists, None otherwise
    """
    if not config or not config.club_logo:
        return None

    logo_url = config.club_logo.url

    # If already absolute, return as-is
    if logo_url.startswith(("http://", "https://")):
        return logo_url

    # Convert relative URL to absolute using canonical URL
    site_url = get_canonical_url()
    return f"{site_url.rstrip('/')}{logo_url}"
