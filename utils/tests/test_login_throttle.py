"""
Tests for login throttling via django-axes (Issue #1110).

Covers the acceptance criteria:
- Repeated failed logins from one IP are throttled after a bounded number of attempts
- Repeated failed logins against one username (distributed IPs) are throttled
- Successful login is unaffected for legitimate users, including after a throttle window
- Kiosk auto-login (Issue #364) still works
- Throttle counters work across multiple app workers (shared storage)
- Tests covering the throttled and not-yet-throttled paths
- Throttled response does not disclose lockout status (generic error)
- X-Forwarded-For is used as the throttle key (not REMOTE_ADDR)
- Cleanup command deletes old rows

Semantics note (django-axes 8.x):
- ``is_locked`` uses ``get_failures() >= failure_limit`` (>=, not >), so with
  ``AXES_FAILURE_LIMIT=5`` the 5th failed attempt already trips the lockout.
- ``AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]`` means both
  per-IP and per-username are independent buckets (OR semantics).  This is
  exactly the spray protection required by the issue.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

UserModel = get_user_model()


def _make_member(username, password="testpass123!"):
    """Create a member that can actually authenticate with a password.

    ``is_superuser=True`` ensures ``Member.save()`` does not sync
    ``is_active`` to False (which would block Django's ModelBackend from
    authenticating the user).  For throttle tests we don't care about
    superuser status, only that the password matches.
    """
    return UserModel.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        first_name="Test",
        last_name="User",
        is_superuser=True,
        is_staff=True,
    )


def _failed_login(client, username, password="wrongpass", ip="1.2.3.4"):
    """POST a failed login from the given client IP."""
    return client.post(
        reverse("login"),
        {"username": username, "password": password},
        HTTP_X_FORWARDED_FOR=ip,
    )


def _delete_all_attempts():
    """Reset all axes state between tests."""
    from axes.models import AccessAttempt, AccessFailureLog

    AccessAttempt.objects.all().delete()
    AccessFailureLog.objects.all().delete()


def _reset_axes():
    """Reset axes state at the start of a test (idempotent)."""
    _delete_all_attempts()


# AXES_FAILURE_LIMIT in manage2soar/settings.py is 5.
LIMIT = 5


@pytest.mark.django_db
class TestSingleIPThrottle:
    """Repeated failed logins from one IP are throttled.

    To isolate the *per-IP* bucket (and prove it fires independently of the
    per-username bucket), the failures below are distributed across **distinct
    usernames** that all share a single IP.  If the per-IP bucket were not in
    effect, distinct usernames would each carry their own per-username budget
    and none of them would be throttled at LIMIT.
    """

    @staticmethod
    def _ip_users(prefix="ipuser"):
        return [f"{prefix}{i}" for i in range(LIMIT)]

    def test_failures_below_limit_allowed(self):
        """(LIMIT-1) distinct-username failures from one IP should NOT be throttled."""
        _reset_axes()
        for u in self._ip_users()[: LIMIT - 1]:
            _make_member(u)
        client = Client()
        for i, u in enumerate(self._ip_users()[: LIMIT - 1]):
            resp = _failed_login(client, u, ip="10.0.0.1")
            assert resp.status_code == 200, f"Attempt {i+1} unexpectedly throttled"

    def test_failure_at_limit_throttled(self):
        """The LIMIT-th distinct-username failure from one IP is throttled.

        django-axes uses ``>=`` for the lockout check, so the Nth failure
        already exceeds the budget of N-1 prior failures.  Because every
        failure here is a *different* username, the only bucket that can trip
        is the per-IP one.
        """
        _reset_axes()
        for u in self._ip_users():
            _make_member(u)
        client = Client()
        for u in self._ip_users()[: LIMIT - 1]:
            _failed_login(client, u, ip="10.0.0.1")
        resp = _failed_login(client, self._ip_users()[-1], ip="10.0.0.1")
        assert (
            resp.status_code == 429
        ), f"Per-IP bucket should trip on the {LIMIT}th distinct-username failure"

    def test_different_ip_with_different_username_not_throttled(self):
        """A different (username, IP) pair should have its own budget.

        Note: with AXES_LOCKOUT_PARAMETERS=["username", "ip_address"],
        the same username from a different IP IS throttled (spray guard).
        So we use a different username too to verify independent buckets.
        """
        _make_member("alice")
        _make_member("bob")
        _reset_axes()
        client = Client()
        # Exhaust alice's per-IP budget on 10.0.0.1
        for _ in range(LIMIT - 1):
            _failed_login(client, "alice", ip="10.0.0.1")
        _failed_login(client, "alice", ip="10.0.0.1")  # now alice is throttled
        # bob from 10.0.0.2 should be fine (different username AND ip)
        resp = _failed_login(client, "bob", ip="10.0.0.2")
        assert (
            resp.status_code == 200
        ), "Different username + IP should have its own budget"


@pytest.mark.django_db
class TestPerUsernameThrottle:
    """Repeated failed logins against one username from distributed IPs (spray)."""

    def test_username_throttled_across_ips(self):
        """LIMIT failures for username 'bob' from LIMIT different IPs → next IP is throttled.

        This is the spray-protection case: an attacker trying one username
        across many IPs should be stopped by the per-username bucket.
        """
        _make_member("bob")
        _reset_axes()
        client = Client()
        for i in range(LIMIT - 1):
            ip = f"192.168.1.{i + 1}"
            _failed_login(client, "bob", ip=ip)
        # LIMIT-th IP, same username → throttled (per-username bucket)
        resp = _failed_login(client, "bob", ip="192.168.2.1")
        assert resp.status_code == 429, "Per-username bucket should trip"

    def test_different_username_not_throttled(self):
        """A different username should not be affected by another user's throttle."""
        _make_member("bob")
        _make_member("carol")
        _reset_axes()
        client = Client()
        # Exhaust bob's per-username budget
        for i in range(LIMIT - 1):
            ip = f"172.16.1.{i + 1}"
            _failed_login(client, "bob", ip=ip)
        _failed_login(client, "bob", ip="172.16.2.1")  # now bob is throttled
        # Carol from a fresh IP should still work
        resp = _failed_login(client, "carol", ip="172.16.3.1")
        assert (
            resp.status_code == 200
        ), "Different username should have independent budget"


