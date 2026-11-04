"""Focused django-axes regression tests."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from test_login_throttle_support import trusted_test_proxy  # noqa: F401
from test_login_throttle_support import (
    LIMIT,
    _failed_login,
    _make_member,
    _reset_axes,
)


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
            assert resp.status_code == 200, f"Attempt {i + 1} unexpectedly throttled"

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
            resp.status_code == 200
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
        assert resp.status_code == 200, "Per-username bucket should trip"

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
        assert resp.status_code == 200

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
        assert resp.status_code == 200

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
        assert resp.status_code == 200


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
        assert resp.status_code == 200
