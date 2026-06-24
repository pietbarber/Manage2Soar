from datetime import datetime
from datetime import timezone as dt_timezone

import pytest
from django.test import override_settings
from django.utils import timezone

from siteconfig.models import SiteConfiguration
from siteconfig.timezone_utils import (
    as_club_local,
    get_club_timezone_name,
    get_club_today,
    get_club_tzinfo,
)


@pytest.mark.django_db
@override_settings(TIME_ZONE="UTC")
def test_get_club_timezone_name_uses_configured_value():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        club_timezone="America/Los_Angeles",
    )

    assert get_club_timezone_name() == "America/Los_Angeles"


@pytest.mark.django_db
@override_settings(TIME_ZONE="America/New_York")
def test_get_club_timezone_name_falls_back_to_utc():
    assert get_club_timezone_name() == "UTC"


@pytest.mark.django_db
def test_get_club_tzinfo_returns_zoneinfo():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        club_timezone="America/Denver",
    )

    assert str(get_club_tzinfo()) == "America/Denver"


@pytest.mark.django_db
@override_settings(TIME_ZONE="UTC")
def test_get_club_today_uses_club_local_date(monkeypatch):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        club_timezone="America/Los_Angeles",
    )

    frozen_utc = timezone.make_aware(
        datetime(2026, 1, 2, 1, 30, 0),
        dt_timezone.utc,
    )
    monkeypatch.setattr(timezone, "now", lambda: frozen_utc)

    assert str(get_club_today()) == "2026-01-01"


@pytest.mark.django_db
def test_as_club_local_converts_aware_datetime():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        club_timezone="America/New_York",
    )

    utc_dt = timezone.make_aware(datetime(2026, 6, 1, 12, 0, 0), dt_timezone.utc)
    local_dt = as_club_local(utc_dt)

    assert local_dt.tzinfo is not None
    assert local_dt.hour == 8
