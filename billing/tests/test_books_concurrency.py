"""Club-books writes that race each other, run on real threads.

Each thread uses its own database connection and commits on its own, the way
two requests at the same moment would, so these tests use transaction=True.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from billing import ledger_services, periods
from billing.ledger_services import (
    BankBalance,
    Line,
    go_live,
    post_expense,
    post_journal_entry,
    verify_books,
)
from billing.models import Account, JournalEntry, LedgerEntry
from billing.services import post_flight_charges, post_manual_charge
from logsheet.models import Airfield, Flight, FlightSplitRequest, Logsheet
from logsheet.utils.flight_charges import get_billing_allocations
from members.models import Member
from siteconfig.models import MembershipStatus
from siteconfig.timezone_utils import get_club_today

pytestmark = pytest.mark.django_db(transaction=True)

TODAY = get_club_today


@pytest.fixture(autouse=True)
def club_books(enable_club_accounting):
    return enable_club_accounting


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="cc-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )


@pytest.fixture
def pause_setup_scan(monkeypatch):
    """Make Finances Setup pause right after it totals member balances.

    Calling the fixture installs the pause and returns an event that's set
    when the pause starts, so another thread can act during it.
    """

    def install():
        scanned = threading.Event()
        original = ledger_services._opening_receivables_lines

        def slow(start_date):
            lines = original(start_date)
            scanned.set()
            time.sleep(0.5)
            return lines

        monkeypatch.setattr(ledger_services, "_opening_receivables_lines", slow)
        return scanned

    return install


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


def bank(amount):
    checking = Account.objects.get(code="110")
    return BankBalance(account=checking, name=checking.name, amount=amount)


def test_identical_journal_entries_posted_at_once_post_once(treasurer, books_started):
    both_ready = threading.Barrier(2)

    @threaded
    def post(_):
        both_ready.wait()
        return post_journal_entry(
            actor=Member.objects.get(pk=treasurer.pk),
            date=TODAY(),
            memo="Keyed",
            source_key="test:concurrent",
            lines=[
                Line(account=Account.objects.get(code="520"), debit=Decimal("20")),
                Line(account=Account.objects.get(code="110"), credit=Decimal("20")),
            ],
        ).pk

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(post, range(2))

    assert first == second
    assert JournalEntry.objects.filter(source_key="test:concurrent").count() == 1


def test_expense_waits_for_a_finances_setup_rerun(treasurer, pause_setup_scan):
    go_live(
        actor=treasurer, start_date=TODAY() - timedelta(days=10), rows=[bank("1000")]
    )
    scanned = pause_setup_scan()

    @threaded
    def rerun():
        go_live(
            actor=Member.objects.get(pk=treasurer.pk),
            start_date=TODAY() - timedelta(days=2),
            rows=[bank("1000")],
        )

    @threaded
    def expense():
        scanned.wait(5)
        try:
            post_expense(
                actor=Member.objects.get(pk=treasurer.pk),
                date=TODAY() - timedelta(days=5),
                paid_from=Account.objects.get(code="110"),
                expense_account=Account.objects.get(code="520"),
                amount="5",
                memo="Fuel",
            )
        except ValidationError as exc:
            return exc.messages
        return []

    with ThreadPoolExecutor(max_workers=2) as executor:
        setup = executor.submit(rerun)
        refused = executor.submit(expense).result()
        setup.result()

    # The expense waited for the rerun, then saw the new start date.
    assert any("start date" in message for message in refused)
    assert not JournalEntry.objects.filter(source=JournalEntry.Source.MANUAL).exists()


def test_member_charge_saved_during_setup_reaches_the_books(
    treasurer, pause_setup_scan
):
    member = Member.objects.create_user(username="cc-member", is_active=True)
    scanned = pause_setup_scan()

    @threaded
    def setup():
        go_live(
            actor=Member.objects.get(pk=treasurer.pk),
            start_date=TODAY(),
            rows=[bank("1000")],
        )

    @threaded
    def charge():
        scanned.wait(5)
        return post_manual_charge(
            member=Member.objects.get(pk=member.pk),
            actor=Member.objects.get(pk=treasurer.pk),
            amount="60",
            effective_date=TODAY() - timedelta(days=1),
            description="Charge",
            reason="Test",
        ).pk

    with ThreadPoolExecutor(max_workers=2) as executor:
        started = executor.submit(setup)
        entry_pk = executor.submit(charge).result()
        started.result()

    # The charge waited for setup, so it posted on its own after the opening.
    entry = LedgerEntry.objects.get(pk=entry_pk)
    assert JournalEntry.objects.filter(member_entry=entry).exists()
    assert verify_books() == []


def test_split_approval_and_member_charge_at_once_both_post(
    treasurer, books_started, monkeypatch
):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    pilot = Member.objects.create_user(
        username="cc-pilot", is_active=True, membership_status="Full Member"
    )
    partner = Member.objects.create_user(
        username="cc-partner", is_active=True, membership_status="Full Member"
    )
    logsheet = Logsheet.objects.create(
        log_date=TODAY(),
        airfield=Airfield.objects.create(identifier="KCC1", name="Race Field"),
        created_by=treasurer,
        finalized=True,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=pilot,
        flight_type="solo",
        tow_cost_actual=Decimal("40.00"),
    )
    post_flight_charges(
        flight=flight, actor=treasurer, allocations=get_billing_allocations(flight)
    )
    split_request = FlightSplitRequest.objects.create(
        flight=flight,
        requester=pilot,
        requested_member=partner,
        split_type="even",
        reason="Shared flight",
        allocation_version=1,
        expires_at=timezone.now() + timedelta(days=7),
    )

    # Pause the approval right after it locks the billing period. The ledger
    # services imported their own copy, so the charge doesn't pause.
    period_locked = threading.Event()
    original = periods.lock_period_for_date

    def slow(period_date):
        closed = original(period_date)
        period_locked.set()
        time.sleep(0.5)
        return closed

    monkeypatch.setattr(periods, "lock_period_for_date", slow)

    @threaded
    def approve():
        client = Client()
        client.force_login(Member.objects.get(pk=partner.pk))
        return client.post(
            reverse("logsheet:flight_split_request_detail", args=[split_request.token]),
            {"decision": "accept"},
        ).status_code

    @threaded
    def charge():
        period_locked.wait(5)
        return post_manual_charge(
            member=Member.objects.get(pk=pilot.pk),
            actor=Member.objects.get(pk=treasurer.pk),
            amount="15",
            effective_date=TODAY(),
            description="Charge",
            reason="Test",
        ).pk

    with ThreadPoolExecutor(max_workers=2) as executor:
        approved = executor.submit(approve)
        entry_pk = executor.submit(charge).result()
        assert approved.result() == 302

    # Neither request deadlocked; the charge waited for the approval.
    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.ACCEPTED
    entry = LedgerEntry.objects.get(pk=entry_pk)
    assert JournalEntry.objects.filter(member_entry=entry).exists()
    assert verify_books() == []
