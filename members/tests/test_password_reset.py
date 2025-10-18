import pytest
from django.core import mail
from django.urls import reverse

from members.models import Member


@pytest.mark.django_db
def test_password_reset_sends_email(client):
    Member.objects.create_user(
        username="piet",
        email="piet@example.com",
        password="oldpassword",
        membership_status="Full Member",
    )

    response = client.post(reverse("password_reset"), {"email": "piet@example.com"})

    assert response.status_code == 302  # Redirect to "password_reset_done"
    assert len(mail.outbox) == 1
    assert "Password reset" in mail.outbox[0].subject
    assert "/reset/" in mail.outbox[0].body


@pytest.mark.django_db
def test_password_reset_with_unknown_email_does_not_send(client):
    response = client.post(reverse("password_reset"), {"email": "ghost@example.com"})
    assert response.status_code == 302
    assert len(mail.outbox) == 0  # Silent fail, don't reveal user existence
