from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from siteconfig.models import SiteConfiguration


def get_club_timezone_name():
    """Return configured club timezone name with explicit UTC fallback."""
    config = SiteConfiguration.objects.only("club_timezone").first()
    if config and config.club_timezone:
        return config.club_timezone
    return "UTC"


def get_club_tzinfo():
    """Return ZoneInfo for the configured club timezone."""
    return ZoneInfo(get_club_timezone_name())


def get_club_now():
    """Return timezone-aware current datetime in club-local timezone."""
    return timezone.now().astimezone(get_club_tzinfo())


def get_club_today():
    """Return club-local operational date for current time."""
    return get_club_now().date()


def as_club_local(value):
    """Convert aware datetime to club-local timezone for operational logic."""
    return value.astimezone(get_club_tzinfo())
