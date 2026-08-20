from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from billing.exceptions import BillingDisabledError
from billing.models import FlightChargeSnapshot, Ledger, LedgerEntry
from billing.permissions import require_audit_text, require_manual_transaction_access

MONEY_QUANTUM = Decimal("0.01")
CHARGE_KINDS = {
    LedgerEntry.Kind.FLIGHT_CHARGE,
    LedgerEntry.Kind.MISC_CHARGE,
    LedgerEntry.Kind.MANUAL_CHARGE,
    LedgerEntry.Kind.GUEST_PAYMENT_PENDING,
}
REVERSIBLE_KINDS = set(LedgerEntry.Kind.values) - {LedgerEntry.Kind.REVERSAL}


def _require_billing_enabled():
    from siteconfig.models import SiteConfiguration

    if not SiteConfiguration.objects.filter(billing_app_enabled=True).exists():
        raise BillingDisabledError("Billing is disabled for this site.")


def _club_today():
    from siteconfig.timezone_utils import get_club_today

    return get_club_today()


def _money(amount):
    amount = Decimal(str(amount)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Billing amounts must be greater than zero.")
    return amount


def get_or_create_ledger(member):
    _require_billing_enabled()
    try:
        with transaction.atomic():
            ledger, _ = Ledger.objects.get_or_create(member=member)
            return ledger
    except IntegrityError:
        # Another transaction may have won the one-to-one insert race.
        return Ledger.objects.get(member=member)


def _validate_existing_source(
    existing,
    *,
    ledger,
    kind,
    effect,
    amount,
    effective_date,
    flight=None,
    correction_group=None,
):
    if not existing:
        raise IntegrityError("Source key insert failed without a persisted entry.")
    values_match = (
        existing.ledger_id == ledger.id
        and existing.kind == kind
        and existing.effect == effect
        and existing.amount == amount
        and existing.effective_date == effective_date
        and existing.flight_id == getattr(flight, "pk", None)
        and existing.correction_group == correction_group
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
    flight=None,
    correction_group=None,
    guest_name="",
    payment_method="",
    remits=None,
):
    """Post one immutable entry, returning an existing identical source entry."""
    _require_billing_enabled()
    if actor is None:
        raise ValidationError("A posting actor is required.")
    if effective_date > _club_today():
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
                and existing.flight_id == getattr(flight, "pk", None)
                and existing.correction_group == correction_group
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
        flight=flight,
        correction_group=correction_group,
        guest_name=guest_name,
        payment_method=payment_method,
        remits=remits,
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
            flight=flight,
            correction_group=correction_group,
        )


@transaction.atomic
def post_flight_charges(*, flight, actor, allocations, correction_group=None):
    """Record frozen Logsheet allocations exactly once per billed member."""
    _require_billing_enabled()
    posted = []
    for allocation in allocations:
        if Decimal(str(allocation["total"])) <= 0:
            continue
        total = _money(allocation["total"])
        member = allocation["member"]
        version = allocation.get("allocation_version", 1)
        source_key = allocation.get("source_key")
        if not source_key:
            raise ValidationError("Flight allocations must provide a source key.")
        entry = post_entry(
            member=member,
            actor=actor,
            kind=LedgerEntry.Kind.FLIGHT_CHARGE,
            effect=LedgerEntry.Effect.DEBIT,
            amount=total,
            effective_date=flight.logsheet.log_date,
            description=f"Flight charge #{flight.pk}",
            source_key=source_key,
            flight=flight,
            correction_group=correction_group,
        )
        snapshot_defaults = {
            "flight": flight,
            "billed_member": member,
            "tow_amount": allocation["tow"],
            "rental_amount": allocation["rental"],
            "instruction_amount": allocation["instruction"],
            "total_amount": total,
            "allocation_rule": allocation.get(
                "allocation_rule", flight.split_type or "full"
            ),
            "allocation_version": version,
            "allocation_snapshot": allocation.get("allocation_snapshot")
            or {"allocation_version": version},
        }
        snapshot, created = FlightChargeSnapshot.objects.get_or_create(
            ledger_entry=entry, defaults=snapshot_defaults
        )
        if not created:
            for field, expected in snapshot_defaults.items():
                actual = (
                    getattr(snapshot, f"{field}_id", None)
                    if field in {"flight", "billed_member"}
                    else getattr(snapshot, field)
                )
                expected_value = (
                    expected.pk if field in {"flight", "billed_member"} else expected
                )
                if actual != expected_value:
                    raise ValidationError(
                        "Existing flight charge snapshot conflicts with allocation."
                    )
        posted.append(entry)
    return posted


