"""Utility functions for badge management and filtering.

This module provides shared helpers for badge leg suppression logic (Issue #560).
When a member earns a parent badge (e.g., FAI Silver), component leg badges
(e.g., Silver Duration, Silver Altitude, Silver Distance) should not be displayed.
"""


def suppress_member_badge_legs(member_badges):
    """Filter badge legs for a single member.

    Given an iterable of MemberBadge instances for one member, suppress (remove)
    any leg badges where the member has also earned the parent badge.

    Args:
        member_badges: Iterable of MemberBadge instances (should include
                      select_related('badge', 'badge__parent_badge') for efficiency)

    Returns:
        List of MemberBadge instances with legs suppressed where parent earned

    Example:
        # In a view:
        member_badges_qs = member.badges.select_related(
            'badge', 'badge__parent_badge'
        ).order_by('badge__order')
        filtered_badges = suppress_member_badge_legs(member_badges_qs)
    """
    # Convert to list to allow multiple iterations
    member_badges_list = list(member_badges)

    # Build set of parent badge IDs that this member has earned
    # (badges with no parent_badge_id are potential parents)
    parent_badge_ids = {
        mb.badge.id for mb in member_badges_list if mb.badge.parent_badge_id is None
    }

    # Filter out leg badges where the parent has been earned
    return [
        mb
        for mb in member_badges_list
        if mb.badge.parent_badge_id not in parent_badge_ids
    ]


def suppress_badge_board_legs(badges):
    """Filter badge legs across all members on badge board.

    Given an iterable of Badge instances (each with a 'filtered_memberbadges'
    attribute containing MemberBadge instances), suppress member entries on
    leg badges if that member has earned the parent badge.

    This function modifies the 'filtered_memberbadges' attribute in-place
    for each badge that has a parent.

    Args:
        badges: Iterable of Badge instances with 'filtered_memberbadges' attribute
               (typically created via Prefetch with to_attr='filtered_memberbadges')

    Returns:
        List of Badge instances with filtered_memberbadges attribute modified in-place

    Example:
        # In badge_board view:
        badges = Badge.objects.select_related('parent_badge').prefetch_related(
            Prefetch('memberbadge_set', queryset=..., to_attr='filtered_memberbadges')
        ).order_by('order')
        badges = suppress_badge_board_legs(badges)
    """
    # Convert to list to allow multiple iterations
    badges_list = list(badges)

    # Build a mapping of parent_badge_id -> set of member_ids who have earned it
    parent_badge_members = {}
    for badge in badges_list:
        if badge.parent_badge_id is None:
            # This badge could be a parent - collect members who have it
            member_ids = {mb.member_id for mb in badge.filtered_memberbadges}
            parent_badge_members[badge.id] = member_ids

    # For each leg badge, filter out members who already have the parent badge
    for badge in badges_list:
        if badge.parent_badge_id and badge.parent_badge_id in parent_badge_members:
            # Filter out members who have earned the parent badge
            parent_member_ids = parent_badge_members[badge.parent_badge_id]
            badge.filtered_memberbadges = [
                mb
                for mb in badge.filtered_memberbadges
                if mb.member_id not in parent_member_ids
            ]

    return badges_list
