"""Focused django-axes regression tests."""

from unittest import mock

import pytest
from django.test import Client
from test_login_throttle_support import trusted_test_proxy  # noqa: F401
from test_login_throttle_support import (
    LIMIT,
    _failed_login,
    _make_member,
    _reset_axes,
)


@pytest.mark.django_db
class TestKioskUnaffected:
    """Kiosk auto-login (Issue #364) is unaffected by login throttling."""

    def test_kiosk_middleware_bypasses_throttle(self):
        """Kiosk authentication happens in middleware before LoginView,
        so axes never sees it.  This test verifies the kiosk middleware
        still authenticates users even after the IP/username has been
        throttled via the login form."""
        from members.models import KioskToken

        member = _make_member("kiosk_user")
        token = KioskToken.objects.create(user=member, name="Test Kiosk")
        token.bind_device("test_fingerprint")

        _reset_axes()
        # Exhaust the login throttle for this username
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "kiosk_user", ip="10.10.10.10")
        _failed_login(client, "kiosk_user", ip="10.10.10.10")  # now locked
        resp = _failed_login(client, "kiosk_user", ip="10.10.10.10")
        assert resp.status_code == 200
        assert resp.wsgi_request.axes_locked_out is True

        # Kiosk middleware should still authenticate via cookies
        # (simulates a kiosk device with valid token + fingerprint)
        kiosk_client = Client()
        kiosk_client.cookies["kiosk_token"] = token.token
        kiosk_client.cookies["kiosk_fingerprint"] = "test_fingerprint"

        # Hit a page that requires authentication — kiosk middleware
        # should auto-login before the request reaches the view
        resp = kiosk_client.get("/members/", follow=True)
        # If kiosk auth works, the user is authenticated (not redirected to login)
        assert resp.wsgi_request.user.is_authenticated


@pytest.mark.django_db
class TestProviderAuthExemptFromThrottle:
    """Password calls must still delegate to Axes; the real social-auth
    strategy bypass is covered in test_provider_auth_integration.py.
    """

    def test_password_login_still_throttled_when_ip_locked(self):
        """A password-form login from a locked IP must still be rejected by axes
        (the exemption above must not weaken the password throttle)."""
        from axes.exceptions import AxesBackendPermissionDenied
        from django.test import RequestFactory

        from utils.auth_backends import AxesCompatBackend

        _make_member("pw_user")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT):
            _failed_login(client, "pw_user", ip="203.0.114.6")

        request = RequestFactory().get("/login/")
        request.META["REMOTE_ADDR"] = "203.0.114.6"

        backend = AxesCompatBackend()
        with pytest.raises(AxesBackendPermissionDenied):
            # No 'backend' kwarg -> password-form path -> axes lockout check
            # runs and the locked IP is denied.
            backend.authenticate(request, username="pw_user", password="wrong")

    def test_password_login_allowed_when_not_locked(self):
        """A password-form login from a non-locked IP must still delegate to the
        axes backend (i.e. be *allowed* by it), proving the exemption only
        applies to the provider path."""
        from django.test import RequestFactory

        import utils.auth_backends as ab

        _make_member("ok_user")
        _reset_axes()
        request = RequestFactory().get("/login/")
        request.META["REMOTE_ADDR"] = "203.0.114.7"

        backend = ab.AxesCompatBackend()
        # Patch the parent's authenticate to prove the password path DELEGATES
        # to axes (rather than short-circuiting) — the parent would then do the
        # real is_allowed() check.
        with mock.patch.object(
            ab.AxesStandaloneBackend, "authenticate", return_value="DELEGATED"
        ) as spied:
            result = backend.authenticate(
                request, username="ok_user", password="testpass123!"
            )
        assert result == "DELEGATED"
        assert spied.called, (
            "Password-form logins must delegate to the axes backend so the "
            "throttle still applies."
        )
