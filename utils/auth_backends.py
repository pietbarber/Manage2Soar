"""
Django authentication backends for Manage2Soar (Issue #1110).

AxesCompatBackend
-----------------
A thin subclass of :class:`axes.backends.AxesStandaloneBackend` that is
compatible with Django's test-client ``Client.login(username, password)``
shortcut.

Why this is needed
++++++++++++++++++
``AxesStandaloneBackend.authenticate`` requires a ``request`` argument and
raises :class:`axes.exceptions.AxesBackendRequestParameterRequired` (a
``ValueError``) when one is not supplied.  Django's ``Client.login()``
calls ``django.contrib.auth.authenticate(**credentials)`` *without* a
request, and ``authenticate()`` only swallows ``PermissionDenied`` — so the
``ValueError`` propagates and breaks every test that uses
``client.login(username=..., password=...)`` (hundreds across this
codebase).

In production this never happens: the ``/login/`` ``LoginView`` always calls
``authenticate(request, ...)`` with a real request, so the lockout check runs
as intended.

The compatibility shim below simply *passes through* (returns ``None`` so the
next backend — ``ModelBackend`` — handles authentication) when no request is
present.  When a request IS present (normal form login), it delegates to the
axes backend so the throttle still applies.

Google OAuth (and any other ``social_core`` provider) callback
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
``social_django.strategy.DjangoStrategy.authenticate`` injects the
provider's ``social_core`` backend instance into ``kwargs['backend']`` and
passes a real ``request`` into Django's ``authenticate()``.  Without
special-casing, ``AxesStandaloneBackend`` would run
``is_allowed()`` with the *empty* password-credential dict and evaluate the
``username=''`` bucket (which, with
``AXES_LOCKOUT_PARAMETERS=["username", "ip_address"]``, collapses to the IP
bucket).  A valid Google sign-in from a shared-IP client that has burned
through the password-login IP budget would be refused by Axes before
``GoogleOAuth2`` ever runs — exactly the cross-protocol throttling that
Issue #1110 was not designed to do.

This backend therefore short-circuits provider-based authentication calls
(identified by the ``social_core.backends.base.BaseAuth`` ``backend`` kwarg
that ``DjangoStrategy.authenticate`` adds) and lets the next configured
backend (``GoogleOAuth2``) handle the sign-in.  Password-form logins never
pass a ``social_core`` backend through ``authenticate()`` (Django's
``LoginView`` calls ``authenticate(request, username=..., password=...)``
without the kwarg), so the throttle still applies to them.
"""

from __future__ import annotations

from typing import Any, Optional

from axes.backends import AxesStandaloneBackend
from django.http import HttpRequest

try:
    from social_core.backends.base import BaseAuth
except ImportError:  # pragma: no cover - social_django is a hard dep in this repo
    BaseAuth = None  # type: ignore[assignment,misc]


def _is_provider_auth_call(kwargs: dict[str, Any]) -> bool:
    """Return True when Django's ``authenticate()`` was called by a
    ``social_core`` provider (e.g. Google OAuth) rather than by a password
    form.

    ``social_django.strategy.DjangoStrategy.authenticate`` is the only call
    site that adds a ``social_core.backends.base.BaseAuth`` instance under
    the ``'backend'`` kwarg; the project's ``LoginView`` and Django's test
    ``Client.login`` never pass that kwarg.
    """
    if BaseAuth is None:
        return False
    backend = kwargs.get("backend")
    return isinstance(backend, BaseAuth)


class AxesCompatBackend(AxesStandaloneBackend):
    """AxesStandaloneBackend that tolerates a missing request (test client)
    and short-circuits ``social_core`` provider authentication calls so the
    password-login throttle does not block valid Google OAuth sign-ins from
    a password-throttled IP (Issue #1110)."""

    def authenticate(
        self,
        request: Optional[HttpRequest] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: dict,
    ):
        # No request means this is Django's Client.login() test shortcut (or a
        # programmatic authenticate() call).  Let the next backend authenticate;
        # the lockout check is not applicable without a request.
        if request is None:
            return None
        # Provider-based authentication (Google OAuth / any social_core
        # backend): Django's authenticate() was reached via
        # ``social_django.strategy.DjangoStrategy.authenticate`` which
        # injects a ``social_core.backends.base.BaseAuth`` instance into
        # ``kwargs['backend']`` and passes a real request.  Axes' IP-based
        # password-login throttle must not fire here, because (a) a shared-IP
        # client that burned the password budget would otherwise be unable to
        # complete a valid Google sign-in, and (b) the Google OAuth2 callback
        # does not carry a password at all, so the username/IP failure
        # counters were populated by unrelated password failures.
        if _is_provider_auth_call(kwargs):
            return None
        # Normal password-form login: delegate to the axes backend so the
        # throttle still applies.
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )
