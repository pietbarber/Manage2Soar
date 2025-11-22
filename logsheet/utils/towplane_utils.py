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
        QuerySet: Towplanes that need closeout forms
    """
    from django.db.models import Q

    return Towplane.objects.filter(
        Q(flight__logsheet=logsheet) | Q(towplanecloseout__logsheet=logsheet)
    ).distinct()
