from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from billing.models import LedgerEntry
from billing.services import get_balance
from members.models import Member


@pytest.fixture
def member(db):
    return Member.objects.create_user(
        username="billing-view-member", is_active=True, membership_status="Full Member"
    )


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="billing-view-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )


def test_ledger_list_requires_treasurer(client, member, treasurer):
    url = reverse("billing:ledger_list")
    assert client.get(url).status_code == 302

    client.force_login(member)
    assert client.get(url).status_code == 403

    client.force_login(treasurer)
    response = client.get(url)
    assert response.status_code == 200
    assert "Member Billing" in response.content.decode()


def test_ledger_detail_posts_manual_charge_and_shows_audit(client, member, treasurer):
    client.force_login(treasurer)
    url = reverse("billing:ledger_detail", args=[member.pk])
    response = client.post(
        url,
        {
            "kind": "manual_charge",
            "amount": "42.50",
            "effective_date": date.today().isoformat(),
            "description": "Replacement part",
            "reason": "Approved by treasurer",
            "effect": "",
        },
    )

    assert response.status_code == 302
    entry = LedgerEntry.objects.get(ledger__member=member)
    assert entry.member_description == "Replacement part"
    assert entry.internal_note == "Approved by treasurer"
    assert get_balance(member.billing_ledger) == Decimal("42.50")

    detail = client.get(url)
    assert detail.status_code == 200
    assert "Replacement part" in detail.content.decode()
    assert "Approved by treasurer" in detail.content.decode()


def test_reversal_is_post_only_and_redirects_to_member_ledger(
    client, member, treasurer
):
    client.force_login(treasurer)
    detail_url = reverse("billing:ledger_detail", args=[member.pk])
    client.post(
        detail_url,
        {
            "kind": "manual_charge",
            "amount": "10.00",
            "effective_date": date.today().isoformat(),
            "description": "Charge",
            "reason": "Reason",
            "effect": "",
        },
    )
    entry = LedgerEntry.objects.get(ledger__member=member)
    reverse_url = reverse("billing:entry_reverse", args=[entry.pk])

    assert client.get(reverse_url).status_code == 405
    response = client.post(reverse_url, {"reason": "Posted in error"})
    assert response.status_code == 302
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.REVERSAL).count() == 1
    assert get_balance(member.billing_ledger) == Decimal("0.00")