@transaction.atomic
def correct_flight_charges(*, flight, actor, allocations, effective_date, reason):
    """Replace every active charge for one flight with a complete allocation."""
    _require_billing_enabled()
    if not allocations:
        raise ValidationError("A correction requires replacement allocations.")
    versions = {allocation.get("allocation_version") for allocation in allocations}
    if len(versions) != 1 or None in versions:
        raise ValidationError("Correction allocations must share one version.")
    version = versions.pop()
    active_ids = list(
        LedgerEntry.objects.filter(
            flight=flight,
            kind=LedgerEntry.Kind.FLIGHT_CHARGE,
            reversal__isnull=True,
        ).values_list("pk", flat=True)
    )
    originals = list(LedgerEntry.objects.select_for_update().filter(pk__in=active_ids))
    if not originals:
        raise ValidationError("The flight has no active charges to correct.")
    current_version = max(
        entry.flight_snapshot.allocation_version for entry in originals
    )
    if version != current_version + 1:
        raise ValidationError("Correction allocations must use the next version.")

    correction_group = uuid4()
    reversals = [
        reverse_entry(
            entry=entry,
            actor=actor,
            effective_date=effective_date,
            reason=reason,
            correction_group=correction_group,
        )
        for entry in originals
    ]
    replacements = post_flight_charges(
        flight=flight,
        actor=actor,
        allocations=allocations,
        correction_group=correction_group,
    )
    return reversals, replacements


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
    flight=None,
):
    if kind not in CHARGE_KINDS:
        raise ValidationError("The selected kind is not a charge kind.")
    if kind == LedgerEntry.Kind.FLIGHT_CHARGE and flight is None:
        raise ValidationError("Flight charges must identify a flight.")
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
        flight=flight,
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


def post_manual_charge(
    *, member, actor, amount, effective_date, description, reason, source_key=None
):
    require_manual_transaction_access(actor)
    description = require_audit_text(description, "member description")
    reason = require_audit_text(reason, "reason")
    return post_charge(
        member=member,
        actor=actor,
        amount=amount,
        effective_date=effective_date,
        description=description,
        source_key=source_key,
        internal_note=reason,
    )


def post_guest_payment_pending(
    *,
    member,
    actor,
    amount,
    effective_date,
    guest_name,
    payment_method,
    description,
    flight=None,
    source_key=None,
):
    """Record a guest liability held by the responsible member."""
    description = require_audit_text(description, "member description")
    guest_name = require_audit_text(guest_name, "guest name")
    if payment_method not in {"cash", "check", "zelle"}:
        raise ValidationError("Choose cash, check, or Zelle for guest payments.")
    return post_entry(
        member=member,
        actor=actor,
        kind=LedgerEntry.Kind.GUEST_PAYMENT_PENDING,
        effect=LedgerEntry.Effect.DEBIT,
        amount=amount,
        effective_date=effective_date,
        description=description,
        source_key=source_key,
        flight=flight,
        guest_name=guest_name,
        payment_method=payment_method,
    )


@transaction.atomic
def remit_guest_payment(*, entry, actor, effective_date, reference=""):
    """Clear a guest payment in full after treasurer confirmation."""
    require_manual_transaction_access(actor)
    original = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
    if original.kind != LedgerEntry.Kind.GUEST_PAYMENT_PENDING:
        raise ValidationError("Only pending guest payments can be remitted.")
    if hasattr(original, "remittance"):
        raise ValidationError("This guest payment has already been remitted.")
    reference = reference.strip() if isinstance(reference, str) else ""
    return post_entry(
        member=original.ledger.member,
        actor=actor,
        kind=LedgerEntry.Kind.GUEST_REMITTANCE,
        effect=LedgerEntry.Effect.CREDIT,
        amount=original.amount,
        effective_date=effective_date,
        description=f"Guest remittance: {original.guest_name}",
        internal_note=reference,
        source_key=f"guest-remittance:{original.pk}",
        flight=original.flight,
        guest_name=original.guest_name,
        payment_method=original.payment_method,
        remits=original,
    )


def post_manual_payment(
    *, member, actor, amount, effective_date, description, reason, source_key=None
):
    require_manual_transaction_access(actor)
    description = require_audit_text(description, "member description")
    reason = require_audit_text(reason, "reason")
    return post_credit(
        member=member,
        actor=actor,
        amount=amount,
        effective_date=effective_date,
        description=description,
        source_key=source_key,
        internal_note=reason,
    )


def post_manual_credit(
    *, member, actor, amount, effective_date, description, reason, source_key=None
):
    require_manual_transaction_access(actor)
    description = require_audit_text(description, "member description")
    reason = require_audit_text(reason, "reason")
    return post_credit(
        member=member,
        actor=actor,
        amount=amount,
        effective_date=effective_date,
        description=description,
        kind=LedgerEntry.Kind.CREDIT,
        source_key=source_key,
        internal_note=reason,
    )


