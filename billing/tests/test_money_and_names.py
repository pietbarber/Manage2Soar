from decimal import Decimal

import pytest

from billing.services import member_label
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
