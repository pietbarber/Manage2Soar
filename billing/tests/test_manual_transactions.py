from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from billing.models import LedgerEntry
from billing.services import (
    get_balance,
    override_opening_balance,
    post_guest_payment_pending,
    post_manual_charge,
    post_manual_credit,
    post_manual_payment,
    post_opening_balance,
    remit_guest_payment,
    reverse_manual_entry,
)
from members.models import Member


@pytest.fixture
def member(db):
    return Member.objects.create_user(username="manual-member")


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(username="manual-treasurer", treasurer=True)


def test_manual_posting_requires_treasurer_or_superuser(member):
    with pytest.raises(ValidationError, match="Only treasurers"):
        post_manual_charge(
            member=member,
            actor=member,
            amount="10",
            effective_date=date.today(),
            description="Manual charge",
            reason="Correction",
        )

    assert not hasattr(member, "billing_ledger")


def test_manual_entries_record_audit_fields_and_balance(member, treasurer):
    charge = post_manual_charge(
        member=member,
        actor=treasurer,
        amount="100",
        effective_date=date.today(),
        description="Club merchandise",
        reason="Member purchase",
    )
    payment = post_manual_payment(
        member=member,
        actor=treasurer,
        amount="60",
        effective_date=date.today(),
        description="Payment received",
        reason="Cash receipt 42",
    )
    credit = post_manual_credit(
        member=member,
        actor=treasurer,
        amount="10",
        effective_date=date.today(),
        description="Courtesy credit",
        reason="Board-approved adjustment",
    )

    assert get_balance(member.billing_ledger) == Decimal("30.00")
    assert charge.created_by_id == treasurer.pk
    assert charge.member_description == "Club merchandise"
    assert charge.internal_note == "Member purchase"
    assert payment.kind == LedgerEntry.Kind.PAYMENT
    assert credit.kind == LedgerEntry.Kind.CREDIT


def test_guest_payment_remains_member_liability_until_full_remittance(
    member, treasurer
):
    pending = post_guest_payment_pending(
        member=member,
        actor=member,
        amount="100",
        effective_date=date.today(),
        guest_name="Guest Pilot",
        payment_method="zelle",
        description="Guest flight payment pending",
    )

    assert pending.kind == LedgerEntry.Kind.GUEST_PAYMENT_PENDING
    assert get_balance(member.billing_ledger) == Decimal("100.00")

    with pytest.raises(ValidationError, match="full amount"):
        LedgerEntry.objects.create(
            ledger=member.billing_ledger,
            kind=LedgerEntry.Kind.GUEST_REMITTANCE,
            effect=LedgerEntry.Effect.CREDIT,
            amount="99.99",
            effective_date=date.today(),
            member_description="Partial remittance",
            created_by=treasurer,
            remits=pending,
        )

    remittance = remit_guest_payment(
        entry=pending,
        actor=treasurer,
        effective_date=date.today(),
        reference="Zelle confirmation 123",
    )

    assert remittance.kind == LedgerEntry.Kind.GUEST_REMITTANCE
    assert get_balance(member.billing_ledger) == Decimal("0.00")
    with pytest.raises(ValidationError, match="already been remitted"):
        remit_guest_payment(
            entry=pending,
            actor=treasurer,
            effective_date=date.today(),
        )
    with pytest.raises(ValidationError, match="Reverse the guest remittance"):
        reverse_manual_entry(
            entry=pending,
            actor=treasurer,
            effective_date=date.today(),
            reason="Attempted collection reversal",
        )


def test_guest_payment_remittance_is_treasurer_only(member, treasurer):
    pending = post_guest_payment_pending(
        member=member,
        actor=member,
        amount="25",
        effective_date=date.today(),
        guest_name="Guest Pilot",
        payment_method="cash",
        description="Guest cash pending",
    )

    with pytest.raises(ValidationError, match="Only treasurers"):
        remit_guest_payment(
            entry=pending,
            actor=member,
            effective_date=date.today(),
        )


def test_opening_balance_can_only_be_posted_once(member, treasurer):
    opening_balance = post_opening_balance(
        member=member,
        actor=treasurer,
        amount="25",
        effect=LedgerEntry.Effect.DEBIT,
        effective_date=date.today(),
        description="Opening receivable",
        reason="Imported opening balance",
    )
    assert opening_balance.kind == LedgerEntry.Kind.OPENING_BALANCE
    assert get_balance(member.billing_ledger) == Decimal("25.00")

    with pytest.raises(ValidationError, match="already been posted"):
        post_opening_balance(
            member=member,
            actor=treasurer,
            amount="5",
            effect=LedgerEntry.Effect.CREDIT,
            effective_date=date.today(),
            description="Opening credit",
            reason="Imported opening balance",
        )


def test_opening_balance_override_posts_an_auditable_adjustment(member, treasurer):
    post_opening_balance(
        member=member,
        actor=treasurer,
        amount="25",
        effect=LedgerEntry.Effect.DEBIT,
        effective_date=date.today(),
        description="Opening receivable",
        reason="Imported opening balance",
    )

    adjustment = override_opening_balance(
        member=member,
        actor=treasurer,
        amount="10",
        effect=LedgerEntry.Effect.CREDIT,
        effective_date=date.today(),
        description="Corrected source report",
        reason="Treasurer corrected import",
    )

    assert adjustment.kind == LedgerEntry.Kind.CREDIT
    assert adjustment.source_key.startswith("opening-override:")
    assert get_balance(member.billing_ledger) == Decimal("-10.00")
    assert (
        LedgerEntry.objects.filter(kind=LedgerEntry.Kind.OPENING_BALANCE).count() == 1
    )


def test_opening_balance_override_accounts_for_reversed_opening_balance(
    member, treasurer
):
    opening_balance = post_opening_balance(
        member=member,
        actor=treasurer,
        amount="25",
        effect=LedgerEntry.Effect.DEBIT,
        effective_date=date.today(),
        description="Opening receivable",
        reason="Imported opening balance",
    )
    reverse_manual_entry(
        entry=opening_balance,
        actor=treasurer,
        effective_date=date.today(),
        reason="Imported in error",
    )

    override_opening_balance(
        member=member,
        actor=treasurer,
        amount="10",
        effect=LedgerEntry.Effect.DEBIT,
        effective_date=date.today(),
        description="Corrected source report",
        reason="Treasurer corrected import",
    )

    assert get_balance(member.billing_ledger) == Decimal("10.00")


def test_manual_reversal_requires_staff_and_preserves_reason(member, treasurer):
    entry = post_manual_charge(
        member=member,
        actor=treasurer,
        amount="25",
        effective_date=date.today(),
        description="Manual charge",
        reason="Correction",
    )
    with pytest.raises(ValidationError, match="Only treasurers"):
        reverse_manual_entry(
            entry=entry,
            actor=member,
            effective_date=date.today(),
            reason="Unauthorized reversal",
        )

    reversal = reverse_manual_entry(
        entry=entry,
        actor=treasurer,
        effective_date=date.today(),
        reason="Entry posted in error",
    )
    assert reversal.reverses_id == entry.pk
    assert reversal.internal_note == "Entry posted in error"
    assert get_balance(member.billing_ledger) == Decimal("0.00")
