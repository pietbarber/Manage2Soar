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
    throttled response is indistinguishable from an ordinary failed
login — no lockout disclosure.
"""

from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.template import loader
from django.views.decorators.cache import add_never_cache_headers

# The generic invalid-credential error, identical to the one Django's
# AuthenticationForm emits for a wrong password, so the throttled response is
# indistinguishable from an ordinary failed login.
_GENERIC_AUTH_ERROR = (
    "Please enter a correct username and password. "
    "Note that both fields may be case-sensitive."
)


class RejectedAuthenticationForm(AuthenticationForm):
    """Validate form fields without retrying authentication after an Axes lockout."""

    def clean(self):
        return self.cleaned_data


def lockout_response(
    request: HttpRequest,
    original_response: Optional[HttpResponseBase] = None,
    credentials: Optional[dict] = None,
) -> HttpResponse:
    """Render the login form with a generic error when axes locks the client out.

    Mirrors the standard ``LoginView`` render so the throttled response is
    indistinguishable from a normal failed login.  Uses a single, consistent
    status code (200) for both HTML and XHR clients, and never reveals whether
    the throttle is IP-based or username-based.

    ``AxesMiddleware`` replaces the view's response *after* the security
    middlewares (``XFrameOptionsMiddleware`` in particular) have already run
    on the original response, so the fresh response produced here would not
    inherit the ``X-Frame-Options`` and never-cache headers that an ordinary
    failed login carries.  ``add_never_cache_headers`` and the explicit
    ``X-Frame-Options`` assignment below close that gap for HTML and XHR,
    so a throttled login form is at least as protected as a
    normal one.
    """
    # A bound form with a no-authentication clean() follows Django's supported
    # validation/error API without retrying credentials after lockout.
    form = RejectedAuthenticationForm(request, data=request.POST)
    form.is_valid()
    form.add_error(None, _GENERIC_AUTH_ERROR)

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

    # LoginView returns HTML with 200 for ordinary failures, including XHR.
    response = HttpResponse(body, status=200)

    # AxesMiddleware replaces the view's response after XFrameOptionsMiddleware
    # has already run on the original response, so this fresh response would
    # not inherit the frame / cache protections an ordinary failed login
    # carries.  Apply them explicitly to the replacement response so a
    # throttled login form is at least as protected as a normal one (Issue
    # #1110 review).
    add_never_cache_headers(response)
    xfo = getattr(settings, "X_FRAME_OPTIONS", "DENY")
    if xfo:
        response["X-Frame-Options"] = str(xfo).upper()

    # Axes replaces the login view response after the normal middleware chain
    # has rendered it. Preserve cookies set by that response, especially the
    # CSRF cookie required for the next login attempt.
    if isinstance(original_response, HttpResponseBase):
        response.cookies.update(original_response.cookies)
        if original_response.get("Vary"):
            response["Vary"] = original_response["Vary"]
    return response
