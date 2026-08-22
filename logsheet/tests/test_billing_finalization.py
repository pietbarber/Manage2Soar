from datetime import date, time
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from billing.models import FlightChargeSnapshot, LedgerEntry
from billing.services import get_balance
from logsheet import services as logsheet_services
from logsheet.models import (
    Airfield,
    Flight,
    Glider,
    Logsheet,
    LogsheetGuestPayment,
    RevisionLog,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture(autouse=True)
def enable_billing_app(db):
    return SiteConfiguration.objects.create(
        club_name="Finalization Test Club",
        domain_name="finalization-test.example.com",
        club_abbreviation="FTC",
        billing_app_enabled=True,
    )


@pytest.fixture
def member(db):
    return Member.objects.create_user(username="finalization-member")


def _flight(logsheet, pilot, *, with_actual=True, **overrides):
    flight_kwargs = {
        "logsheet": logsheet,
        "pilot": pilot,
        "flight_type": "solo",
        "tow_cost_actual": Decimal("20.00") if with_actual else None,
        "rental_cost_actual": Decimal("15.00") if with_actual else None,
        "instruction_fee_actual": Decimal("5.00") if with_actual else None,
    }
    flight_kwargs.update(overrides)
    return Flight.objects.create(**flight_kwargs)


def _allocation(flight, member):
    return {
        "member": member,
        "tow": Decimal("20.00"),
        "rental": Decimal("15.00"),
        "instruction": Decimal("5.00"),
        "total": Decimal("40.00"),
        "allocation_rule": "full",
        "allocation_version": 1,
        "source_key": f"flight:{flight.pk}:member:{member.pk}:v1",
        "allocation_snapshot": {"pilot_id": member.pk},
    }


@pytest.mark.django_db
def test_finalization_posts_frozen_charge_once(member, monkeypatch):
    airfield = Airfield.objects.create(identifier="KFIN", name="Finalization")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(logsheet, member)
    allocation = _allocation(flight, member)
    monkeypatch.setattr(
        logsheet_services,
        "get_billing_allocations",
        lambda current_flight: [allocation],
    )
    enqueue_summary = Mock()

    with TestCase.captureOnCommitCallbacks(execute=True):
        assert logsheet_services.finalize_logsheet_financials(
            logsheet_id=logsheet.pk,
            actor=member,
            enqueue_summary=enqueue_summary,
        )
    assert not logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=enqueue_summary,
    )

    assert LedgerEntry.objects.filter(flight=flight).count() == 1
    assert get_balance(member.billing_ledger) == Decimal("40.00")
    assert RevisionLog.objects.filter(logsheet=logsheet).count() == 1
    enqueue_summary.assert_called_once_with(logsheet.pk)


@pytest.mark.django_db
def test_guest_finalization_posts_pending_payment_to_responsible_member(member):
    airfield = Airfield.objects.create(identifier="KGST", name="Guest Flight")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Pilot",
        commercial_ride=False,
    )
    guest_payment = LogsheetGuestPayment.objects.create(
        logsheet=logsheet,
        flight=flight,
        responsible_member=member,
        guest_name="Guest Pilot",
        amount=Decimal("40.00"),
        payment_method="zelle",
    )

    assert logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=Mock(),
    )

    entry = LedgerEntry.objects.get(source_key=f"guest-payment:{guest_payment.pk}")
    assert entry.kind == LedgerEntry.Kind.GUEST_PAYMENT_PENDING
    assert entry.flight_id == flight.pk
    assert entry.guest_name == "Guest Pilot"
    assert get_balance(member.billing_ledger) == Decimal("40.00")


@pytest.mark.django_db
def test_guest_finalization_uses_frozen_total_not_stale_row_amount(member):
    """The pending guest entry is posted from the frozen *_actual totals,
    and the guest row is synced to that value, even if the row still holds
    a stale amount from before closeout edits."""
    airfield = Airfield.objects.create(identifier="KGST2", name="Guest Sync")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    # Frozen totals sum to 40 (20 + 15 + 5).
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Pilot",
        commercial_ride=False,
    )
    # Row holds a stale amount (30) that predates the cost freeze.
    guest_payment = LogsheetGuestPayment.objects.create(
        logsheet=logsheet,
        flight=flight,
        responsible_member=member,
        guest_name="Guest Pilot",
        amount=Decimal("30.00"),
        payment_method="zelle",
    )

    logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=Mock(),
    )

    entry = LedgerEntry.objects.get(source_key=f"guest-payment:{guest_payment.pk}")
    assert entry.kind == LedgerEntry.Kind.GUEST_PAYMENT_PENDING
    assert entry.effect == LedgerEntry.Effect.DEBIT
    # Posted from the frozen total (40), not the stale row amount (30).
    assert entry.amount == Decimal("40.00")
    assert get_balance(member.billing_ledger) == Decimal("40.00")
    # The row is synced to the authoritative frozen total.
    guest_payment.refresh_from_db()
    assert guest_payment.amount == Decimal("40.00")


@pytest.mark.django_db
def test_guest_finalization_requires_explicit_payment_method(member):
    airfield = Airfield.objects.create(identifier="KGM1", name="Guest Method")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Pilot",
        commercial_ride=False,
    )
    guest_payment = LogsheetGuestPayment.objects.create(
        logsheet=logsheet,
        flight=flight,
        responsible_member=member,
        guest_name="Guest Pilot",
        amount=Decimal("40.00"),
    )

    with pytest.raises(ValidationError, match="payment method"):
        logsheet_services.finalize_logsheet_financials(
            logsheet_id=logsheet.pk,
            actor=member,
            enqueue_summary=Mock(),
        )

    assert not Logsheet.objects.get(pk=logsheet.pk).finalized
    assert not LedgerEntry.objects.filter(
        source_key=f"guest-payment:{guest_payment.pk}"
    ).exists()


@pytest.mark.django_db
def test_finalization_rolls_back_cost_freezes_and_charges(member, monkeypatch):
    other_member = Member.objects.create_user(username="finalization-other")
    airfield = Airfield.objects.create(identifier="KROLL", name="Rollback")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    first = _flight(logsheet, member, with_actual=False)
    second = _flight(logsheet, other_member, with_actual=False)
    real_post = logsheet_services.post_flight_charges
    calls = 0

    def fail_on_second(*, flight, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValidationError("posting failed")
        kwargs.pop("allocations")
        return real_post(
            flight=flight,
            allocations=[_allocation(flight, flight.pilot)],
            **kwargs,
        )

    monkeypatch.setattr(logsheet_services, "post_flight_charges", fail_on_second)
    with pytest.raises(ValidationError, match="posting failed"):
        logsheet_services.finalize_logsheet_financials(
            logsheet_id=logsheet.pk,
            actor=member,
            enqueue_summary=Mock(),
        )

    first.refresh_from_db()
    second.refresh_from_db()
    logsheet.refresh_from_db()
    assert first.tow_cost_actual is None
    assert second.tow_cost_actual is None
    assert not logsheet.finalized
    assert not LedgerEntry.objects.filter(flight__logsheet=logsheet).exists()
    assert not RevisionLog.objects.filter(logsheet=logsheet).exists()


@pytest.mark.django_db
def test_finalization_freezes_costs_but_skips_ledger_when_billing_is_disabled(
    member, enable_billing_app
):
    enable_billing_app.billing_app_enabled = False
    enable_billing_app.save(update_fields=["billing_app_enabled"])
    airfield = Airfield.objects.create(identifier="KOFF", name="Billing Disabled")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="NFINOFF",
        rental_rate=Decimal("15.00"),
        club_owned=True,
        is_active=True,
    )
    flight = _flight(
        logsheet,
        member,
        with_actual=False,
        glider=glider,
        launch_time=time(10, 0),
        landing_time=time(11, 0),
    )
    enqueue_summary = Mock()

    with TestCase.captureOnCommitCallbacks(execute=True):
        assert logsheet_services.finalize_logsheet_financials(
            logsheet_id=logsheet.pk,
            actor=member,
            enqueue_summary=enqueue_summary,
        )

    flight.refresh_from_db()
    logsheet.refresh_from_db()
    assert logsheet.finalized
    assert flight.rental_cost_actual == Decimal("15.00")
    assert flight.instruction_fee_actual == Decimal("0.00")
    assert not LedgerEntry.objects.filter(flight=flight).exists()
    assert not FlightChargeSnapshot.objects.filter(flight=flight).exists()
    assert RevisionLog.objects.filter(logsheet=logsheet).count() == 1
    enqueue_summary.assert_called_once_with(logsheet.pk)


