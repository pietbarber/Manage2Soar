from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from billing.services import post_flight_charges, post_guest_payment_pending
from siteconfig.models import SiteConfiguration

from .models import Flight, Logsheet, LogsheetGuestPayment, RevisionLog
from .utils.finalization_email import enqueue_finalization_summary_email_job
from .utils.flight_charges import get_billing_allocations


@transaction.atomic
def finalize_logsheet_financials(
    *, logsheet_id, actor, enqueue_summary=enqueue_finalization_summary_email_job
):
    """Freeze costs, optionally post ledger charges, and finalize atomically."""
    locked_logsheet = Logsheet.objects.select_for_update().get(pk=logsheet_id)
    if locked_logsheet.finalized:
        return False

    billing_enabled = SiteConfiguration.objects.filter(
        billing_app_enabled=True
    ).exists()

    # Keep nullable relationships out of the locking query. PostgreSQL rejects
    # FOR UPDATE queries that lock the nullable side of an outer join.
    locked_flights = list(
        Flight.objects.select_for_update().filter(logsheet=locked_logsheet)
    )
    for flight in locked_flights:
        # Track which cost fields actually changed to avoid no-op saves
        costs_to_save = []
        if flight.tow_cost_actual is None:
            flight.tow_cost_actual = flight.tow_cost_calculated
            costs_to_save.append("tow_cost_actual")
        if flight.rental_cost_actual is None:
            flight.rental_cost_actual = flight.rental_cost
            costs_to_save.append("rental_cost_actual")
        if flight.instruction_fee_actual is None:
            flight.instruction_fee_actual = flight.instruction_fee_calculated
            costs_to_save.append("instruction_fee_actual")

        # Only save if we actually changed something, and persist only those fields
        # to avoid rewriting unrelated auto-calculated fields like duration
        if costs_to_save:
            flight.save(update_fields=costs_to_save)

        if billing_enabled:
            post_flight_charges(
                flight=flight,
                actor=actor,
                allocations=get_billing_allocations(flight),
            )

    # Lock the guest-payment rows alongside the logsheet/flights so their
    # details cannot change mid-transaction. Lock the base table only (no
    # joins): PostgreSQL rejects FOR UPDATE on the nullable side of an outer
    # join, and responsible_member is nullable. Then re-fetch the related
    # fields for the posting loop below (materialized to a list once).
    locked_guest_pks = list(
        locked_logsheet.guest_payments.select_for_update().values_list("pk", flat=True)
    )
    guest_payments = list(
        LogsheetGuestPayment.objects.select_related("flight", "responsible_member")
        .filter(logsheet=locked_logsheet, pk__in=locked_guest_pks)
        .order_by("pk")
    )

    # Guest-payment completeness is validated even when billing is disabled:
    # a finalized logsheet cannot be re-finalized to backfill settlement rows
    # later, so payable guest flights must have complete rows up front.
    # Guest settlement excludes commercial rides (prepaid; handled via the
    # commercial-ride ticket flow), so they do not require a pending entry.
    # Only guest flights with a positive frozen total require posting.
    payable_guest_flight_ids = set()
    for flight in locked_flights:
        if flight.commercial_ride or not (flight.guest_pilot_name or "").strip():
            continue
        frozen_total = (
            (flight.tow_cost_actual or Decimal("0.00"))
            + (flight.rental_cost_actual or Decimal("0.00"))
            + (flight.instruction_fee_actual or Decimal("0.00"))
        )
        if frozen_total > 0:
            payable_guest_flight_ids.add(flight.pk)

    recorded_guest_flight_ids = {payment.flight_id for payment in guest_payments}
    missing_guest_payments = payable_guest_flight_ids - recorded_guest_flight_ids
    if missing_guest_payments:
        raise ValidationError(
            "Complete guest payment details before finalizing flights: "
            + ", ".join(f"#{flight_id}" for flight_id in sorted(missing_guest_payments))
        )
    for guest_payment in guest_payments:
        # Commercial rides are prepaid; do not require settlement entries.
        if guest_payment.flight.commercial_ride:
            continue
        # Zero-cost guest flights do not need settlement entries.
        if guest_payment.flight_id not in payable_guest_flight_ids:
            continue
        if not guest_payment.responsible_member_id:
            raise ValidationError(
                "Every guest payment must identify a responsible member."
            )
        if not guest_payment.payment_method:
            raise ValidationError("Every guest payment must identify a payment method.")
        if guest_payment.amount <= 0:
            raise ValidationError(
                "Every payable guest flight must have a positive payment amount."
            )

    if billing_enabled:
        for guest_payment in guest_payments:
            # Commercial rides are prepaid; do not post a pending guest entry.
            if guest_payment.flight.commercial_ride:
                continue
            # Zero-cost guest flights do not need settlement entries.
            if guest_payment.flight_id not in payable_guest_flight_ids:
                continue
            post_guest_payment_pending(
                member=guest_payment.responsible_member,
                actor=actor,
                amount=guest_payment.amount,
                effective_date=locked_logsheet.log_date,
                guest_name=guest_payment.guest_name,
                payment_method=guest_payment.payment_method,
                description=(
                    f"Guest payment pending for flight #{guest_payment.flight_id}"
                ),
                flight=guest_payment.flight,
                source_key=f"guest-payment:{guest_payment.pk}",
            )

    locked_logsheet.finalized = True
    locked_logsheet.save()
    RevisionLog.objects.create(
        logsheet=locked_logsheet,
        revised_by=actor,
        note="Logsheet finalized",
    )
    transaction.on_commit(lambda: enqueue_summary(locked_logsheet.pk))
    return True