@pytest.mark.django_db
class TestSuccessfulLoginAfterThrottle:
    """Successful login is unaffected for legitimate users."""

    def test_login_works_when_not_throttled(self):
        """A single failed attempt should not block a subsequent successful login."""
        _make_member("dave")
        _reset_axes()
        client = Client()
        _failed_login(client, "dave", password="wrong", ip="10.1.1.1")
        resp = client.post(
            reverse("login"),
            {"username": "dave", "password": "testpass123!"},
            HTTP_X_FORWARDED_FOR="10.1.1.1",
        )
        assert resp.status_code == 302, (
            f"Expected redirect on successful login, got {resp.status_code}. "
            f"Body: {resp.content.decode()[:400]}"
        )

    def test_login_after_cooldown_expires(self):
        """After the cool-off window, the throttle no longer applies."""
        _make_member("eve")
        _reset_axes()
        client = Client()
        # Exhaust the budget
        for _ in range(LIMIT - 1):
            _failed_login(client, "eve", ip="10.2.2.2")
        _failed_login(client, "eve", ip="10.2.2.2")  # now locked

        # Verify throttled
        resp = client.post(
            reverse("login"),
            {"username": "eve", "password": "wrong"},
            HTTP_X_FORWARDED_FOR="10.2.2.2",
        )
        assert resp.status_code == 429

        # Backdate the attempt time past the cool-off window (15 min default)
        from axes.models import AccessAttempt

        old_time = timezone.now() - timedelta(minutes=16)
        AccessAttempt.objects.filter(ip_address="10.2.2.2").update(
            attempt_time=old_time
        )
        # Also backdate the expiration if it exists
        from axes.models import AccessAttemptExpiration

        AccessAttemptExpiration.objects.update(expires_at=old_time)

        # Now login should succeed (throttle expired)
        resp = client.post(
            reverse("login"),
            {"username": "eve", "password": "testpass123!"},
            HTTP_X_FORWARDED_FOR="10.2.2.2",
        )
        assert resp.status_code == 302, (
            f"Expected redirect after cooldown expiry, got {resp.status_code}. "
            f"Body: {resp.content.decode()[:400]}"
        )


