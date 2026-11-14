"""Shared fixtures and request helpers for focused login throttle tests."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

UserModel = get_user_model()
LIMIT = 5


@pytest.fixture(autouse=True)
def trusted_test_proxy(settings):
    # Test Client connects from localhost and sends a single-hop XFF chain.
    settings.CLIENT_IP_TRUSTED_PROXIES = ["127.0.0.1/32"]
    settings.CLIENT_IP_TRAILING_PROXIES = 0


def _make_member(username, password="testpass123!"):
    """Create a member that can actually authenticate with a password."""
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


def _reset_axes():
    """Clear Axes attempts and audit logs before a throttle scenario."""
    from axes.models import AccessAttempt, AccessFailureLog, AccessLog

    AccessAttempt.objects.all().delete()
    AccessFailureLog.objects.all().delete()
    AccessLog.objects.all().delete()
