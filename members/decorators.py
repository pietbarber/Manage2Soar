from functools import wraps

from django.shortcuts import redirect, render

from .utils import is_active_member


def is_kiosk_session(request):
    """
    Check if the current request is from a kiosk session (Issue #364, #486).

    Returns True if the user logged in via kiosk token (has kiosk cookies).
    Kiosk sessions should bypass membership_status checks.
    """
    has_kiosk_token = bool(request.COOKIES.get("kiosk_token"))
    has_kiosk_fingerprint = bool(request.COOKIES.get("kiosk_fingerprint"))
    return has_kiosk_token and has_kiosk_fingerprint


def active_member_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # Allow kiosk sessions regardless of membership_status (Issue #486)
        if is_kiosk_session(request):
            return view_func(request, *args, **kwargs)

        # Use centralized helper which includes superuser handling
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper
