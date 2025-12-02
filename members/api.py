"""
API endpoints for M2S mail server integration.

This module provides a REST-like API for the mail server to fetch
member lists for mailing list aliases and sender whitelists.

Security: All endpoints require API key authentication via X-API-Key header.
"""

import secrets
from functools import wraps

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from siteconfig.models import MembershipStatus

from .models import Member


def api_key_required(view_func):
    """
    Decorator to require valid API key for mail server access.

    The API key should be sent in the X-API-Key header and must match
    the M2S_MAIL_API_KEY setting.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        expected_key = getattr(settings, "M2S_MAIL_API_KEY", None)

        if not expected_key or not expected_key.strip():
            return JsonResponse(
                {"error": "API key not configured on server"}, status=500
            )

        if not api_key or not secrets.compare_digest(api_key, expected_key):
            return JsonResponse({"error": "Invalid or missing API key"}, status=401)

        return view_func(request, *args, **kwargs)

    return wrapper


def get_active_members():
    """
    Return queryset of active members (those who should receive club emails).

    Active means they have a membership status that is marked as active
    in the SiteConfiguration MembershipStatus table.
    """
    active_statuses = list(MembershipStatus.get_active_statuses())
    return Member.objects.filter(
        membership_status__in=active_statuses, is_active=True
    ).exclude(email="")


@csrf_exempt
@require_GET
@api_key_required
def email_lists(request):
    """
    Return email lists for mailing list aliases.

    Response format:
    {
        "lists": {
            "members": ["email1@example.com", "email2@example.com", ...],
            "instructors": ["instructor1@example.com", ...],
            "towpilots": ["towpilot1@example.com", ...],
            "board": ["secretary@example.com", "treasurer@example.com", ...]
        },
        "whitelist": ["email1@example.com", "email2@example.com", ...]
    }

    The whitelist contains all emails that are allowed to send to mailing lists.
    """
    active_members = get_active_members()

    # Build the lists
    members_list = list(active_members.values_list("email", flat=True))

    instructors_list = list(
        active_members.filter(instructor=True).values_list("email", flat=True)
    )

    towpilots_list = list(
        active_members.filter(towpilot=True).values_list("email", flat=True)
    )

    # Board = secretary, treasurer, and anyone in the "Board" group
    board_members = active_members.filter(Q(secretary=True) | Q(treasurer=True))
    # Also check for members in a "Board" or "Directors" group
    board_members = board_members | active_members.filter(
        groups__name__in=["Board", "Directors", "Board of Directors"]
    )
    board_list = list(board_members.distinct().values_list("email", flat=True))

    # Whitelist = all active member emails (only members can send to lists)
    whitelist = members_list.copy()

    return JsonResponse(
        {
            "lists": {
                "members": members_list,
                "instructors": instructors_list,
                "towpilots": towpilots_list,
                "board": board_list,
            },
            "whitelist": whitelist,
        }
    )
