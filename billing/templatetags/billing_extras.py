from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

from billing.services import member_label

register = template.Library()

CENT = Decimal("0.01")


@register.filter
def money(value):
    """Format dollars with thousands separators; negatives go in parentheses.

    ``1234.5`` -> ``$1,234.50`` and ``-730`` -> ``($730.00)``, the accounting
    convention. Exports stay plain signed numbers.
    """
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return value
    text = f"${abs(amount):,.2f}"
    return f"({text})" if amount < 0 else text


@register.filter
def member_name(member):
    return member_label(member)
