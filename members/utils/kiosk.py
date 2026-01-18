"""
Kiosk session utilities (Issue #364, #486).

Shared functions for detecting and managing kiosk authentication sessions.
"""


def is_kiosk_session(request):
    """
    Check if the current user was authenticated via kiosk token.

    Returns True if KioskAutoLoginMiddleware authenticated this user via
    kiosk token. Uses session flag set by the middleware, not cookies directly.

    This prevents security issues where stale kiosk cookies could grant access
    when users log in via other methods (OAuth2, Django admin password, etc.).

    Args:
        request: HttpRequest object with session

    Returns:
        bool: True if user authenticated via kiosk, False otherwise

    Security Note:
        Session-based check ensures only actively kiosk-authenticated users
        bypass membership_status checks, not users with leftover cookies from
        previous kiosk sessions.

    Usage:
        In decorators:
            if is_kiosk_session(request):
                # Allow access without membership_status check

        In templates (via template tag):
            {% is_kiosk_session as kiosk_mode %}
            {% if kiosk_mode %}...{% endif %}

    See Also:
        - utils.middleware.KioskAutoLoginMiddleware (sets session flag)
        - members.views_kiosk.kiosk_bind_device (sets session flag on first login)
        - members.decorators.active_member_required (uses this function)
    """
    return request.session.get("is_kiosk_authenticated", False)
