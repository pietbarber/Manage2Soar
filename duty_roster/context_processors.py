"""
Context processors for duty_roster app.

Provides global template context for instructor-related notifications.
"""

from datetime import date


def instructor_pending_requests(request):
    """
    Add pending instruction request count to template context for instructors.

    Returns a count of pending requests for days where the current user
    is the assigned instructor or surge instructor.
    """
    if not request.user.is_authenticated:
        return {"instructor_pending_count": 0}

    # Check if user is an instructor
    if not getattr(request.user, "instructor", False):
        return {"instructor_pending_count": 0}

    # Import here to avoid circular imports
    from django.db import models

    from duty_roster.models import DutyAssignment, InstructionSlot

    today = date.today()

    # Get assignments where this user is instructor or surge instructor
    my_assignments = DutyAssignment.objects.filter(
        date__gte=today,
    ).filter(
        models.Q(instructor=request.user) | models.Q(surge_instructor=request.user)
    )

    # Count pending instruction slots
    pending_count = (
        InstructionSlot.objects.filter(
            assignment__in=my_assignments,
            instructor_response="pending",
        )
        .exclude(status="cancelled")
        .count()
    )

    return {"instructor_pending_count": pending_count}