@pytest.mark.django_db
class TestThrottledResponseGeneric:
    """Throttled response must not disclose lockout status."""

    def test_429_response_does_not_contain_locked(self):
        _make_member("frank")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "frank", ip="10.3.3.3")
        _failed_login(client, "frank", ip="10.3.3.3")  # now locked
        resp = _failed_login(client, "frank", ip="10.3.3.3")
        assert resp.status_code == 429
        body = resp.content.decode().lower()
        # Should NOT contain lockout-specific language
        assert "locked" not in body
        assert "suspended" not in body
        # Should contain the same generic error as a normal failed login
        assert "correct username and password" in body

    def test_normal_failure_and_throttled_failure_same_message(self):
        """The 429 body should match the 200 failure body (same generic error)."""
        _make_member("grace")
        _reset_axes()
        client = Client()
        # Normal failure (not throttled)
        resp_normal = _failed_login(client, "grace", ip="10.4.4.1")
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


@pytest.mark.django_db
class TestCooldownNotRenewed:
    """A failed attempt made while already locked out must NOT extend the
    cooldown window (``AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT=False``).

    If the cooldown were being renewed, an attacker could keep a victim (or a
    shared-office NAT) locked out indefinitely by retrying.  axes implements
    this by short-circuiting ``user_login_failed`` while locked out, so no new
    attempt record is created and the original attempt_time is preserved.
    """

    def test_failure_during_lockout_does_not_add_record(self):
        _make_member("carl")
        _reset_axes()
        client = Client()
        for _ in range(LIMIT - 1):
            _failed_login(client, "carl", ip="10.11.0.1")
        _failed_login(client, "carl", ip="10.11.0.1")  # now locked

        from axes.models import AccessAttempt

        rows_before = AccessAttempt.objects.filter(ip_address="10.11.0.1").count()
        times_before = list(
            AccessAttempt.objects.filter(ip_address="10.11.0.1").values_list(
                "attempt_time", flat=True
            )
        )

        # A further failed attempt while locked out must be a no-op on the
        # records (cooldown not renewed).
        resp = _failed_login(client, "carl", ip="10.11.0.1")
        assert resp.status_code == 429

        rows_after = AccessAttempt.objects.filter(ip_address="10.11.0.1").count()
        times_after = list(
            AccessAttempt.objects.filter(ip_address="10.11.0.1").values_list(
                "attempt_time", flat=True
            )
        )
        assert rows_before == rows_after, (
            "A failure during lockout should not create a new attempt record "
            "(that would renew the cooldown)."
        )
        assert times_before == times_after, (
            "A failure during lockout should not update the attempt time "
            "(that would extend the cooldown window)."
        )


