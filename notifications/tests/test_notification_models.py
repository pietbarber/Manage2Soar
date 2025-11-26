import pytest
from django.contrib.auth import get_user_model

from notifications.models import Notification

User = get_user_model()


@pytest.mark.django_db
def test_create_notification():
    user = User.objects.create(username="notifyuser")
    Notification.objects.create(user=user, message="Test notification")
    assert Notification.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_mark_notification_read():
    user = User.objects.create(username="notifyuser2")
    n = Notification.objects.create(user=user, message="Test", read=False)
    n.read = True
    n.save()
    n.refresh_from_db()
    assert n.read is True


@pytest.mark.django_db
def test_notification_user_only_sees_own(client, django_user_model):
    user1 = django_user_model.objects.create_user(
        username="u1", password="pw1", membership_status="Full Member"
    )
    user2 = django_user_model.objects.create_user(
        username="u2", password="pw2", membership_status="Full Member"
    )
    Notification.objects.create(user=user1, message="Msg1")
    Notification.objects.create(user=user2, message="Msg2")
    client.force_login(user1)
    response = client.get("/notifications/")
    assert b"Msg1" in response.content
    assert b"Msg2" not in response.content
