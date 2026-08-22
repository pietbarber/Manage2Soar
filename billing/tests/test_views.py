import csv
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from billing.models import LedgerEntry
from billing.services import (
    get_balance,
    post_guest_payment_pending,
    post_manual_charge,
    post_opening_balance,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


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


def test_member_cannot_access_or_modify_another_members_ledger(
    client, member, treasurer
):
    other_member = Member.objects.create_user(
        username="other-billing-member", is_active=True, membership_status="Full Member"
    )
    entry = post_manual_charge(
        member=member,
        actor=treasurer,
        amount="10.00",
        effective_date=date.today(),
        description="Charge",
        reason="Test setup",
    )
    client.force_login(other_member)

    assert (
        client.get(reverse("billing:ledger_detail", args=[member.pk])).status_code
        == 403
    )
    assert (
        client.post(
            reverse("billing:ledger_detail", args=[member.pk]),
            {
                "kind": "manual_charge",
                "amount": "25.00",
                "effective_date": date.today().isoformat(),
                "description": "Unauthorized charge",
                "reason": "Unauthorized",
                "effect": "",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("billing:entry_reverse", args=[entry.pk]),
            {"reason": "Unauthorized"},
        ).status_code
        == 403
    )
    entry.refresh_from_db()
    assert not LedgerEntry.objects.filter(reverses=entry).exists()
    assert not LedgerEntry.objects.filter(
        ledger__member=member, member_description="Unauthorized charge"
    ).exists()


def test_treasurer_can_confirm_full_guest_remittance(client, member, treasurer):
    pending = post_guest_payment_pending(
        member=member,
        actor=member,
        amount="75.00",
        effective_date=date.today(),
        guest_name="Guest Pilot",
        payment_method="zelle",
        description="Guest payment pending",
    )
    client.force_login(treasurer)

    response = client.post(
        reverse("billing:guest_payment_remit", args=[pending.pk]),
        {"reference": "ZELLE-75"},
    )

    assert response.status_code == 302
    pending.refresh_from_db()
    assert pending.remittance.amount == Decimal("75.00")
    assert get_balance(member.billing_ledger) == Decimal("0.00")


def test_guest_remittance_uses_club_local_date_not_server_date(
    client, member, treasurer, monkeypatch
):
    """The remittance effective date must come from the club-local date, not
    the server date: when the server runs ahead of the club timezone (e.g.
    UTC server, club behind), server date.today() is a future club date and
    posting would be rejected."""
    from datetime import timedelta

    from siteconfig import timezone_utils

    club_date = date.today()

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return club_date + timedelta(days=1)

    # Club-local operational date stays at the real today...
    monkeypatch.setattr(timezone_utils, "get_club_today", lambda: club_date)
    # ...while the server clock is a full day ahead of it.
    monkeypatch.setattr("billing.views.date", _FakeDate)

    pending = post_guest_payment_pending(
        member=member,
        actor=treasurer,
        amount="75.00",
        effective_date=club_date,
        guest_name="Guest Pilot",
        payment_method="zelle",
        description="Guest payment pending",
    )
    client.force_login(treasurer)

    response = client.post(
        reverse("billing:guest_payment_remit", args=[pending.pk]),
        {"reference": "ZELLE-75"},
    )

    assert response.status_code == 302
    pending.refresh_from_db()
    assert pending.remittance.amount == Decimal("75.00")
    # Posted with the club-local date, not the (future) server date.
    assert pending.remittance.effective_date == club_date
    assert get_balance(member.billing_ledger) == Decimal("0.00")


def test_ledger_list_redirects_when_billing_is_disabled(client, treasurer):
    SiteConfiguration.objects.update(billing_app_enabled=False)
    client.force_login(treasurer)

    response = client.get(reverse("billing:ledger_list"), follow=True)

    assert response.redirect_chain == [("/", 302)]
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Billing is disabled for this site."
    ]


def test_billing_navigation_is_hidden_when_disabled(client, treasurer):
    SiteConfiguration.objects.update(billing_app_enabled=False)
    client.force_login(treasurer)

    response = client.get("/")

    assert reverse("billing:ledger_list") not in response.content.decode()
    assert reverse("logsheet:personal_charges") in response.content.decode()


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


def test_ledger_csv_requires_treasurer_and_sanitizes_cells(client, member, treasurer):
    client.force_login(treasurer)
    detail_url = reverse("billing:ledger_detail", args=[member.pk])
    client.post(
        detail_url,
        {
            "kind": "manual_charge",
            "amount": "10.00",
            "effective_date": date.today().isoformat(),
            "description": "=formula",
            "reason": "@internal-note",
            "effect": "",
        },
    )
    export_url = reverse("billing:ledger_detail_csv", args=[member.pk])

    response = client.get(export_url)
    assert response.status_code == 200
    rows = list(csv.reader(StringIO(response.content.decode())))
    assert rows[0][-1] == "Internal Note"
    assert rows[1][2] == "'=formula"
    assert rows[1][-1] == "'@internal-note"

    client.force_login(member)
    assert client.get(export_url).status_code == 403


def test_opening_balance_override_is_separate_from_routine_entries(
    client, member, treasurer
):
    post_opening_balance(
        member=member,
        actor=treasurer,
        amount="25.00",
        effect=LedgerEntry.Effect.DEBIT,
        effective_date=date.today(),
        description="Imported balance",
        reason="Initial import",
    )
    client.force_login(treasurer)
    detail_url = reverse("billing:ledger_detail", args=[member.pk])

    response = client.get(detail_url)
    content = response.content.decode()
    assert '<option value="opening_balance">' not in content
    assert "Override opening balance" in content

    response = client.post(
        reverse("billing:opening_balance_override", args=[member.pk]),
        {
            "amount": "10.00",
            "effect": LedgerEntry.Effect.CREDIT,
            "effective_date": date.today().isoformat(),
            "description": "Corrected source report",
            "reason": "Corrected import",
        },
    )

    assert response.status_code == 302
    assert get_balance(member.billing_ledger) == Decimal("-10.00")
