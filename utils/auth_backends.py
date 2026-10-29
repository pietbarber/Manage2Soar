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
"""

from __future__ import annotations

from typing import Optional

from axes.backends import AxesStandaloneBackend
from django.http import HttpRequest


class AxesCompatBackend(AxesStandaloneBackend):
    """AxesStandaloneBackend that tolerates a missing request (test client)."""

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
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )
