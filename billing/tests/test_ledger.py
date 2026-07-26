from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection, transaction

from billing.models import FlightChargeSnapshot, LedgerEntry
from billing.services import (
    get_balance,
    get_or_create_ledger,
    post_charge,
    post_credit,
    post_flight_charges,
    reverse_entry,
)
from logsheet.models import Airfield, Flight, Logsheet
from members.models import Member


@pytest.fixture
def member(db):
    return Member.objects.create_user(username="member")


@pytest.fixture
def actor(db):
    return Member.objects.create_user(username="treasurer")


def test_entries_derive_balance(member, actor):
    post_charge(
        member=member,
        actor=actor,
        amount="100",
        effective_date=date.today(),
        description="Flight",
    )
    post_credit(
        member=member,
        actor=actor,
        amount="60",
        effective_date=date.today(),
        description="Payment",
    )
    assert get_balance(member.billing_ledger) == Decimal("40.00")


def test_source_posting_is_idempotent(member, actor):
    kwargs = dict(
        member=member,
        actor=actor,
        amount="25",
        effective_date=date.today(),
        description="Flight",
        source_key="flight:1",
    )
    first = post_charge(**kwargs)
    second = post_charge(**kwargs)
    assert first.pk == second.pk
    assert member.billing_ledger.entries.count() == 1


def test_blank_source_key_is_not_persisted_as_an_idempotency_key(member, actor):
    kwargs = dict(
        member=member,
        actor=actor,
        amount="25",
        effective_date=date.today(),
        description="Unidentified charge",
        source_key="",
    )
    first = post_charge(**kwargs)
    second = post_charge(**kwargs)
    assert first.pk != second.pk
    assert first.source_key is None
    assert second.source_key is None


def test_source_semantic_conflict_is_rejected(member, actor):
    post_charge(
        member=member,
        actor=actor,
        amount="25",
        effective_date=date.today(),
        description="Flight",
        source_key="flight:conflict",
    )
    with pytest.raises(ValidationError):
        post_charge(
            member=member,
            actor=actor,
            amount="30",
            effective_date=date.today(),
            description="Different flight amount",
            source_key="flight:conflict",
        )


def test_flight_charge_requires_a_flight(member, actor):
    with pytest.raises(ValidationError):
        post_charge(
            member=member,
            actor=actor,
            amount="10",
            effective_date=date.today(),
            description="Missing source flight",
            kind=LedgerEntry.Kind.FLIGHT_CHARGE,
        )

    ledger = get_or_create_ledger(member)
    with pytest.raises(DatabaseError):
        LedgerEntry.objects.bulk_create(
            [
                LedgerEntry(
                    ledger=ledger,
                    kind=LedgerEntry.Kind.FLIGHT_CHARGE,
                    effect=LedgerEntry.Effect.DEBIT,
                    amount="10",
                    effective_date=date.today(),
                    member_description="Bypass",
                    created_by=actor,
                )
            ]
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_source_posting_is_idempotent(member, actor):
    def post():
        close_old_connections()
        try:
            return post_charge(
                member=Member.objects.get(pk=member.pk),
                actor=Member.objects.get(pk=actor.pk),
                amount="25",
                effective_date=date.today(),
                description="Concurrent flight",
                source_key="flight:concurrent",
            ).pk
        finally:
            close_old_connections()
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: post(), range(2)))
    assert results[0] == results[1]
    assert (
        member.billing_ledger.entries.filter(source_key="flight:concurrent").count()
        == 1
    )


def test_reversal_is_linked_and_changes_balance(member, actor):
    entry = post_charge(
        member=member,
        actor=actor,
        amount="25",
        effective_date=date.today(),
        description="Flight",
    )
    reversal = reverse_entry(
        entry=entry, actor=actor, effective_date=date.today(), reason="Correction"
    )
    assert reversal.reverses_id == entry.id
    assert get_balance(member.billing_ledger) == Decimal("0.00")


def test_invalid_amount_and_future_date_rejected(member, actor):
    with pytest.raises(ValidationError):
        post_charge(
            member=member,
            actor=actor,
            amount="0",
            effective_date=date.today(),
            description="Invalid",
        )
    with pytest.raises(ValidationError):
        post_charge(
            member=member,
            actor=actor,
            amount="1",
            effective_date=date.today() + timedelta(days=1),
            description="Future",
        )


def test_posted_entries_cannot_be_edited_or_deleted(member, actor):
    entry = post_charge(
        member=member,
        actor=actor,
        amount="25",
        effective_date=date.today(),
        description="Flight",
    )
    with pytest.raises(ValidationError):
        entry.member_description = "Changed"
        entry.save()
    with pytest.raises(ValidationError):
        entry.delete()


