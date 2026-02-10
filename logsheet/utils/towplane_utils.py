"""
Utility functions for towplane operations.
"""

from logsheet.models import Towplane


def get_relevant_towplanes(logsheet):
    """
    Get all towplanes that need closeout forms for this logsheet.

    This includes:
    - Towplanes used for towing (have flights on this logsheet)
    - Towplanes with existing closeouts (manual additions or previous rentals)
    - Self-Launch towplane ONLY if used with club-owned gliders (for Hobbs tracking)

    Excludes:
    - WINCH and OTHER virtual towplanes (never need closeout)
    - SELF when only used with privately-owned gliders

    Args:
        logsheet: Logsheet instance to find towplanes for

    Returns:
        QuerySet: Towplanes that need closeout forms
    """
    from django.db.models import Q

    # Get all towplanes used in flights or with existing closeouts
    towplanes = Towplane.objects.filter(
        Q(flight__logsheet=logsheet) | Q(towplanecloseout__logsheet=logsheet)
    ).distinct()

    # Filter out virtual towplanes that don't need closeout
    result = []
    for towplane in towplanes:
        # Always skip WINCH and OTHER (completely virtual)
        if towplane.n_number.upper() in {"WINCH", "OTHER"}:
            continue

        # For SELF, only include if used with club-owned gliders
        if towplane.n_number.upper() == "SELF":
            # Check if any flight with this towplane used a club-owned glider
            has_club_glider = logsheet.flights.filter(
                towplane=towplane, glider__club_owned=True
            ).exists()
            if not has_club_glider:
                continue

        result.append(towplane)

    return Towplane.objects.filter(pk__in=[tp.pk for tp in result])
