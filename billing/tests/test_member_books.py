"""Member ledger entries reaching the club books through Member Receivables."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from billing.ledger_services import (
    BankBalance,
    account_balance,
    go_live,
    verify_books,
)
from billing.models import Account, BillingPeriod, JournalEntry, LedgerEntry
from billing.services import (
    get_balance,
    post_flight_charges,
    post_guest_payment_pending,
    post_manual_charge,
    post_manual_credit,
    post_manual_payment,
    remit_guest_payment,
    reverse_manual_entry,
)
from logsheet.models import Airfield, Flight, Logsheet
from members.models import Member
from siteconfig.timezone_utils import get_club_today

TODAY = get_club_today
D = Decimal


@pytest.fixture(autouse=True)
def club_books(enable_club_accounting):
    return enable_club_accounting


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="mb-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )


@pytest.fixture
def member(db):
    return Member.objects.create_user(username="mb-member", is_active=True)


@pytest.fixture
def other_member(db):
    return Member.objects.create_user(username="mb-other", is_active=True)


def account(code):
    return Account.objects.get(code=code)


def receivables():
    return Account.objects.get(system_role=Account.Role.MEMBER_RECEIVABLES)


def start_books(treasurer, amount="1000"):
    return go_live(
        actor=treasurer,
        start_date=TODAY(),
        rows=[BankBalance(account=account("110"), name="Checking", amount=amount)],
    )


@pytest.fixture
def live(treasurer):
    return start_books(treasurer)


def charge(member, treasurer, amount="60", when=None, **kwargs):
    return post_manual_charge(
        member=member,
        actor=treasurer,
        amount=amount,
        effective_date=when or TODAY(),
        description="Charge",
        reason="Test",
        **kwargs,
    )


def payment(member, treasurer, amount="100", when=None, **kwargs):
    return post_manual_payment(
        member=member,
        actor=treasurer,
        amount=amount,
        effective_date=when or TODAY(),
        description="Payment",
        reason="Test",
        **kwargs,
    )


def test_go_live_folds_member_balances_into_the_opening_entry(
    treasurer, member, other_member
):
    yesterday = TODAY() - timedelta(days=1)
    charge(member, treasurer, "60", when=yesterday)
    payment(other_member, treasurer, "100", when=yesterday)

    opening = start_books(treasurer, amount="1000")

    lines = {
        line.member_id: line for line in opening.lines.filter(member__isnull=False)
    }
    assert (lines[member.pk].debit, lines[member.pk].credit) == (D("60"), D("0"))
    assert (lines[other_member.pk].debit, lines[other_member.pk].credit) == (
        D("0"),
        D("100"),
    )
    assert account_balance(receivables()) == D("-40.00")
    general_fund = Account.objects.get(system_role=Account.Role.GENERAL_FUND)
    assert account_balance(general_fund) == D("960.00")
    assert not JournalEntry.objects.filter(member_entry__isnull=False).exists()
    assert verify_books() == []


def test_member_entries_wait_for_go_live(treasurer, member):
    entry = charge(member, treasurer)
    assert not JournalEntry.objects.exists()

    start_books(treasurer)

    # Dated on the start date, so Finances Setup posts it on its own.
    journal = JournalEntry.objects.get(member_entry=entry)
    assert journal.date == TODAY()
    assert account_balance(account("450")) == D("60.00")
    assert verify_books() == []


def test_default_accounts_for_each_kind(treasurer, member, live):
    charge(member, treasurer, "60")
    payment(member, treasurer, "100")
    post_manual_credit(
        member=member,
        actor=treasurer,
        amount="15",
        effective_date=TODAY(),
        description="Volunteer credit",
        reason="Test",
    )
    pending = post_guest_payment_pending(
        member=member,
        actor=treasurer,
        amount="80",
        effective_date=TODAY(),
        guest_name="Guest",
        payment_method="cash",
        description="Guest flight",
    )
    remit_guest_payment(entry=pending, actor=treasurer, effective_date=TODAY())

    assert account_balance(account("450")) == D("60.00")
    assert account_balance(account("440")) == D("80.00")
    assert account_balance(account("580")) == D("15.00")
    assert account_balance(account("100")) == D("180.00")
    assert account_balance(receivables()) == get_balance(member.billing_ledger)
    assert get_balance(member.billing_ledger) == D("-55.00")
    assert verify_books() == []


def test_chosen_accounts_are_used(treasurer, member, live):
    charge(member, treasurer, "50", book_account=account("400"))
    payment(member, treasurer, "50", book_account=account("110"))
    pending = post_guest_payment_pending(
        member=member,
        actor=treasurer,
        amount="80",
        effective_date=TODAY(),
        guest_name="Guest",
        payment_method="zelle",
        description="Guest flight",
    )
    remit_guest_payment(
        entry=pending,
        actor=treasurer,
        effective_date=TODAY(),
        deposit_account=account("110"),
    )

    assert account_balance(account("400")) == D("50.00")
    assert account_balance(account("110")) == D("1130.00")
    assert account_balance(account("100")) == D("0.00")
    assert verify_books() == []


def test_wrong_account_for_kind_posts_nothing(treasurer, member, live):
    with pytest.raises(ValidationError, match="cash or bank account"):
        payment(member, treasurer, book_account=account("400"))
    with pytest.raises(ValidationError, match="income account"):
        charge(member, treasurer, book_account=account("110"))
    assert not LedgerEntry.objects.exists()


def test_flight_charge_splits_revenue(treasurer, member, live):
    logsheet = Logsheet.objects.create(
        log_date=TODAY(),
        airfield=Airfield.objects.create(identifier="KMB1", name="Books Field"),
        created_by=treasurer,
    )
    flight = Flight.objects.create(logsheet=logsheet, pilot=member, flight_type="solo")
    post_flight_charges(
        flight=flight,
        actor=treasurer,
        allocations=[
            {
                "member": member,
                "tow": D("20.00"),
                "rental": D("15.00"),
                "instruction": D("0.00"),
                "total": D("35.00"),
                "source_key": f"flight:{flight.pk}:member:{member.pk}:v1",
            }
        ],
    )

    assert account_balance(account("410")) == D("20.00")
    assert account_balance(account("420")) == D("15.00")
    assert account_balance(account("430")) == D("0.00")
    assert account_balance(receivables()) == D("35.00")
    assert verify_books() == []


def test_reversal_mirrors_the_posted_entry(treasurer, member, live):
    entry = payment(member, treasurer, "100", book_account=account("110"))
    reversal = reverse_manual_entry(
        entry=entry, actor=treasurer, effective_date=TODAY(), reason="Bounced"
    )

    original = JournalEntry.objects.get(member_entry=entry)
    assert original.reversal.member_entry == reversal
    assert account_balance(account("110")) == D("1000.00")
    assert account_balance(receivables()) == D("0.00")
    assert verify_books() == []


def test_reversing_an_entry_from_before_go_live(treasurer, member):
    entry = charge(member, treasurer, "60", when=TODAY() - timedelta(days=1))
    start_books(treasurer)

    reverse_manual_entry(
        entry=entry, actor=treasurer, effective_date=TODAY(), reason="Not owed"
    )

    # The charge lives in the opening entry, so its reversal uses the
    # default revenue account for a manual charge.
    assert account_balance(account("450")) == D("-60.00")
    assert account_balance(receivables()) == D("0.00")
    assert verify_books() == []


def test_late_entry_dated_before_start_posts_on_start_date(treasurer, member, live):
    entry = charge(member, treasurer, "60", when=TODAY() - timedelta(days=3))

    journal = JournalEntry.objects.get(member_entry=entry)
    assert journal.date == TODAY()
    assert account_balance(receivables()) == D("60.00")
    assert verify_books() == []


def test_cleared_start_date_falls_back_to_the_opening_entry(
    treasurer, member, live, club_books
):
    club_books.club_accounting_start_date = None
    club_books.save(update_fields=["club_accounting_start_date"])

    entry = charge(member, treasurer, "60", when=TODAY() - timedelta(days=3))

    assert JournalEntry.objects.get(member_entry=entry).date == TODAY()
    with pytest.raises(ValidationError, match="Keep that start date"):
        go_live(
            actor=treasurer,
            start_date=TODAY() - timedelta(days=1),
            rows=[BankBalance(account=account("110"), name="Checking", amount="1")],
        )


def test_closed_month_refuses_member_entry_once_books_are_live(treasurer, member, live):
    BillingPeriod.objects.update_or_create(
        year=TODAY().year, month=TODAY().month, defaults={"is_closed": True}
    )
    with pytest.raises(ValidationError, match="billing period is closed"):
        charge(member, treasurer)
    assert not LedgerEntry.objects.exists()


def test_go_live_rerun_keeps_member_activity(treasurer, member, live):
    charge(member, treasurer, "60")

    start_books(treasurer, amount="1200")

    assert account_balance(account("110")) == D("1200.00")
    assert account_balance(receivables()) == D("60.00")
    assert verify_books() == []
    with pytest.raises(ValidationError, match="Keep that start date"):
        go_live(
            actor=treasurer,
            start_date=TODAY() - timedelta(days=1),
            rows=[BankBalance(account=account("110"), name="Checking", amount="1")],
        )


def test_verify_flags_entries_missing_from_books_and_sync_posts_them(
    treasurer, member, live, club_books
):
    club_books.club_accounting_enabled = False
    club_books.save(update_fields=["club_accounting_enabled"])
    payment(member, treasurer, "25")
    club_books.club_accounting_enabled = True
    club_books.save(update_fields=["club_accounting_enabled"])

    problems = verify_books()
    assert any("mb-member" in problem for problem in problems)
    assert any("missing from the books" in problem for problem in problems)

    call_command("sync_member_books", "--post", "--actor", treasurer.username)

    assert verify_books() == []


def test_ledger_page_posts_to_chosen_account(client, treasurer, member, live):
    client.force_login(treasurer)
    url = reverse("billing:ledger_detail", args=[member.pk])
    data = {
        "kind": "payment",
        "amount": "40.00",
        "effective_date": TODAY().isoformat(),
        "description": "Zelle payment",
        "reason": "Received",
    }

    response = client.post(url, {**data, "book_account": account("400").pk})
    assert response.status_code == 200
    assert "book_account" in response.context["form"].errors

    response = client.post(url, {**data, "book_account": account("110").pk})
    assert response.status_code == 302
    assert account_balance(account("110")) == D("1040.00")
