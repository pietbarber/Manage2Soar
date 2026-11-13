from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from .authorization import resolve_authorization
from .utils import is_active_member
from .utils.kiosk import is_kiosk_session
from .utils.permissions import SAFETY_REPORT_PERMISSION


def active_member_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        # Allow kiosk sessions regardless of membership_status (Issue #486)
        if is_kiosk_session(request):
            return view_func(request, *args, **kwargs)

        # Use centralized helper which includes superuser handling
        if not is_active_member(user):
            return render(request, "403.html", status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def non_kiosk_member_required(view_func):
    """Require an active member, but reject kiosk (shared) sessions.

    Kiosk sessions authenticate as a shared Role Account. Credential-recovery
    flows (email address or password changes) must not be usable from them,
    otherwise anyone at the kiosk could take over the shared account.
    """
    member_view = active_member_required(view_func)

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if is_kiosk_session(request):
            return render(request, "403.html", status=403)
        return member_view(request, *args, **kwargs)

    return wrapper


def safety_officer_required(view_func):
    """Decorator that requires the user to be a safety officer.

    Safety officers are active members with the safety-report capability, or
    superusers.
    Also checks for active membership status before role check.
    Non-authenticated users are redirected to login.
    Non-safety-officers get a 403 Forbidden response.

    Related: Issue #585 - Safety Officer Interface
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        decision = resolve_authorization(
            user,
            SAFETY_REPORT_PERMISSION,
            require_active_member=True,
        )
        if decision.allow:
            return view_func(request, *args, **kwargs)

        return render(request, "403.html", status=403)

    return wrapper
