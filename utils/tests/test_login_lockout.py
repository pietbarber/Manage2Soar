"""Focused django-axes regression tests."""

import re

import pytest
from django.test import Client
from django.urls import reverse
from test_login_throttle_support import trusted_test_proxy  # noqa: F401
from test_login_throttle_support import (
    LIMIT,
    _failed_login,
    _make_member,
    _reset_axes,
)


@pytest.mark.django_db
class TestThrottledResponseGeneric:
    """Throttled response must not disclose lockout status."""

    def test_response_does_not_contain_locked(self):
        _make_member("frank")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "frank", ip="10.3.3.3")
        _failed_login(client, "frank", ip="10.3.3.3")  # now locked
        resp = _failed_login(client, "frank", ip="10.3.3.3")
        assert resp.status_code == 200
        body = resp.content.decode().lower()
        # Should NOT contain lockout-specific language
        assert "locked" not in body
        assert "suspended" not in body
        # Should contain the same generic error as a normal failed login
        assert "correct username and password" in body

    def test_normal_failure_and_throttled_failure_same_message(self):
        """Status, body and security headers must match an ordinary failure."""
        _make_member("grace")
        _reset_axes()
        client = Client()
        # Normal failure (not throttled)
        resp_normal = _failed_login(client, "grace", ip="10.4.4.2")
        body_normal = resp_normal.content.decode().lower()

        # Exhaust budget and get throttled
        for _ in range(LIMIT - 1):
            _failed_login(client, "grace", ip="10.4.4.2")
        _failed_login(client, "grace", ip="10.4.4.2")
        resp_throttled = _failed_login(client, "grace", ip="10.4.4.2")
        body_throttled = resp_throttled.content.decode().lower()

        # Both should contain the same generic error text
        assert "correct username and password" in body_normal
        assert "correct username and password" in body_throttled
        assert resp_normal.status_code == resp_throttled.status_code == 200
        assert (
            resp_normal.cookies["csrftoken"].value
            == resp_throttled.cookies["csrftoken"].value
        )

        def stable_body(response):
            body = re.sub(
                rb'name="csrfmiddlewaretoken" value="[^"]+"',
                b'name="csrfmiddlewaretoken" value="<token>"',
                response.content,
            )
            return re.sub(
                rb"const csrfToken = '[^']+'", b"const csrfToken = '<token>'", body
            )

        assert stable_body(resp_normal) == stable_body(resp_throttled)
        for header in ("Content-Type", "Cache-Control", "X-Frame-Options"):
            assert resp_normal.get(header) == resp_throttled.get(header)


@pytest.mark.django_db
class TestLockoutResponseRendering:
    """The throttled response re-renders the real login form with a generic
    error, using a single consistent status for both HTML and XHR clients
    (``AXES_LOCKOUT_CALLABLE``)."""

    @staticmethod
    def _lock(ip):
        _make_member("locky")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "locky", ip=ip)
        _failed_login(client, "locky", ip=ip)
        return _failed_login(client, "locky", ip=ip)

    def test_html_lockout_renders_login_form_with_generic_error(self):
        resp = self._lock("10.13.0.1")
        assert resp.status_code == 200
        assert "text/html" in resp.get("Content-Type", "")
        body = resp.content.decode()
        # The real login form is rendered (not a bare message/redirect).
        assert "<form" in body
        # Same generic error as an ordinary failed login.
        assert "correct username and password" in body
        # No lockout-specific disclosure.
        assert "locked" not in body.lower()
        assert "suspended" not in body.lower()

    def test_lockout_error_renders_exactly_once(self):
        """The throttled login form must show the generic error exactly once.

        Using a bound form (with the POST data) would re-authenticate the
        rejected credentials and stack a second invalid-login error on top of
        the one we add.  The form must be display-only so the error appears
        exactly once — matching an ordinary failed login, which also shows it
        once.
        """
        _make_member("oncey")
        _reset_axes()
        client = Client()
        # A normal (not yet throttled) failed login shows the error exactly once.
        normal = _failed_login(client, "oncey", ip="10.15.0.1")
        assert normal.content.decode().count("correct username and password") == 1

        # Now lock the client and verify the throttled body also shows it once.
        for _ in range(LIMIT - 1):
            _failed_login(client, "oncey", ip="10.15.0.2")
        _failed_login(client, "oncey", ip="10.15.0.2")
        throttled = _failed_login(client, "oncey", ip="10.15.0.2")
        assert throttled.status_code == 200
        assert (
            throttled.content.decode().count("correct username and password") == 1
        ), "The throttled error must appear exactly once (no duplicated message)."

    def test_xhr_lockout_uses_same_status(self):
        _make_member("locky")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "locky", ip="10.14.0.1")
        _failed_login(client, "locky", ip="10.14.0.1")
        resp = client.post(
            reverse("login"),
            {"username": "locky", "password": "wrong"},
            HTTP_X_FORWARDED_FOR="10.14.0.1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        # XHR receives the same HTML response as an ordinary failed login.
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/html")

    def test_xhr_failure_and_lockout_have_same_shape(self):
        _make_member("xhr_user")
        _reset_axes()
        client = Client()

        def attempt():
            return client.post(
                reverse("login"),
                {"username": "xhr_user", "password": "wrong"},
                HTTP_X_FORWARDED_FOR="10.14.0.3",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

        normal = attempt()
        for _ in range(LIMIT):
            attempt()
        locked = attempt()
        assert normal.status_code == locked.status_code == 200
        from axes.models import AccessAttempt

        assert AccessAttempt.objects.filter(
            username="xhr_user",
            ip_address="10.0.0.3",
            failures_since_start__gte=LIMIT,
        ).exists(), "The test must establish a real Axes lockout"
        for header in ("Content-Type", "Cache-Control", "X-Frame-Options"):
            assert normal.get(header) == locked.get(header)

        def without_csrf(response):
            return re.sub(
                rb"(?<=const csrfToken = ')[^']+",
                b"<token>",
                re.sub(
                    rb'(?<=name="csrfmiddlewaretoken" value=")[^"]+',
                    b"<token>",
                    response.content,
                ),
            )

        assert without_csrf(normal) == without_csrf(locked)

    def test_html_lockout_has_frame_and_cache_protection(self):
        """The throttled HTML response must carry the X-Frame-Options and
        never-cache protections that an ordinary failed login carries.

        AxesMiddleware replaces the view's response *after* XFrameOptionsMiddleware
        has run on the original response, so the callable must apply these
        headers itself (Issue #1110 review).
        """
        resp = self._lock("10.16.0.1")
        assert resp.status_code == 200
        # X-Frame-Options present and matches the project default (DENY).
        assert resp["X-Frame-Options"] == "DENY"
        # Never-cache directive (from add_never_cache_headers).
        assert "no-store" in resp["Cache-Control"].lower()

    def test_xhr_lockout_has_frame_and_cache_protection(self):
        """The throttled XHR/JSON response must carry the same protections."""
        _make_member("hdr_user")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "hdr_user", ip="10.17.0.1")
        _failed_login(client, "hdr_user", ip="10.17.0.1")
        resp = client.post(
            reverse("login"),
            {"username": "hdr_user", "password": "wrong"},
            HTTP_X_FORWARDED_FOR="10.17.0.1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert resp.status_code == 200
        assert resp["X-Frame-Options"] == "DENY"
        assert "no-store" in resp["Cache-Control"].lower()
