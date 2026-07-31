from urllib.parse import urlparse

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from members.account_emails import send_account_setup_email
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
@override_settings(
    DEFAULT_FROM_EMAIL="Club Admin <admin@testclub.example>",
    EMAIL_DEV_MODE=True,
    EMAIL_DEV_MODE_REDIRECT_TO="developer@example.com",
)
def test_account_setup_email_contains_valid_canonical_password_token():
    config = SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_abbreviation="TSC",
        domain_name="testclub.example",
        canonical_url="https://members.testclub.example",
    )
    member = Member.objects.create_user(
        username="newpilot",
        email="newpilot@example.com",
        first_name="New",
        last_name="Pilot",
        membership_status="",
        is_active=False,
    )
    member.set_unusable_password()
    member.save(update_fields=["password"])

    send_account_setup_email(member)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["developer@example.com"]
    assert message.from_email == "noreply@testclub.example"
    assert message.alternatives[0][1] == "text/html"
    assert config.club_name in message.body
    assert member.username in message.body

    setup_url = next(
        line for line in message.body.splitlines() if line.startswith("https://")
    )
    parsed_path = urlparse(setup_url).path.strip("/").split("/")
    _, uidb64, token = parsed_path

    assert setup_url.startswith("https://members.testclub.example/reset/")
    assert force_str(urlsafe_base64_decode(uidb64)) == str(member.pk)
    assert default_token_generator.check_token(member, token)

    member.set_password("a-new-secure-password")
    member.save(update_fields=["password"])
    assert not default_token_generator.check_token(member, token)


@pytest.mark.django_db
def test_account_setup_email_requires_saved_member_with_email():
    unsaved_member = Member(username="unsaved", email="unsaved@example.com")
    with pytest.raises(ValueError, match="saved"):
        send_account_setup_email(unsaved_member)

    member_without_email = Member.objects.create_user(username="noemail", email="")
    with pytest.raises(ValueError, match="email address"):
        send_account_setup_email(member_without_email)
