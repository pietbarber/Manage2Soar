from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from billing.services import member_label, post_credit
from billing.templatetags.billing_extras import member_name, money
from members.models import Member


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("1234.5"), "$1,234.50"),
        (0, "$0.00"),
        (Decimal("-730"), "($730.00)"),
        (Decimal("-1234567.891"), "($1,234,567.89)"),
        (Decimal("-0.001"), "$0.00"),
        ("12.345", "$12.35"),
        ("not a number", "not a number"),
    ],
)
def test_money_filter(value, expected):
    assert money(value) == expected


def test_member_label_matches_site_display_name(db):
    member = Member.objects.create_user(
        username="jr-test",
        first_name="Robert",
        last_name="Smith",
        nickname="Bob",
        name_suffix="Jr.",
    )
    assert member_label(member) == "Bob Smith, Jr."
    assert member_name(member) == member_label(member)


def test_member_label_falls_back_to_username(db):
    member = Member.objects.create_user(username="no-name")
    assert member_label(member) == "no-name"


def test_member_ledger_shows_credit_in_parentheses(client, db):
    treasurer = Member.objects.create_user(
        username="money-treasurer",
        treasurer=True,
        is_active=True,
        membership_status="Full Member",
    )
    member = Member.objects.create_user(
        username="money-member",
        first_name="Pat",
        last_name="Pilot",
        nickname="Patty",
        is_active=True,
        membership_status="Full Member",
    )
    post_credit(
        member=member,
        actor=treasurer,
        amount="1250.00",
        effective_date=date.today(),
        description="Payment",
    )
    client.force_login(treasurer)
    html = client.get(
        reverse("billing:ledger_detail", args=[member.pk])
    ).content.decode()
    assert "($1,250.00)" in html
    assert "$-1250.00" not in html
    assert "Patty Pilot" in html
    listing = client.get(reverse("billing:ledger_list")).content.decode()
    assert "($1,250.00)" in listing
    assert "Patty Pilot" in listing
