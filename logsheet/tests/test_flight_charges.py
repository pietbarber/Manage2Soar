from decimal import Decimal

from logsheet.utils.flight_charges import split_even, split_flight_costs


def test_split_even_assigns_odd_cent_remainder_to_partner():
    pilot_share, partner_share = split_even(Decimal("0.01"))

    assert pilot_share == Decimal("0.00")
    assert partner_share == Decimal("0.01")


def test_split_flight_costs_even_assigns_remainder_to_partner():
    pilot = object()
    partner = object()

    allocations = split_flight_costs(
        pilot=pilot,
        partner=partner,
        split_type="even",
        tow_cost=Decimal("0.01"),
        rental_cost=Decimal("0.03"),
        instruction_cost=Decimal("0.05"),
    )

    assert allocations[pilot] == {
        "tow": Decimal("0.00"),
        "rental": Decimal("0.01"),
        "instruction": Decimal("0.02"),
    }
    assert allocations[partner] == {
        "tow": Decimal("0.01"),
        "rental": Decimal("0.02"),
        "instruction": Decimal("0.03"),
    }
