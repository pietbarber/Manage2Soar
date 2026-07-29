from datetime import date

import pytest

from billing.exceptions import BillingDisabledError
from billing.models import LedgerEntry
from billing.services import (
    correct_flight_charges,
    post_charge,
    post_flight_charges,
    reverse_entry,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def members(db):
    return (
        Member.objects.create_user(username="disabled-member"),
        Member.objects.create_user(username="disabled-actor", treasurer=True),
    )


def test_posting_is_rejected_when_billing_is_disabled(members):
    member, actor = members
    SiteConfiguration.objects.update(billing_app_enabled=False)

    with pytest.raises(BillingDisabledError, match="Billing is disabled"):
        post_charge(
            member=member,
            actor=actor,
            amount="10.00",
            effective_date=date.today(),
            description="Disabled charge",
        )

    assert not LedgerEntry.objects.exists()


def test_top_level_flight_mutations_check_disabled_flag_before_inputs(members):
    _member, actor = members
    SiteConfiguration.objects.update(billing_app_enabled=False)

    with pytest.raises(BillingDisabledError):
        post_flight_charges(flight=None, actor=actor, allocations=[])
    with pytest.raises(BillingDisabledError):
        correct_flight_charges(
            flight=None,
            actor=actor,
            allocations=[],
            effective_date=date.today(),
            reason="Disabled correction",
        )


def test_reversal_is_rejected_after_billing_is_disabled(members):
    member, actor = members
    entry = post_charge(
        member=member,
        actor=actor,
        amount="10.00",
        effective_date=date.today(),
        description="Existing charge",
    )
    SiteConfiguration.objects.update(billing_app_enabled=False)

    with pytest.raises(BillingDisabledError):
        reverse_entry(
            entry=entry,
            actor=actor,
            effective_date=date.today(),
            reason="Disabled reversal",
        )

    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.REVERSAL).exists()
