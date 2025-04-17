import pytest
from django.urls import reverse
from django.core import mail
from members.models import Member

from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator


@pytest.mark.django_db
def test_password_reset_sends_email(client):
    user = Member.objects.create_user(
        username="piet", email="piet@example.com", password="oldpassword", membership_status="Full Member"
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
