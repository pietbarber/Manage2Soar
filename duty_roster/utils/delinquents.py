"""
Shared utilities for duty delinquency detection and reporting.

This module provides shared business logic for identifying members who are
actively flying but not performing duty, used by both the web view and the
monthly email command.
"""


def apply_duty_delinquent_exemptions(queryset):
    """
    Apply standard duty delinquency exemptions to a Member queryset.

    Members are exempt from duty delinquency tracking if they:
    - Are the club treasurer (too busy with financial duties)
    - Have "Emeritus Member" status (honorary status, no duty obligations)

    Args:
        queryset: A Django QuerySet of Member objects

    Returns:
        QuerySet with exemptions applied
    """
    return queryset.exclude(treasurer=True).exclude(membership_status="Emeritus Member")
