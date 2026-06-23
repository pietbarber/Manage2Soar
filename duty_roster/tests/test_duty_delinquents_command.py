from datetime import date, datetime, time
from datetime import timezone as dt_timezone

import pytest
from django.core.management import call_command

from logsheet.models import Airfield, Flight, Logsheet
from members.models import Member
from notifications.models import Notification
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_report_duty_delinquents_uses_club_local_date_cutoff(monkeypatch):
    SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_nickname="Test Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
        club_timezone="America/Los_Angeles",
    )

    member_manager = Member.objects.create(
        username="mm_one",
        first_name="Mila",
        last_name="Manager",
        email="manager@example.com",
        membership_status="Full Member",
        member_manager=True,
        joined_club=date(2020, 1, 1),
    )

    delinquent_member = Member.objects.create(
        username="active_flyer",
        first_name="Alex",
        last_name="Flyer",
        email="alex@example.com",
        membership_status="Full Member",
        joined_club=date(2025, 1, 1),
    )

    airfield = Airfield.objects.create(identifier="KTZ1", name="Timezone Field")
    logsheet = Logsheet.objects.create(
        log_date=date(2025, 12, 2),
        airfield=airfield,
        created_by=member_manager,
        finalized=True,
    )
    Flight.objects.create(
        logsheet=logsheet,
        pilot=delinquent_member,
        flight_type="Dual",
        launch_time=time(10, 0),
        landing_time=time(10, 20),
    )

    # 01:30 UTC on Jan 2 is Jan 1 in America/Los_Angeles.
    frozen_utc = datetime(2026, 1, 2, 1, 30, 0, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("siteconfig.timezone_utils.timezone.now", lambda: frozen_utc)

    captured = {}

    def _mock_send_mail(**kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(
        "duty_roster.management.commands.report_duty_delinquents.send_mail",
        _mock_send_mail,
    )

    call_command(
        "report_duty_delinquents",
        "--lookback-months=1",
        "--min-flights=1",
        "--min-membership-months=1",
        verbosity=0,
    )

    assert captured["recipient_list"] == ["manager@example.com"]
    assert "Monthly Duty Delinquency Report - 1 Member(s)" == captured["subject"]
    assert Notification.objects.filter(user=member_manager).exists()
