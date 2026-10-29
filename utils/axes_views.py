"""
Custom django-axes lockout response for the login view (Issue #1110).

Why a custom ``AXES_LOCKOUT_CALLABLE``?
---------------------------------------
The default axes lockout path responds with a bare ``HTTP 429`` whose body is
either a plain-text message, a JSON blob (for ``XMLHttpRequest``), a redirect,
or an ``AXES_LOCKOUT_TEMPLATE``.  Any of those are visibly *different* from a
normal failed-login response, which lets an attacker fingerprint lockout state
(and therefore which usernames exist) just by comparing responses.

The callable below always re-renders the **real** login template (the same one
a normal login request uses) with the same generic authentication error that
``AuthenticationForm`` shows for a wrong password.  It returns a single
consistent status code for both HTML and XHR requests.  The result is that a
throttled response is byte-for-byte indistinguishable from an ordinary failed
login — no lockout disclosure.
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.forms.forms import NON_FIELD_ERRORS
from django.forms.utils import ErrorDict, ErrorList
from django.http import HttpRequest, HttpResponse, HttpResponseBase, JsonResponse
from django.template import loader

# The generic invalid-credential error, identical to the one Django's
# AuthenticationForm emits for a wrong password, so the throttled response is
# indistinguishable from an ordinary failed login.
_GENERIC_AUTH_ERROR = (
    "Please enter a correct username and password. "
    "Note that both fields may be case-sensitive."
)


def lockout_response(
    request: HttpRequest,
    original_response: Optional[HttpResponseBase] = None,
    credentials: Optional[dict] = None,
) -> HttpResponse:
    """Render the login form with a generic error when axes locks the client out.

    Mirrors the standard ``LoginView`` render so the throttled response is
    indistinguishable from a normal failed login.  Uses a single, consistent
    status code (429) for both HTML and XHR clients, and never reveals whether
    the throttle is IP-based or username-based.
    """
    # Use a display-only (unbound) form so nothing re-authenticates the rejected
    # credentials: binding the POST data would run ``clean()``/``authenticate()``
    # again and add a second, duplicate invalid-login error on top of ours.
    # ``initial`` prefills the username (matching an ordinary failed login)
    # without validating, and ``_errors`` carries exactly one generic non-field
    # error.  The result renders the generic message exactly once.
    form = AuthenticationForm(
        request, initial={"username": request.POST.get("username", "")}
    )
    form._errors = ErrorDict({NON_FIELD_ERRORS: ErrorList([_GENERIC_AUTH_ERROR])})

    context = {
        "form": form,
        "next": request.POST.get("next") or request.GET.get("next", ""),
        "username": request.POST.get("username", ""),
        "google_oauth_configured": bool(
            getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", None)
        ),
    }

    template = loader.get_template("registration/login.html")
    body = template.render(context, request)

    status = 429
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"error": body}, status=status)
    response = HttpResponse(body, status=status)
    response["Content-Type"] = "text/html; charset=utf-8"
    return response