@pytest.mark.django_db
class TestNoResetOnSuccess:
    """A successful login must NOT wipe prior failure records
    (``AXES_RESET_ON_SUCCESS=False``).

    Preserving the records means a correct password cannot clear an in-flight
    lockout, and the audit trail of prior failures in the window is retained.
    """

    def test_success_keeps_prior_failures(self):
        _make_member("dora")
        _reset_axes()
        client = Client()
        for _ in range(3):
            _failed_login(client, "dora", ip="10.12.0.1")

        from axes.models import AccessAttempt

        rows_before = AccessAttempt.objects.filter(ip_address="10.12.0.1").count()
        assert rows_before >= 1

        # Successful login from the same IP/username.
        resp = client.post(
            reverse("login"),
            {"username": "dora", "password": "testpass123!"},
            HTTP_X_FORWARDED_FOR="10.12.0.1",
        )
        assert resp.status_code == 302, "Successful login should redirect"

        rows_after = AccessAttempt.objects.filter(ip_address="10.12.0.1").count()
        assert rows_after == rows_before, (
            "Successful login should NOT delete prior failure records "
            "(AXES_RESET_ON_SUCCESS is disabled)."
        )


@pytest.mark.django_db
class TestClientIpSelection:
    """``get_client_ip`` must pick the client entry the trusted upstream proxy
    observed, not a client-controlled (spoofable) entry and not the shared
    load-balancer IP.

    Per the GCP external Application Load Balancer docs, the LB appends
    ``<client-ip>, <load-balancer-ip>`` to the right of any client-supplied
    ``X-Forwarded-For`` value:

        XFF: <existing spoofable entries>, <client-ip>, <load-balancer-ip>

    So the trustworthy client entry is the second-from-right entry (default
    ``CLIENT_IP_TRAILING_PROXIES = 1``), while the right-most entry is the
    shared LB address.
    """

    @staticmethod
    def _ip(xff, remote="1.1.1.1"):
        from django.test import RequestFactory

        from utils.ip_utils import get_client_ip

        r = RequestFactory().get("/x")
        if xff is not None:
            r.META["HTTP_X_FORWARDED_FOR"] = xff
        r.META["REMOTE_ADDR"] = remote
        return get_client_ip(r)

    def test_selects_second_from_right_for_gke_header(self):
        """Realistic GKE header: ``<spoof>, <client>, <load-balancer>`` → client."""
        ip = self._ip("8.8.8.8, 203.0.113.5, 198.51.100.99")
        assert ip == "203.0.113.5", (
            "The second-from-right entry is the client the LB observed; the "
            "right-most is the shared LB IP and the left is client-controlled."
        )

    def test_clean_two_entry_header(self):
        """Clean header with no spoofing: ``<client>, <load-balancer>`` → client."""
        assert self._ip("198.51.100.7, 198.51.100.99") == "198.51.100.7"

    def test_single_hop_proxy_falls_back_to_last(self):
        """Single-hop proxy (e.g. single-host nginx) appends only the client,
        so the chain is ``<client>`` and the last entry is correct."""
        assert self._ip("198.51.100.7") == "198.51.100.7"

    def test_no_xff_uses_remote_addr(self):
        """No XFF header (local dev / tests) falls back to REMOTE_ADDR."""
        assert self._ip(None, remote="10.0.0.9") == "10.0.0.9"

    def test_multi_entry_does_not_pick_shared_lb_ip(self):
        """A multi-hop chain must not select the shared (right-most) address."""
        ip = self._ip("1.2.3.4, 5.6.7.8, 9.9.9.9, 10.10.10.10")
        assert ip == "9.9.9.9", (
            "Must select the client entry (second from right), not the shared "
            "load-balancer IP (right-most)."
        )


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
        assert resp.status_code == 429
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
        assert throttled.status_code == 429
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
        # Consistent status for XHR (same 429 as the HTML path).
        assert resp.status_code == 429