def test_kind_effect_validation(member, actor):
    ledger = get_or_create_ledger(member)
    with pytest.raises(ValidationError):
        LedgerEntry.objects.create(
            ledger=ledger,
            kind=LedgerEntry.Kind.PAYMENT,
            effect=LedgerEntry.Effect.DEBIT,
            amount="10",
            effective_date=date.today(),
            member_description="Bad",
            created_by=actor,
        )


def test_database_constraints_block_bulk_mutation(member, actor):
    entry = post_charge(
        member=member,
        actor=actor,
        amount="10",
        effective_date=date.today(),
        description="Charge",
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LedgerEntry.objects.filter(pk=entry.pk).update(
                kind=LedgerEntry.Kind.PAYMENT,
                effect=LedgerEntry.Effect.DEBIT,
            )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LedgerEntry.objects.filter(pk=entry.pk).delete()


def test_reversal_requires_original(member, actor):
    ledger = get_or_create_ledger(member)
    with pytest.raises(ValidationError):
        LedgerEntry.objects.create(
            ledger=ledger,
            kind=LedgerEntry.Kind.REVERSAL,
            effect=LedgerEntry.Effect.CREDIT,
            amount="10",
            effective_date=date.today(),
            member_description="Malformed reversal",
            created_by=actor,
        )


def test_reversal_requires_string_reason(member, actor):
    entry = post_charge(
        member=member,
        actor=actor,
        amount="10",
        effective_date=date.today(),
        description="Charge",
    )
    with pytest.raises(ValidationError):
        reverse_entry(
            entry=entry,
            actor=actor,
            effective_date=date.today(),
            reason=None,
        )


def test_flight_charge_posts_immutable_snapshot_once(member, actor, db):
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=Airfield.objects.create(identifier="KSTEP2", name="Step Two"),
        created_by=actor,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=member,
        flight_type="solo",
        tow_cost_actual=Decimal("20.00"),
        rental_cost_actual=Decimal("15.00"),
        instruction_fee_actual=Decimal("5.00"),
    )
    allocation = {
        "member": member,
        "tow": Decimal("20.00"),
        "rental": Decimal("15.00"),
        "instruction": Decimal("5.00"),
        "total": Decimal("40.00"),
        "allocation_rule": "full",
        "allocation_version": 1,
        "allocation_snapshot": {"pilot_id": member.pk},
    }
    first = post_flight_charges(flight=flight, actor=actor, allocations=[allocation])
    second = post_flight_charges(flight=flight, actor=actor, allocations=[allocation])
    assert first[0].pk == second[0].pk
    snapshot = FlightChargeSnapshot.objects.get(flight=flight)
    assert FlightChargeSnapshot.objects.filter(flight=flight).count() == 1
    assert get_balance(member.billing_ledger) == Decimal("40.00")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            FlightChargeSnapshot.objects.filter(pk=snapshot.pk).update(
                total_amount=Decimal("1.00")
            )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            FlightChargeSnapshot.objects.filter(pk=snapshot.pk).delete()


def test_snapshot_validates_entry_kind_and_member(member, actor):
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=Airfield.objects.create(identifier="KSTEP3", name="Step Three"),
        created_by=actor,
    )
    flight = Flight.objects.create(logsheet=logsheet, pilot=member, flight_type="solo")
    entry = post_charge(
        member=member,
        actor=actor,
        amount="10",
        effective_date=date.today(),
        description="Flight charge",
        kind=LedgerEntry.Kind.FLIGHT_CHARGE,
        flight=flight,
    )
    other_member = Member.objects.create_user(username="other-member")
    with pytest.raises(ValidationError):
        FlightChargeSnapshot.objects.create(
            ledger_entry=entry,
            flight=flight,
            billed_member=other_member,
            tow_amount="10",
            rental_amount="0",
            instruction_amount="0",
            total_amount="10",
            allocation_rule="full",
            allocation_version=1,
        )

    entry_two = post_charge(
        member=member,
        actor=actor,
        amount="10",
        effective_date=date.today(),
        description="Another flight charge",
        kind=LedgerEntry.Kind.FLIGHT_CHARGE,
        flight=flight,
    )
    with pytest.raises(DatabaseError):
        FlightChargeSnapshot.objects.bulk_create(
            [
                FlightChargeSnapshot(
                    ledger_entry=entry_two,
                    flight=flight,
                    billed_member=member,
                    tow_amount="9",
                    rental_amount="0",
                    instruction_amount="0",
                    total_amount="10",
                    allocation_rule="full",
                    allocation_version=1,
                )
            ]
        )
