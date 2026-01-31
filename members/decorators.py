from functools import wraps

from django.shortcuts import redirect, render

from .utils import is_active_member
from .utils.kiosk import is_kiosk_session


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


def safety_officer_required(view_func):
    """Decorator that requires the user to be a safety officer.

    Safety officers are members with safety_officer=True or superusers.
    Non-authenticated users are redirected to login.
    Non-safety-officers get a 403 Forbidden response.

    Related: Issue #585 - Safety Officer Interface
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect("login")

        # Superusers always have access
        if user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Check if user is a safety officer
        if hasattr(user, "safety_officer") and user.safety_officer:
            return view_func(request, *args, **kwargs)

        return render(request, "403.html", status=403)

    return wrapper
