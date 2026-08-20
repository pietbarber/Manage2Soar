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
