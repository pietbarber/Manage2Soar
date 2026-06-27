from decimal import ROUND_HALF_UP, Decimal


def effective_rental_cost(flight):
    """Return effective rental cost with historical snapshot priority.

    For finalized logsheets, prefer locked actual values and only clamp against
    the glider max-rental cap when configured.
    """
    if flight.logsheet.finalized and flight.rental_cost_actual is not None:
        if flight.glider and flight.glider.max_rental_rate is not None:
            max_rate = Decimal(str(flight.glider.max_rental_rate))
            return min(flight.rental_cost_actual, max_rate)
        return flight.rental_cost_actual

    return flight.rental_cost


def split_flight_costs(
    pilot,
    partner,
    split_type,
    tow_cost,
    rental_cost,
    instruction_cost=Decimal("0.00"),
):
    """Return per-member tow/rental/instruction allocations for a flight."""
    tow = Decimal(str(tow_cost or Decimal("0.00")))
    rental = Decimal(str(rental_cost or Decimal("0.00")))
    instruction = Decimal(str(instruction_cost or Decimal("0.00")))

    allocations = {}
    primary = pilot or partner

    if split_type:
        if pilot and partner and split_type == "even":
            half_tow = tow / 2
            half_rental = rental / 2
            half_instruction = instruction / 2
            allocations[pilot] = {
                "tow": half_tow,
                "rental": half_rental,
                "instruction": half_instruction,
            }
            allocations[partner] = {
                "tow": half_tow,
                "rental": half_rental,
                "instruction": half_instruction,
            }
        elif pilot and partner and split_type == "tow":
            allocations[pilot] = {
                "tow": Decimal("0.00"),
                "rental": rental,
                "instruction": instruction,
            }
            allocations[partner] = {
                "tow": tow,
                "rental": Decimal("0.00"),
                "instruction": Decimal("0.00"),
            }
        elif pilot and partner and split_type == "rental":
            allocations[pilot] = {
                "tow": tow,
                "rental": Decimal("0.00"),
                "instruction": instruction,
            }
            allocations[partner] = {
                "tow": Decimal("0.00"),
                "rental": rental,
                "instruction": Decimal("0.00"),
            }
        elif pilot and partner and split_type == "full":
            allocations[partner] = {
                "tow": tow,
                "rental": rental,
                "instruction": instruction,
            }
        elif primary:
            allocations[primary] = {
                "tow": tow,
                "rental": rental,
                "instruction": instruction,
            }
    elif pilot:
        allocations[pilot] = {
            "tow": tow,
            "rental": rental,
            "instruction": instruction,
        }

    return allocations


def quantize_currency(value):
    """Quantize a value to cents using billing-standard half-up rounding."""
    return Decimal(str(value or Decimal("0.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
