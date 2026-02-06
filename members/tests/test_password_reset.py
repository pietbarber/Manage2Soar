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


@pytest.mark.django_db
def test_password_reset_uses_canonical_url(client):
    """Test that password reset emails use canonical URL from SiteConfiguration.

    Issue #612: Ensures password reset emails use canonical domain (skylinesoaring.org)
    instead of alternate domains (manage2soar.com), preventing password manager
    domain mismatch issues.
    """
    from siteconfig.models import SiteConfiguration

    # Create or update SiteConfiguration with canonical URL
    config = SiteConfiguration.objects.first()
    if not config:
        config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            club_abbreviation="TSC",
            domain_name="test.example.com",
        )
    config.canonical_url = "https://www.skylinesoaring.org"
    config.save()

    # Create test user
    Member.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="oldpassword",
        membership_status="Full Member",
    )

    # Request password reset
    response = client.post(reverse("password_reset"), {"email": "testuser@example.com"})

    assert response.status_code == 302
    assert len(mail.outbox) == 1

    # Verify that canonical URL is used in the password reset link
    # Check for the complete URL pattern (protocol + domain + path) to avoid
    # "incomplete URL substring sanitization" security warning (CodeQL)
    email_body = mail.outbox[0].body
    assert (
        "https://www.skylinesoaring.org/reset/" in email_body
    ), "Password reset email should use canonical URL from SiteConfiguration"

    # Verify HTML part also uses canonical URL (if present)
    if hasattr(mail.outbox[0], "alternatives") and mail.outbox[0].alternatives:
        html_body = mail.outbox[0].alternatives[0][0]
        assert "https://www.skylinesoaring.org/reset/" in html_body