@transaction.atomic
def post_opening_balance(
    *, member, actor, amount, effect, effective_date, description, reason
):
    require_manual_transaction_access(actor)
    description = require_audit_text(description, "member description")
    reason = require_audit_text(reason, "reason")
    if effect not in LedgerEntry.Effect.values:
        raise ValidationError("Opening balance must specify a debit or credit effect.")
    ledger = get_or_create_ledger(member)
    if (
        LedgerEntry.objects.select_for_update()
        .filter(ledger=ledger, kind=LedgerEntry.Kind.OPENING_BALANCE)
        .exists()
    ):
        raise ValidationError(
            "An opening balance has already been posted for this account."
        )
    return post_entry(
        member=member,
        actor=actor,
        kind=LedgerEntry.Kind.OPENING_BALANCE,
        effect=effect,
        amount=amount,
        effective_date=effective_date,
        description=description,
        internal_note=reason,
    )


@transaction.atomic
def override_opening_balance(
    *, member, actor, amount, effect, effective_date, description, reason
):
    """Adjust an account's opening balance without changing posted history."""
    require_manual_transaction_access(actor)
    description = require_audit_text(description, "member description")
    reason = require_audit_text(reason, "reason")
    if effect not in LedgerEntry.Effect.values:
        raise ValidationError("Opening balance must specify a debit or credit effect.")

    ledger = get_or_create_ledger(member)
    entries = list(LedgerEntry.objects.select_for_update().filter(ledger=ledger))
    if not any(entry.kind == LedgerEntry.Kind.OPENING_BALANCE for entry in entries):
        raise ValidationError(
            "An opening balance must be posted before it can be overridden."
        )

    override_prefix = f"opening-override:{ledger.pk}:"
    opening_entry_ids = {
        entry.pk
        for entry in entries
        if entry.kind == LedgerEntry.Kind.OPENING_BALANCE
        or (entry.source_key and entry.source_key.startswith(override_prefix))
    }
    current_opening_balance = sum(
        (
            entry.signed_amount
            for entry in entries
            if entry.pk in opening_entry_ids
            or (
                entry.kind == LedgerEntry.Kind.REVERSAL
                and entry.reverses_id in opening_entry_ids
            )
        ),
        Decimal("0.00"),
    )
    target_balance = _money(amount)
    if effect == LedgerEntry.Effect.CREDIT:
        target_balance = -target_balance
    adjustment = target_balance - current_opening_balance
    if adjustment == 0:
        raise ValidationError("The account already has this opening balance.")

    return post_entry(
        member=member,
        actor=actor,
        kind=(
            LedgerEntry.Kind.MANUAL_CHARGE
            if adjustment > 0
            else LedgerEntry.Kind.CREDIT
        ),
        effect=(
            LedgerEntry.Effect.DEBIT if adjustment > 0 else LedgerEntry.Effect.CREDIT
        ),
        amount=abs(adjustment),
        effective_date=effective_date,
        description=f"Opening balance override: {description}",
        internal_note=reason,
        source_key=f"{override_prefix}{uuid4()}",
    )


def reverse_manual_entry(*, entry, actor, effective_date, reason):
    require_manual_transaction_access(actor)
    return reverse_entry(
        entry=entry,
        actor=actor,
        effective_date=effective_date,
        reason=reason,
    )


@transaction.atomic
def reverse_entry(*, entry, actor, effective_date, reason, correction_group=None):
    _require_billing_enabled()
    if actor is None:
        raise ValidationError("A reversal actor is required.")
    if effective_date > _club_today():
        raise ValidationError("Future effective dates are not allowed.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("A reversal reason is required.")
    original = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
    if original.kind not in REVERSIBLE_KINDS:
        raise ValidationError("A reversal cannot itself be reversed.")
    if original.kind == LedgerEntry.Kind.GUEST_PAYMENT_PENDING and hasattr(
        original, "remittance"
    ):
        raise ValidationError(
            "Reverse the guest remittance before reversing its collection."
        )
    if hasattr(original, "reversal"):
        raise ValidationError("This entry has already been reversed.")
    reversal = LedgerEntry(
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
        correction_group=correction_group,
    )
    reversal._service_created = True
    reversal.save()
    return reversal


def get_balance(ledger, as_of=None):
    entries = ledger.entries.all()
    if as_of is not None:
        entries = entries.filter(effective_date__lte=as_of)
    total = sum((entry.signed_amount for entry in entries), Decimal("0"))
    return total.quantize(MONEY_QUANTUM)


def get_statement_rows(ledger):
    """Return entries with the account balance after each posted entry."""
    if ledger is None:
        return []

    balance = Decimal("0.00")
    rows = []
    for entry in ledger.entries.select_related("created_by").order_by(
        "effective_date", "created_at", "id"
    ):
        balance += entry.signed_amount
        rows.append({"entry": entry, "running_balance": balance})
    return rows
