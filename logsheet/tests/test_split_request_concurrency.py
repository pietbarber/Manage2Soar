"""A split approval and a billing-period close that race each other.

Each thread uses its own database connection and commits on its own, the way
two requests at the same moment would, so these tests use transaction=True.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from billing import periods
from billing.models import BillingPeriod
from logsheet.models import Airfield, Flight, FlightSplitRequest, Logsheet
from members.models import Member
from siteconfig.models import MembershipStatus, SiteConfiguration
from siteconfig.timezone_utils import get_club_today

pytestmark = pytest.mark.django_db(transaction=True)


def threaded(func):
    """Run func on its own database connection, as a separate request would."""

    def run(*args):
        close_old_connections()
        try:
            return func(*args)
        finally:
            close_old_connections()
            connection.close()

    return run


def test_split_approval_and_period_close_at_once_do_not_deadlock(monkeypatch):
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Race Club", domain_name="race.example.com", club_abbreviation="RC"
    )
    config.billing_app_enabled = True
    config.save(update_fields=["billing_app_enabled"])
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    treasurer = Member.objects.create_user(
        username="pc-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )
    pilot = Member.objects.create_user(
        username="pc-pilot", is_active=True, membership_status="Full Member"
    )
    partner = Member.objects.create_user(
        username="pc-partner", is_active=True, membership_status="Full Member"
    )
    log_date = get_club_today()
    logsheet = Logsheet.objects.create(
        log_date=log_date,
        airfield=Airfield.objects.create(identifier="KPC1", name="Race Field"),
        created_by=treasurer,
        finalized=True,
    )
    flight = Flight.objects.create(logsheet=logsheet, pilot=pilot, flight_type="solo")
    split_request = FlightSplitRequest.objects.create(
        flight=flight,
        requester=pilot,
        requested_member=partner,
        split_type="even",
        reason="Shared flight",
        allocation_version=1,
        expires_at=timezone.now() + timedelta(days=7),
    )

    period_locked = threading.Event()
    approval_resuming = threading.Event()
    original = periods.lock_period_for_date
    original_save = BillingPeriod.save

    def slow(period_date):
        assert period_locked.wait(5), "period close did not acquire its lock"
        approval_resuming.set()
        return original(period_date)

    def signal_period_lock(self, *args, **kwargs):
        result = original_save(self, *args, **kwargs)
        if self.is_closed:
            period_locked.set()
            assert approval_resuming.wait(5), "approval did not resume"
        return result

    monkeypatch.setattr(periods, "lock_period_for_date", slow)
    monkeypatch.setattr(BillingPeriod, "save", signal_period_lock)

    @threaded
    def approve():
        client = Client()
        client.force_login(Member.objects.get(pk=partner.pk))
        return client.post(
            reverse("logsheet:flight_split_request_detail", args=[split_request.token]),
            {"decision": "accept"},
        ).status_code

    @threaded
    def close():
        periods.close_period(
            year=log_date.year,
            month=log_date.month,
            actor=Member.objects.get(pk=treasurer.pk),
            reason="Month reconciled",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        approved = executor.submit(approve)
        closed = executor.submit(close)
        # Either call raises if the database had to break a deadlock.
        closed.result()
        assert approved.result() == 302

    # The close won the race: the approval saw the closed month and stopped,
    # and the still-pending request was locked for a treasurer to decide.
    assert BillingPeriod.objects.get(year=log_date.year, month=log_date.month).is_closed
    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.LOCKED
