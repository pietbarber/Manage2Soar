"""
Utility functions for towplane operations.
"""

from logsheet.models import Towplane


def get_relevant_towplanes(logsheet):
    """
    Get all towplanes that need closeout forms for this logsheet.

    This includes:
    - Towplanes used for towing (have flights on this logsheet)
    - Towplanes with existing closeouts (manual additions for rentals)
    - Self-Launch towplane ONLY if used with club-owned gliders (for Hobbs tracking)

    Excludes:
    - WINCH and OTHER virtual towplanes (never need closeout)
    - SELF when only used with privately-owned gliders

    Args:
        logsheet: Logsheet instance to find towplanes for

    Returns:
        QuerySet: Towplanes that need closeout forms
    """
    from django.db.models import Exists, OuterRef, Q

    # Build a single optimized query that:
    # 1. Gets towplanes used in flights or with existing closeouts
    # 2. Excludes WINCH and OTHER (never need closeout)
    # 3. For SELF, only include if used with club-owned gliders
    # Subquery: Check if SELF towplane has flights with club-owned gliders
    club_glider_flights = logsheet.flights.filter(
        towplane=OuterRef("pk"), glider__club_owned=True
    )

    # Get all towplanes used in flights or with existing closeouts
    towplanes = Towplane.objects.filter(
        Q(flight__logsheet=logsheet) | Q(towplanecloseout__logsheet=logsheet)
    ).distinct()

    # Exclude WINCH and OTHER (always)
    towplanes = towplanes.exclude(n_number__iregex=r"^(WINCH|OTHER)$")

    # For SELF, only include if used with club-owned gliders
    # Non-virtual towplanes are included automatically
    towplanes = towplanes.filter(
        Q(~Q(n_number__iexact="SELF"))  # Include all non-SELF towplanes
        | Q(n_number__iexact="SELF")
        & Q(Exists(club_glider_flights))  # SELF only with club gliders
    )

    return towplanes
