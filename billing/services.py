from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from billing.models import Ledger, LedgerEntry

MONEY_QUANTUM = Decimal("0.01")
CHARGE_KINDS = {
    LedgerEntry.Kind.FLIGHT_CHARGE,
    LedgerEntry.Kind.MISC_CHARGE,
    LedgerEntry.Kind.MANUAL_CHARGE,
}
REVERSIBLE_KINDS = set(LedgerEntry.Kind.values) - {LedgerEntry.Kind.REVERSAL}


def _money(amount):
    amount = Decimal(str(amount)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Billing amounts must be greater than zero.")
    return amount


def get_or_create_ledger(member):
    try:
        with transaction.atomic():
            ledger, _ = Ledger.objects.get_or_create(member=member)
            return ledger
    except IntegrityError:
        # Another transaction may have won the one-to-one insert race.
        return Ledger.objects.get(member=member)


def _validate_existing_source(
    existing, *, ledger, kind, effect, amount, effective_date
):
    if not existing:
        raise IntegrityError("Source key insert failed without a persisted entry.")
    values_match = (
        existing.ledger_id == ledger.id
        and existing.kind == kind
        and existing.effect == effect
        and existing.amount == amount
        and existing.effective_date == effective_date
    )
    if not values_match:
        raise ValidationError("Source key already identifies a different entry.")
    return existing


@transaction.atomic
def post_entry(
    *,
    member,
    actor,
    kind,
    effect,
    amount,
    effective_date,
    description,
    internal_note="",
    source_key=None,
):
    """Post one immutable entry, returning an existing identical source entry."""
    if actor is None:
        raise ValidationError("A posting actor is required.")
    if effective_date > date.today():
        raise ValidationError("Future effective dates are not allowed.")
    if source_key is not None:
        if not isinstance(source_key, str):
            raise ValidationError("Source keys must be strings.")
        source_key = source_key.strip() or None
    amount = _money(amount)
    ledger = get_or_create_ledger(member)
    if source_key:
        existing = LedgerEntry.objects.filter(source_key=source_key).first()
        if existing:
            values_match = (
                existing.ledger_id == ledger.id
                and existing.kind == kind
                and existing.effect == effect
                and existing.amount == amount
                and existing.effective_date == effective_date
            )
            if not values_match:
                raise ValidationError(
                    "Source key already identifies a different entry."
                )
            return existing
    entry_kwargs = dict(
        ledger=ledger,
        kind=kind,
        effect=effect,
        amount=amount,
        effective_date=effective_date,
        member_description=description,
        internal_note=internal_note,
        created_by=actor,
        source_key=source_key,
    )
    try:
        with transaction.atomic():
            return LedgerEntry.objects.create(**entry_kwargs)
    except IntegrityError:
        if not source_key:
            raise
        existing = LedgerEntry.objects.filter(source_key=source_key).first()
        return _validate_existing_source(
            existing,
            ledger=ledger,
            kind=kind,
            effect=effect,
            amount=amount,
            effective_date=effective_date,
        )


def post_charge(
    *,
    member,
    actor,
    amount,
    effective_date,
    description,
    kind=LedgerEntry.Kind.MANUAL_CHARGE,
    source_key=None,
    internal_note="",
):
    if kind not in CHARGE_KINDS:
        raise ValidationError("The selected kind is not a charge kind.")
    return post_entry(
        member=member,
        actor=actor,
        kind=kind,
        effect=LedgerEntry.Effect.DEBIT,
        amount=amount,
        effective_date=effective_date,
        description=description,
        internal_note=internal_note,
        source_key=source_key,
    )


def post_credit(
    *,
    member,
    actor,
    amount,
    effective_date,
    description,
    kind=LedgerEntry.Kind.PAYMENT,
    source_key=None,
    internal_note="",
):
    if kind not in {LedgerEntry.Kind.PAYMENT, LedgerEntry.Kind.CREDIT}:
        raise ValidationError("The selected kind is not a credit kind.")
    return post_entry(
        member=member,
        actor=actor,
        kind=kind,
        effect=LedgerEntry.Effect.CREDIT,
        amount=amount,
        effective_date=effective_date,
        description=description,
        internal_note=internal_note,
        source_key=source_key,
    )


@transaction.atomic
def reverse_entry(*, entry, actor, effective_date, reason):
    if actor is None:
        raise ValidationError("A reversal actor is required.")
    if effective_date > date.today():
        raise ValidationError("Future effective dates are not allowed.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A reversal reason is required.")
    original = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
    if original.kind == LedgerEntry.Kind.REVERSAL:
        raise ValidationError("A reversal cannot itself be reversed.")
    if hasattr(original, "reversal"):
        raise ValidationError("This entry has already been reversed.")
    return LedgerEntry.objects.create(
        ledger=original.ledger,
        kind=LedgerEntry.Kind.REVERSAL,
        effect=(
            LedgerEntry.Effect.CREDIT
            if original.effect == LedgerEntry.Effect.DEBIT
            else LedgerEntry.Effect.DEBIT
        ),
        amount=original.amount,
        effective_date=effective_date,
        member_description=f"Reversal: {original.member_description}",
        internal_note=reason,
        created_by=actor,
        reverses=original,
    )


def get_balance(ledger, as_of=None):
    entries = ledger.entries.all()
    if as_of is not None:
        entries = entries.filter(effective_date__lte=as_of)
    total = sum((entry.signed_amount for entry in entries), Decimal("0"))
    return total.quantize(MONEY_QUANTUM)
