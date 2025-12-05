"""
Context processors for duty_roster app.

Provides global template context for instructor-related notifications.
"""

from datetime import date

from django.core.cache import cache

# Cache timeout in seconds (5 minutes)
INSTRUCTOR_PENDING_CACHE_TIMEOUT = 300


def get_instructor_pending_count(user):
    """
    Get the pending instruction request count for an instructor.

    Uses caching to avoid database queries on every request.
    Cache is invalidated when InstructionSlot changes (see signals.py).

    Args:
        user: The authenticated user (must be an instructor)

    Returns:
        int: Count of pending instruction requests
    """
    cache_key = f"instructor_pending_count_{user.id}"

    # Try to get from cache
    cached_count = cache.get(cache_key)
    if cached_count is not None:
        return cached_count

    # Import here to avoid circular imports
    from django.db import models

    from duty_roster.models import InstructionSlot

    today = date.today()

    # Count pending instruction slots using a JOIN instead of a subquery
    pending_count = (
        InstructionSlot.objects.filter(
            assignment__date__gte=today,
            instructor_response="pending",
        )
        .filter(
            models.Q(assignment__instructor=user)
            | models.Q(assignment__surge_instructor=user)
        )
        .exclude(status="cancelled")
        .count()
    )

    # Cache the result
    cache.set(cache_key, pending_count, INSTRUCTOR_PENDING_CACHE_TIMEOUT)

    return pending_count


def invalidate_instructor_pending_cache(user_id):
    """
    Invalidate the pending count cache for a specific instructor.

    Called from signals when InstructionSlot changes.

    Args:
        user_id: The ID of the user whose cache should be invalidated
    """
    cache_key = f"instructor_pending_count_{user_id}"
    cache.delete(cache_key)


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

    pending_count = get_instructor_pending_count(request.user)

    return {"instructor_pending_count": pending_count}