@pytest.mark.django_db
def test_guest_payment_completeness_required_even_when_billing_disabled(
    member, enable_billing_app
):
    """Guest-payment completeness is validated even with billing disabled.

    A finalized logsheet cannot be re-finalized to backfill settlement rows
    later, so payable guest flights must have complete settlement rows up
    front even though no ledger entries are posted while billing is off.
    """
    enable_billing_app.billing_app_enabled = False
    enable_billing_app.save(update_fields=["billing_app_enabled"])
    airfield = Airfield.objects.create(identifier="KGD1", name="Disabled Guest")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Pilot",
        commercial_ride=False,
    )

    with pytest.raises(ValidationError, match="Complete guest payment details"):
        logsheet_services.finalize_logsheet_financials(
            logsheet_id=logsheet.pk,
            actor=member,
            enqueue_summary=Mock(),
        )

    assert not Logsheet.objects.get(pk=logsheet.pk).finalized

    # With a complete guest-payment row, finalization succeeds (no posting).
    LogsheetGuestPayment.objects.create(
        logsheet=logsheet,
        flight=flight,
        responsible_member=member,
        guest_name="Guest Pilot",
        amount=Decimal("40.00"),
        payment_method="cash",
    )
    assert logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=Mock(),
    )
    assert Logsheet.objects.get(pk=logsheet.pk).finalized
    assert not LedgerEntry.objects.filter(flight=flight).exists()


@pytest.mark.django_db
def test_guest_finalization_ignores_zero_cost_guest_flight_without_payment(member):
    airfield = Airfield.objects.create(identifier="KGZ0", name="Zero Guest")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Zero",
        commercial_ride=False,
        tow_cost_actual=Decimal("0.00"),
        rental_cost_actual=Decimal("0.00"),
        instruction_fee_actual=Decimal("0.00"),
    )

    assert logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=Mock(),
    )

    assert Logsheet.objects.get(pk=logsheet.pk).finalized
    assert not LogsheetGuestPayment.objects.filter(logsheet=logsheet).exists()
    assert not LedgerEntry.objects.filter(
        source_key__startswith="guest-payment:",
        flight=flight,
    ).exists()


@pytest.mark.django_db
def test_guest_finalization_heals_zero_payment_for_payable_guest_flight(
    member,
):
    """A payable guest flight (positive frozen total) with a zero-amount row
    is healed to the authoritative frozen total and posted, rather than
    rejected: the frozen *_actual fields are the source of truth."""
    airfield = Airfield.objects.create(identifier="KGP0", name="Payable Guest")
    logsheet = Logsheet.objects.create(
        log_date=date.today(), airfield=airfield, created_by=member
    )
    flight = _flight(
        logsheet,
        member,
        guest_pilot_name="Guest Pilot",
        commercial_ride=False,
    )
    guest_payment = LogsheetGuestPayment.objects.create(
        logsheet=logsheet,
        flight=flight,
        responsible_member=member,
        guest_name="Guest Pilot",
        amount=Decimal("0.00"),
        payment_method="cash",
    )

    assert logsheet_services.finalize_logsheet_financials(
        logsheet_id=logsheet.pk,
        actor=member,
        enqueue_summary=Mock(),
    )

    assert Logsheet.objects.get(pk=logsheet.pk).finalized
    guest_payment.refresh_from_db()
    assert guest_payment.amount == Decimal("40.00")
    entry = LedgerEntry.objects.get(source_key=f"guest-payment:{guest_payment.pk}")
    assert entry.kind == LedgerEntry.Kind.GUEST_PAYMENT_PENDING
    assert entry.amount == Decimal("40.00")
