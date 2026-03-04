from decimal import ROUND_HALF_UP, Decimal


def split_flight_costs(pilot, partner, split_type, tow_cost, rental_cost):
    """Return per-member tow/rental allocations for a flight."""
    tow = Decimal(str(tow_cost or Decimal("0.00")))
    rental = Decimal(str(rental_cost or Decimal("0.00")))

    allocations = {}
    primary = pilot or partner

    if split_type:
        if pilot and partner and split_type == "even":
            half_tow = tow / 2
            half_rental = rental / 2
            allocations[pilot] = {"tow": half_tow, "rental": half_rental}
            allocations[partner] = {"tow": half_tow, "rental": half_rental}
        elif pilot and partner and split_type == "tow":
            allocations[pilot] = {"tow": Decimal("0.00"), "rental": rental}
            allocations[partner] = {"tow": tow, "rental": Decimal("0.00")}
        elif pilot and partner and split_type == "rental":
            allocations[pilot] = {"tow": tow, "rental": Decimal("0.00")}
            allocations[partner] = {"tow": Decimal("0.00"), "rental": rental}
        elif pilot and partner and split_type == "full":
            allocations[partner] = {"tow": tow, "rental": rental}
        elif primary:
            allocations[primary] = {"tow": tow, "rental": rental}
    elif pilot:
        allocations[pilot] = {"tow": tow, "rental": rental}

    return allocations


def quantize_currency(value):
    """Quantize a value to cents using billing-standard half-up rounding."""
    return Decimal(str(value or Decimal("0.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
