from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection, transaction

from billing.exceptions import ClubAccountingDisabledError
from billing.ledger_services import (
    Line,
    account_balance,
    account_balances,
    account_register,
    post_cash_transfer,
    post_expense,
    post_income,
    post_journal_entry,
    reverse_journal_entry,
    verify_books,
)
from billing.models import Account, BillingPeriod, JournalEntry, JournalLine
from members.models import Member
from siteconfig.timezone_utils import get_club_today


def today():
    return get_club_today()


@pytest.fixture(autouse=True)
def club_books(enable_club_accounting):
    return enable_club_accounting


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="gl-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )


@pytest.fixture
def member(db):
    return Member.objects.create_user(
        username="gl-member", is_active=True, membership_status="Full Member"
    )


@pytest.fixture
def checking(db):
    return Account.objects.create(
        code="101", name="Test Checking", type=Account.Type.ASSET, is_cash=True
    )


@pytest.fixture
def savings(db):
    return Account.objects.create(
        code="102", name="Test Savings", type=Account.Type.ASSET, is_cash=True
    )


def account(code):
    return Account.objects.get(code=code)


def role(name):
    return Account.objects.get(system_role=name)


def test_seeded_chart_has_every_system_role():
    roles = set(
        Account.objects.exclude(system_role=None).values_list("system_role", flat=True)
    )
    assert roles == set(Account.Role.values)
    assert list(
        Account.objects.filter(is_cash=True)
        .exclude(system_role=Account.Role.UNDEPOSITED_FUNDS)
        .values_list("code", "name")
    ) == [("110", "Checking")]


def test_expense_debits_expense_and_credits_cash(treasurer, checking):
    entry = post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("500"),
        amount="450.00",
        memo="October field rent",
        payee="Airport authority",
        reference="1042",
    )
    lines = {line.account.code: line for line in entry.lines.all()}
    assert lines["500"].debit == Decimal("450.00")
    assert lines["101"].credit == Decimal("450.00")
    assert account_balance(checking) == Decimal("-450.00")
    assert account_balance(account("500")) == Decimal("450.00")
    assert entry.payee == "Airport authority"
    assert entry.reference == "1042"


def test_income_and_transfer_move_cash(treasurer, checking, savings):
    post_income(
        actor=treasurer,
        date=today(),
        deposit_to=checking,
        income_account=account("460"),
        amount="1000",
        memo="Donation",
    )
    post_cash_transfer(
        actor=treasurer,
        date=today(),
        from_account=checking,
        to_account=savings,
        amount="250",
        memo="Move to savings",
    )
    assert account_balance(checking) == Decimal("750.00")
    assert account_balance(savings) == Decimal("250.00")
    assert account_balance(account("460")) == Decimal("1000.00")


def test_unbalanced_entry_is_refused(treasurer, checking):
    with pytest.raises(ValidationError, match="must equal credits"):
        post_journal_entry(
            actor=treasurer,
            date=today(),
            memo="Bad entry",
            lines=[
                Line(account=account("500"), debit=Decimal("10")),
                Line(account=checking, credit=Decimal("9.99")),
            ],
        )
    assert not JournalEntry.objects.exists()


@pytest.mark.parametrize(
    "lines_factory, message",
    [
        (lambda c: [Line(account=c, debit=Decimal("5"))], "at least two lines"),
        (
            lambda c: [
                Line(account=c, debit=Decimal("5"), credit=Decimal("5")),
                Line(account=account("500"), credit=Decimal("5")),
            ],
            "either a debit or a credit",
        ),
        (
            lambda c: [
                Line(account=c, debit=Decimal("-5")),
                Line(account=account("500"), credit=Decimal("-5")),
            ],
            "cannot be negative",
        ),
    ],
)
def test_malformed_lines_are_refused(treasurer, checking, lines_factory, message):
    with pytest.raises(ValidationError, match=message):
        post_journal_entry(
            actor=treasurer, date=today(), memo="Bad", lines=lines_factory(checking)
        )


def test_manual_entries_cannot_touch_member_receivables(treasurer, member, checking):
    receivables = role(Account.Role.MEMBER_RECEIVABLES)
    with pytest.raises(ValidationError, match="only through member ledgers"):
        post_journal_entry(
            actor=treasurer,
            date=today(),
            memo="Sneaky",
            lines=[
                Line(account=checking, debit=Decimal("5")),
                Line(account=receivables, credit=Decimal("5"), member=member),
            ],
        )


def test_only_receivables_lines_name_a_member(treasurer, member, checking):
    with pytest.raises(ValidationError, match="Only Member Receivables"):
        post_journal_entry(
            actor=treasurer,
            date=today(),
            memo="Member on cash line",
            lines=[
                Line(account=checking, debit=Decimal("5"), member=member),
                Line(account=account("490"), credit=Decimal("5")),
            ],
        )


