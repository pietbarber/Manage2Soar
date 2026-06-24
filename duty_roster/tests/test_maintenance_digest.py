from datetime import date, datetime
from datetime import timezone as dt_timezone

import pytest
from django.core.management import call_command

from logsheet.models import AircraftMeister, Glider, MaintenanceIssue
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_send_maintenance_digest_uses_club_local_today_for_subject(monkeypatch):
    site_config = SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_nickname="Test Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
        club_timezone="America/Los_Angeles",
    )

    meister = Member.objects.create(
        username="meister_one",
        first_name="Mia",
        last_name="Meister",
        email="meister@example.com",
        membership_status="Full Member",
    )
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N123TZ",
        rental_rate=0,
        club_owned=True,
        is_active=True,
    )
    AircraftMeister.objects.create(glider=glider, member=meister)
    MaintenanceIssue.objects.create(
        glider=glider,
        description="Canopy latch adjustment",
        report_date=date(2026, 5, 28),
        grounded=False,
        resolved=False,
    )

    # 03:10 UTC on May 30 is still May 29 in America/Los_Angeles.
    frozen_utc = datetime(2026, 5, 30, 3, 10, 0, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("siteconfig.timezone_utils.timezone.now", lambda: frozen_utc)

    captured = {}

    def _mock_send_mail(**kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(
        "duty_roster.management.commands.send_maintenance_digest.send_mail",
        _mock_send_mail,
    )

    call_command("send_maintenance_digest", verbosity=0)

    assert captured["recipient_list"] == ["meister@example.com"]
    assert captured["subject"] == "[Test Soaring Club] Maintenance Summary - May 29"
    assert site_config.club_timezone == "America/Los_Angeles"
