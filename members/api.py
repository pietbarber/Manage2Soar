"""
API endpoints for M2S mail server integration.

This module provides a REST-like API for the mail server to fetch
member lists for mailing list aliases and sender whitelists.

Security: All endpoints require API key authentication via X-API-Key header.

Mailing lists are now configurable via the siteconfig MailingList model.
The admin can define arbitrary lists with criteria like "instructor",
"towpilot", "duty_officer", "private_glider_owner", etc.
"""

import secrets
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from siteconfig.models import MailingList, MembershipStatus, SiteConfiguration

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


@require_GET
@csrf_exempt
@api_key_required
def email_lists(request):
    """
    Return email lists for mailing list aliases.

    Response format:
    {
        "lists": {
            "members": ["email1@example.com", "email2@example.com", ...],
            "instructors": ["instructor1@example.com", ...],
            ...
        },
        "whitelist": ["email1@example.com", "email2@example.com", ...],
        "bypass_lists": ["treasurer", "webmaster", ...]
    }

    Lists are now dynamically generated from the MailingList model in siteconfig.
    Each list's subscribers are determined by the criteria configured in the admin.

    The whitelist contains all emails that are allowed to send to mailing lists
    (all active members plus manually whitelisted addresses).

    bypass_lists contains names of lists that should accept mail from anyone
    (still requires SPF PASS, but bypasses sender whitelist).
    """
    # Get all active mailing lists
    mailing_lists = MailingList.objects.filter(is_active=True)

    # Build lists data - each list requires a subscriber query, but this is
    # unavoidable since criteria are dynamic and require different queries
    lists_data = {ml.name: ml.get_subscriber_emails() for ml in mailing_lists}

    # Bypass lists - lists that accept mail from anyone (not just whitelisted senders)
    bypass_lists = [ml.name for ml in mailing_lists if ml.bypass_whitelist]

    # Whitelist = all active member emails + manual whitelist additions
    active_members = get_active_members()
    member_emails = list(active_members.values_list("email", flat=True))

    # Parse manual whitelist from siteconfig (one email per line)
    manual_emails = []
    config = SiteConfiguration.objects.first()
    if config and config.manual_whitelist:
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email

        for line in config.manual_whitelist.strip().split("\n"):
            email = line.strip().lower()
            if email:
                try:
                    validate_email(email)
                    manual_emails.append(email)
                except ValidationError:
                    # Silently skip invalid emails - they won't be included
                    pass

    # Combine and dedupe whitelist
    whitelist = sorted(set(member_emails + manual_emails))

    return JsonResponse(
        {
            "lists": lists_data,
            "whitelist": whitelist,
            "bypass_lists": bypass_lists,
        }
    )
