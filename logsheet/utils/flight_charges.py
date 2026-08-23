from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.01")


def split_even(total_cost):
    """Split a monetary amount evenly and assign odd-cent remainder to partner."""
    total = Decimal(str(total_cost or Decimal("0.00"))).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    total_cents = int((total * 100).to_integral_value(rounding=ROUND_HALF_UP))
    pilot_cents = total_cents // 2
    partner_cents = total_cents - pilot_cents
    return (
        Decimal(pilot_cents).scaleb(-2),
        Decimal(partner_cents).scaleb(-2),
    )


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

    # Keep the calculated amount unrounded until allocation can distribute any
    # fractional cent deterministically between members.
    cost = flight.rental_cost_calculated
    if cost is None:
        return None
    if flight.glider and flight.glider.max_rental_rate is not None:
        cost = min(cost, Decimal(str(flight.glider.max_rental_rate)))
    return cost


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
            pilot_tow, partner_tow = split_even(tow)
            pilot_rental, partner_rental = split_even(rental)
            pilot_instruction, partner_instruction = split_even(instruction)
            allocations[pilot] = {
                "tow": pilot_tow,
                "rental": pilot_rental,
                "instruction": pilot_instruction,
            }
            allocations[partner] = {
                "tow": partner_tow,
                "rental": partner_rental,
                "instruction": partner_instruction,
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
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )


def get_billing_allocations(flight, allocation_version=1):
    """Return the frozen member allocation input consumed by Billing."""
    if flight.commercial_ride or (flight.guest_pilot_name or "").strip():
        return []
    allocations = split_flight_costs(
        flight.pilot,
        flight.split_with,
        flight.split_type,
        flight.tow_cost_actual,
        flight.rental_cost_actual,
        flight.instruction_fee_actual,
    )
    result = []
    for member, components in allocations.items():
        tow = quantize_currency(components["tow"])
        rental = quantize_currency(components["rental"])
        instruction = quantize_currency(components["instruction"])
        total = quantize_currency(tow + rental + instruction)
        if total <= Decimal("0.00"):
            continue
        result.append(
            {
                "member": member,
                "tow": tow,
                "rental": rental,
                "instruction": instruction,
                "total": total,
                "allocation_rule": flight.split_type or "full",
                "allocation_version": allocation_version,
                "source_key": (
                    f"flight:{flight.pk}:member:{member.pk}:v{allocation_version}"
                ),
                "allocation_snapshot": {
                    "split_type": flight.split_type,
                    "pilot_id": flight.pilot_id,
                    "split_with_id": flight.split_with_id,
                },
            }
        )
    return result
