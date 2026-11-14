"""Focused django-axes regression tests."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from test_login_throttle_support import trusted_test_proxy  # noqa: F401
from test_login_throttle_support import (
    _failed_login,
    _make_member,
    _reset_axes,
)


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

    def test_deletes_old_access_logs(self):
        """django-axes 8.x inserts an AccessLog row per successful login
        (AXES_DISABLE_ACCESS_LOG defaults to False).  The cleanup must apply
        the same 24-hour retention to AccessLog, not just to the attempt and
        failure tables (Issue #1110 review)."""
        from axes.models import AccessLog

        _make_member("waldo")
        _reset_axes()

        # Simulate a successful-login audit row created by axes.
        log = AccessLog.objects.create(
            username="waldo",
            ip_address="10.18.0.1",
            user_agent="test-agent",
            http_accept="text/html",
            path_info="/login/",
            session_hash="abc123",
        )

        # Backdate past the 24h retention horizon.
        old_time = timezone.now() - timedelta(hours=25)
        AccessLog.objects.filter(pk=log.pk).update(attempt_time=old_time)

        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_login_attempts", "--force", stdout=out)

        assert AccessLog.objects.filter(ip_address="10.18.0.1").count() == 0

    def test_preserves_recent_access_logs(self):
        """A fresh AccessLog (within the retention window) must be kept."""
        from axes.models import AccessLog

        _make_member("xena")
        _reset_axes()
        AccessLog.objects.create(
            username="xena",
            ip_address="10.19.0.1",
            user_agent="test-agent",
            http_accept="text/html",
            path_info="/login/",
            session_hash="def456",
        )

        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_login_attempts", "--force", stdout=out)

        assert AccessLog.objects.filter(ip_address="10.19.0.1").count() == 1