def test_non_treasurer_cannot_post(member, checking):
    with pytest.raises(ValidationError, match="treasurers and superusers"):
        post_expense(
            actor=member,
            date=today(),
            paid_from=checking,
            expense_account=account("500"),
            amount="1",
            memo="Nope",
        )


def test_posting_requires_club_accounting(treasurer, checking, enable_club_accounting):
    enable_club_accounting.club_accounting_enabled = False
    enable_club_accounting.save(update_fields=["club_accounting_enabled"])
    with pytest.raises(ClubAccountingDisabledError):
        post_expense(
            actor=treasurer,
            date=today(),
            paid_from=checking,
            expense_account=account("500"),
            amount="1",
            memo="Off",
        )


def test_future_dates_are_refused(treasurer, checking):
    with pytest.raises(ValidationError, match="Future dates"):
        post_expense(
            actor=treasurer,
            date=today() + timedelta(days=1),
            paid_from=checking,
            expense_account=account("500"),
            amount="1",
            memo="Tomorrow",
        )


def test_entries_must_follow_the_start_date(
    treasurer, checking, enable_club_accounting
):
    enable_club_accounting.club_accounting_start_date = today()
    enable_club_accounting.save(update_fields=["club_accounting_start_date"])
    with pytest.raises(ValidationError, match="after the books' start date"):
        post_expense(
            actor=treasurer,
            date=today(),
            paid_from=checking,
            expense_account=account("500"),
            amount="1",
            memo="On start date",
        )


def test_closed_billing_period_refuses_entries(treasurer, checking):
    BillingPeriod.objects.create(year=today().year, month=today().month, is_closed=True)
    with pytest.raises(ValidationError, match="billing period is closed"):
        post_expense(
            actor=treasurer,
            date=today(),
            paid_from=checking,
            expense_account=account("500"),
            amount="1",
            memo="Closed",
        )


def test_source_key_is_idempotent(treasurer, checking):
    kwargs = dict(
        actor=treasurer,
        date=today(),
        memo="Keyed",
        source_key="test:keyed",
        lines=[
            Line(account=account("500"), debit=Decimal("20")),
            Line(account=checking, credit=Decimal("20")),
        ],
    )
    first = post_journal_entry(**kwargs)
    assert post_journal_entry(**kwargs) == first
    assert JournalEntry.objects.count() == 1

    kwargs["lines"] = [
        Line(account=account("500"), debit=Decimal("21")),
        Line(account=checking, credit=Decimal("21")),
    ]
    with pytest.raises(ValidationError, match="different journal entry"):
        post_journal_entry(**kwargs)


def test_reversal_mirrors_lines_and_cannot_repeat(treasurer, checking):
    original = post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("510"),
        amount="300",
        memo="Wrong amount",
    )
    reversal = reverse_journal_entry(
        entry=original, actor=treasurer, date=today(), reason="Typo"
    )
    assert reversal.source == JournalEntry.Source.REVERSAL
    assert reversal.reverses == original
    assert account_balance(checking) == Decimal("0.00")
    assert account_balance(account("510")) == Decimal("0.00")
    with pytest.raises(ValidationError, match="already been reversed"):
        reverse_journal_entry(entry=original, actor=treasurer, date=today(), reason="x")
    with pytest.raises(ValidationError, match="cannot itself be reversed"):
        reverse_journal_entry(entry=reversal, actor=treasurer, date=today(), reason="x")


def test_reversal_cannot_predate_original(treasurer, checking):
    original = post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("510"),
        amount="1",
        memo="Today",
    )
    with pytest.raises(ValidationError, match="before the original"):
        reverse_journal_entry(
            entry=original,
            actor=treasurer,
            date=today() - timedelta(days=1),
            reason="Backdated",
        )


def test_journal_records_are_immutable_through_the_orm(treasurer, checking):
    entry = post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("500"),
        amount="5",
        memo="Immutable",
    )
    line = entry.lines.first()
    with pytest.raises(ValidationError):
        entry.save()
    with pytest.raises(ValidationError):
        entry.delete()
    with pytest.raises(ValidationError):
        line.save()
    with pytest.raises(ValidationError):
        line.delete()
    with pytest.raises(ValidationError):
        JournalLine.objects.bulk_create([JournalLine(entry=entry, account=checking)])


def test_journal_entries_cannot_be_created_outside_the_service(treasurer):
    with pytest.raises(ValidationError, match="ledger service"):
        JournalEntry(
            date=today(),
            memo="Direct",
            source=JournalEntry.Source.MANUAL,
            created_by=treasurer,
        ).save()