@pytest.mark.django_db
class TestSharedStorage:
    """Throttle counters work across multiple app workers (shared storage)."""

    def test_attempts_stored_in_database(self):
        """Failed logins should create AccessAttempt rows in the database."""
        _make_member("heidi")
        _reset_axes()
        client = Client()
        _failed_login(client, "heidi", ip="10.5.5.5")

        from axes.models import AccessAttempt

        attempts = AccessAttempt.objects.filter(ip_address="10.5.5.5")
        assert attempts.count() >= 1

    def test_counters_visible_across_client_instances(self):
        """Two different Django test clients (simulating two workers) should
        share the same throttle state via the database."""
        _make_member("ivan")
        _reset_axes()
        client1 = Client()
        client2 = Client()
        ip = "10.6.6.6"

        # (LIMIT-1) failures from client1
        for _ in range(LIMIT - 1):
            _failed_login(client1, "ivan", ip=ip)

        # 1 more failure from client2 (simulating a different worker)
        _failed_login(client2, "ivan", ip=ip)

        # Next failure from client1 should be throttled
        resp = _failed_login(client1, "ivan", ip=ip)
        assert resp.status_code == 429


@pytest.mark.django_db
class TestXForwardedForThrottleKey:
    """Throttle must key on X-Forwarded-For, not REMOTE_ADDR."""

    def test_uses_xff_not_remote_addr(self):
        """Two different XFF values → independent throttle budgets,
        even though REMOTE_ADDR is the same (simulating the LB)."""
        _make_member("judy")
        _make_member("judy2")
        _reset_axes()
        client = Client()
        ip1 = "203.0.113.1"  # RFC 5737 test range
        ip2 = "203.0.113.2"

        # Exhaust budget for XFF ip1 (use judy)
        for _ in range(LIMIT - 1):
            _failed_login(client, "judy", ip=ip1)
        _failed_login(client, "judy", ip=ip1)  # now judy is throttled

        # judy2 from ip2 should have its own budget (different username + ip)
        resp = _failed_login(client, "judy2", ip=ip2)
        assert (
            resp.status_code == 200
        ), "Different XFF + username should have independent budget"

    def test_same_xff_shares_budget(self):
        """Same XFF value → shared budget (even from different 'workers')."""
        _make_member("mallory")
        _reset_axes()
        client1 = Client()
        client2 = Client()
        ip = "198.51.100.1"

        # (LIMIT-1) from client1
        for _ in range(LIMIT - 1):
            _failed_login(client1, "mallory", ip=ip)
        # 1 from client2
        _failed_login(client2, "mallory", ip=ip)
        # Next from client1 → throttled
        resp = _failed_login(client1, "mallory", ip=ip)
        assert resp.status_code == 429


@pytest.mark.django_db
class TestCleanupCommand:
    """cleanup_login_attempts deletes old rows and preserves recent ones."""

    def test_deletes_old_attempts(self):
        from axes.models import AccessAttempt

        _make_member("oscar")
        _reset_axes()
        client = Client()
        _failed_login(client, "oscar", ip="10.7.7.7")

        # Backdate all attempts to 25 hours ago (past the 24h retention)
        old_time = timezone.now() - timedelta(hours=25)
        AccessAttempt.objects.all().update(attempt_time=old_time)

        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_login_attempts", "--force", stdout=out)

        assert AccessAttempt.objects.filter(ip_address="10.7.7.7").count() == 0

    def test_preserves_recent_attempts(self):
        from axes.models import AccessAttempt

        _make_member("peggy")
        _reset_axes()
        client = Client()
        _failed_login(client, "peggy", ip="10.8.8.8")

        # All attempts are fresh (just created), so cleanup should not delete them
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_login_attempts", "--force", stdout=out)

        assert AccessAttempt.objects.filter(ip_address="10.8.8.8").count() >= 1

    def test_dry_run_does_not_delete(self):
        from axes.models import AccessAttempt

        _make_member("r2d2")
        _reset_axes()
        client = Client()
        _failed_login(client, "r2d2", ip="10.9.9.9")

        old_time = timezone.now() - timedelta(hours=25)
        AccessAttempt.objects.all().update(attempt_time=old_time)

        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_login_attempts", "--force", "--dry-run", stdout=out)

        # Dry run should NOT delete
        assert AccessAttempt.objects.filter(ip_address="10.9.9.9").count() >= 1


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
        assert resp.status_code == 429  # Confirmed throttled

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
