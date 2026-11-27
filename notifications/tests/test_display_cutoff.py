"""Tests for the 30-day member-facing notification display window (Issue #1168).

Boundary tests freeze time using the repository's established pattern of
monkeypatching ``django.utils.timezone.now`` (see
``instructors/tests/test_pending_spr_reminders.py``) combined with explicit
``created_at`` values relative to the frozen "now".
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from notifications.context_processors import notifications as notifications_context
from notifications.models import Notification

FROZEN_NOW = timezone.make_aware(datetime(2026, 11, 27, 12, 0, 0), UTC)
CUTOFF = FROZEN_NOW - timedelta(days=30)


@pytest.fixture
def frozen_now(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: FROZEN_NOW)
    return FROZEN_NOW


def make_user(django_user_model, username):
    return django_user_model.objects.create_user(
        username=username, password="pw", membership_status="Full Member"
    )


def make_notification(user, created_at, message, dismissed=False):
    return Notification.objects.create(
        user=user,
        message=message,
        created_at=created_at,
        dismissed=dismissed,
    )


def context_for(user):
    request = RequestFactory().get("/")
    request.user = user
    return notifications_context(request)["notifications"]


@pytest.mark.django_db
def test_context_processor_shows_recent_undismissed_newest_first(
    frozen_now, django_user_model
):
    user = make_user(django_user_model, "recent_cp")
    oldest = make_notification(user, FROZEN_NOW - timedelta(days=29), "29 days old")
    middle = make_notification(user, FROZEN_NOW - timedelta(days=10), "10 days old")
    newest = make_notification(user, FROZEN_NOW - timedelta(hours=1), "1 hour old")

    assert context_for(user) == [newest, middle, oldest]


@pytest.mark.django_db
def test_context_processor_includes_notification_exactly_at_cutoff(
    frozen_now, django_user_model
):
    user = make_user(django_user_model, "at_cutoff")
    at_cutoff = make_notification(user, CUTOFF, "Exactly at cutoff")

    assert context_for(user) == [at_cutoff]


@pytest.mark.django_db
def test_context_processor_excludes_notification_beyond_cutoff(
    frozen_now, django_user_model
):
    user = make_user(django_user_model, "beyond")
    make_notification(user, CUTOFF - timedelta(seconds=1), "Just too old")

    assert context_for(user) == []


@pytest.mark.django_db
def test_context_processor_hides_dismissed_notification(frozen_now, django_user_model):
    user = make_user(django_user_model, "dismissed_cp")
    make_notification(
        user, FROZEN_NOW - timedelta(hours=1), "Dismissed message", dismissed=True
    )

    assert context_for(user) == []


@pytest.mark.django_db
def test_notifications_page_shows_recent_and_hides_beyond_cutoff(
    frozen_now, django_user_model, client
):
    user = make_user(django_user_model, "boundary_view")
    make_notification(user, CUTOFF, "AtCutoffMessage")
    make_notification(user, CUTOFF - timedelta(seconds=1), "BeyondCutoffMessage")
    make_notification(user, FROZEN_NOW - timedelta(hours=1), "RecentMessage")

    client.force_login(user)
    response = client.get("/notifications/")

    assert b"AtCutoffMessage" in response.content
    assert b"RecentMessage" in response.content
    assert b"BeyondCutoffMessage" not in response.content


@pytest.mark.django_db
def test_notifications_page_hides_dismissed_notification(
    frozen_now, django_user_model, client
):
    user = make_user(django_user_model, "dismissed_view")
    make_notification(
        user, FROZEN_NOW - timedelta(hours=1), "DismissedMessage", dismissed=True
    )

    client.force_login(user)
    response = client.get("/notifications/")

    assert b"DismissedMessage" not in response.content


@pytest.mark.django_db
def test_user_isolation_in_both_paths(frozen_now, django_user_model, client):
    alice = make_user(django_user_model, "alice")
    bob = make_user(django_user_model, "bob")
    make_notification(bob, FROZEN_NOW - timedelta(hours=1), "BobRecentMessage")
    make_notification(bob, CUTOFF - timedelta(seconds=1), "BobOldMessage")

    # Page-top path (context processor)
    assert context_for(alice) == []

    # Dedicated page path
    client.force_login(alice)
    response = client.get("/notifications/")
    assert b"BobRecentMessage" not in response.content
    assert b"BobOldMessage" not in response.content


@pytest.mark.django_db
def test_empty_state_when_all_expired_or_dismissed(
    frozen_now, django_user_model, client
):
    user = make_user(django_user_model, "empty")
    make_notification(user, CUTOFF - timedelta(days=5), "ExpiredMessage")
    make_notification(
        user, FROZEN_NOW - timedelta(hours=1), "DismissedMessage", dismissed=True
    )

    # Page-top path: the context processor returns an empty list, so the
    # dropdown block rendered by base.html is absent.
    assert context_for(user) == []

    # Dedicated page: normal empty state, and the page-top block (which
    # carries the bell icon) is not rendered either.
    client.force_login(user)
    response = client.get("/notifications/")
    assert b"No notifications." in response.content
    assert b"ExpiredMessage" not in response.content
    assert b"DismissedMessage" not in response.content
    assert "\U0001f514".encode("utf-8") not in response.content


@pytest.mark.django_db
def test_viewing_does_not_delete_or_mutate(frozen_now, django_user_model, client):
    user = make_user(django_user_model, "nomutate")
    expired = make_notification(
        user, CUTOFF - timedelta(days=10), "ExpiredRow", dismissed=False
    )
    recent = make_notification(
        user, FROZEN_NOW - timedelta(days=2), "RecentRow", dismissed=False
    )

    client.force_login(user)
    client.get("/notifications/")

    expired.refresh_from_db()
    recent.refresh_from_db()
    assert Notification.objects.filter(pk=expired.pk).exists()
    assert expired.dismissed is False
    assert expired.read is False
    assert recent.dismissed is False
    assert recent.read is False