@pytest.mark.django_db(transaction=True)
def test_database_triggers_block_journal_updates_and_deletes():
    treasurer = Member.objects.create_user(
        username="gl-trigger-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )
    checking = Account.objects.create(
        code="105", name="Trigger Checking", type=Account.Type.ASSET, is_cash=True
    )
    entry = post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=Account.objects.get(code="500"),
        amount="5",
        memo="Trigger",
    )
    for sql, params in (
        ("UPDATE billing_journalentry SET memo = %s WHERE id = %s", ["x", entry.pk]),
        ("DELETE FROM billing_journalentry WHERE id = %s", [entry.pk]),
        (
            "UPDATE billing_journalline SET debit = %s WHERE entry_id = %s",
            [1, entry.pk],
        ),
        ("DELETE FROM billing_journalline WHERE entry_id = %s", [entry.pk]),
    ):
        with pytest.raises(DatabaseError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)


def test_system_accounts_are_protected():
    receivables = role(Account.Role.MEMBER_RECEIVABLES)
    with pytest.raises(ValidationError):
        receivables.delete()
    receivables.type = Account.Type.LIABILITY
    with pytest.raises(ValidationError, match="role needs"):
        receivables.save()
    general_fund = role(Account.Role.GENERAL_FUND)
    general_fund.is_active = False
    with pytest.raises(ValidationError, match="cannot be deactivated"):
        general_fund.save()


def test_account_type_is_locked_once_posted(treasurer, checking):
    post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("520"),
        amount="5",
        memo="Fuel",
    )
    fuel = account("520")
    fuel.type = Account.Type.INCOME
    with pytest.raises(ValidationError, match="cannot change type"):
        fuel.save()


def test_cash_accounts_must_be_assets():
    with pytest.raises(ValidationError):
        Account.objects.create(
            code="299",
            name="Cash liability",
            type=Account.Type.LIABILITY,
            is_cash=True,
        )


def test_trial_balance_and_register(treasurer, checking, savings):
    post_income(
        actor=treasurer,
        date=today() - timedelta(days=2),
        deposit_to=checking,
        income_account=account("400"),
        amount="500",
        memo="Dues",
    )
    post_expense(
        actor=treasurer,
        date=today() - timedelta(days=1),
        paid_from=checking,
        expense_account=account("530"),
        amount="120",
        memo="Insurance",
    )
    post_cash_transfer(
        actor=treasurer,
        date=today(),
        from_account=checking,
        to_account=savings,
        amount="80",
        memo="Sweep",
    )
    rows = account_balances()
    assert sum(row["debit"] for row in rows) == sum(row["credit"] for row in rows)
    debit_normal = sum(row["balance"] for row in rows if row["account"].is_debit_normal)
    credit_normal = sum(
        row["balance"] for row in rows if not row["account"].is_debit_normal
    )
    assert debit_normal == credit_normal

    register = account_register(checking, start=today() - timedelta(days=1))
    assert register["opening_balance"] == Decimal("500.00")
    assert [row["balance"] for row in register["rows"]] == [
        Decimal("380.00"),
        Decimal("300.00"),
    ]
    assert register["rows"][1]["other_accounts"] == ["Test Savings"]
    assert verify_books() == []


def test_verify_books_command(treasurer, checking):
    post_expense(
        actor=treasurer,
        date=today(),
        paid_from=checking,
        expense_account=account("550"),
        amount="3",
        memo="Fee",
    )
    call_command("verify_books")


def test_verify_books_command_fails_on_problems(monkeypatch):
    monkeypatch.setattr(
        "billing.management.commands.verify_books.verify_books",
        lambda: ["Journal entry #1 does not balance."],
    )
    with pytest.raises(CommandError, match="1 problem"):
        call_command("verify_books")


def test_siteconfig_requires_billing_for_club_accounting(enable_club_accounting):
    enable_club_accounting.billing_app_enabled = False
    with pytest.raises(ValidationError) as excinfo:
        enable_club_accounting.full_clean()
    assert "club_accounting_enabled" in excinfo.value.message_dict


def test_opening_source_must_use_start_date(
    treasurer, checking, enable_club_accounting
):
    start = (
        date(today().year, 1, 1) if today().month > 1 else today() - timedelta(days=1)
    )
    enable_club_accounting.club_accounting_start_date = start
    enable_club_accounting.save(update_fields=["club_accounting_start_date"])
    lines = [
        Line(account=checking, debit=Decimal("100")),
        Line(account=role(Account.Role.OPENING_BALANCE_EQUITY), credit=Decimal("100")),
    ]
    with pytest.raises(ValidationError, match="dated on the books' start date"):
        post_journal_entry(
            actor=treasurer,
            date=today(),
            memo="Opening",
            lines=lines,
            source=JournalEntry.Source.OPENING,
        )
    entry = post_journal_entry(
        actor=treasurer,
        date=start,
        memo="Opening",
        lines=lines,
        source=JournalEntry.Source.OPENING,
    )
    with pytest.raises(ValidationError, match="opening entry cannot be reversed"):
        reverse_journal_entry(entry=entry, actor=treasurer, date=today(), reason="x")
