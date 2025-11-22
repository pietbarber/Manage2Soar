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

    Args:
        logsheet: Logsheet instance to find towplanes for

    Returns:
        QuerySet: Union of towplanes that need closeout forms
    """
    # Towplanes used for towing
    towing_towplanes = Towplane.objects.filter(flight__logsheet=logsheet).distinct()

    # Towplanes with existing closeouts (manual additions or previous rentals)
    closeout_towplanes = Towplane.objects.filter(
        towplanecloseout__logsheet=logsheet
    ).distinct()

    return towing_towplanes.union(closeout_towplanes)
