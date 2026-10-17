import re
import smtplib
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import signing
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from social_core.pipeline.user import user_details

from members.admin import CustomMemberChangeForm
from members.forms import PasswordResetConfirmForm
from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from members.views import _email_change_password_fingerprint, request_email_change
from siteconfig.models import (
    MembershipStatus,
    SiteConfiguration,
    default_member_profile_field_policies,
)
from utils.email import DevModeEmailMultiAlternatives


def configure_email_changes():
    MembershipStatus.objects.create(name="Email Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    policies = default_member_profile_field_policies()
    policies["email"] = "direct"
    return SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example",
        club_abbreviation="TEST",
        member_profile_field_policies=policies,
    )


def make_email_token(member, email):
    if member.pending_email_requested_at is None:
        member.pending_email_requested_at = timezone.now()
        member.save(update_fields=["pending_email_requested_at"])
    return signing.dumps(
        {
            "member_id": member.pk,
            "email": email,
            "requested_at": member.pending_email_requested_at.isoformat(),
            "current_email": member.email,
            "password_fingerprint": _email_change_password_fingerprint(member),
        },
        salt="members.email-change",
    )


def set_pending_email(member, email):
    requested_at = timezone.now()
    if (
        member.pending_email_requested_at
        and requested_at <= member.pending_email_requested_at
    ):
        requested_at = member.pending_email_requested_at + timedelta(microseconds=1)
    member.pending_email = email
    member.pending_email_requested_at = requested_at
    member.save(update_fields=["pending_email", "pending_email_requested_at"])
    return make_email_token(member, email)


@pytest.mark.django_db
def test_member_profile_shows_direct_email_and_password_controls(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="profile_email_controls",
        email="current@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "pending@example.com"
    member.save(update_fields=["pending_email"])
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert reverse("members:request_email_change").encode() in response.content
    assert reverse("members:set_password").encode() in response.content
    assert b"pending@example.com" in response.content
    assert b'name="username"' not in response.content
    assert b'aria-labelledby="emailSettingsModalLabel"' in response.content


@pytest.mark.django_db
def test_member_profile_hides_account_controls_when_disabled(client):
    config = configure_email_changes()
    policies = config.member_profile_field_policies
    policies["email"] = "disabled"
    policies["password"] = "disabled"
    config.member_profile_field_policies = policies
    config.save(update_fields=["member_profile_field_policies"])
    member = Member.objects.create_user(
        username="profile_email_controls_disabled",
        email="current@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert reverse("members:request_email_change").encode() not in response.content
    assert reverse("members:set_password").encode() not in response.content


@pytest.mark.django_db
def test_email_change_request_stores_pending_email_and_sends_confirmation(
    client, mailoutbox, django_capture_on_commit_callbacks
):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_request",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("members:request_email_change"), {"email": "New@Example.com"}
        )

    assert response.status_code == 302
    assert response.url == reverse("members:email_change_requested")
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"
    assert member.pending_email_requested_at is not None
    assert mailoutbox[0].to == ["new@example.com"]
    assert "/members/email/confirm/" in mailoutbox[0].body
    assert mailoutbox[0].alternatives[0][1] == "text/html"
    assert "/members/email/confirm/" in mailoutbox[0].alternatives[0][0]
    assert mailoutbox[1].to == ["old@example.com"]
    assert mailoutbox[1].alternatives[0][1] == "text/html"
    assert b"Security Notice" in mailoutbox[1].alternatives[0][0].encode()


@pytest.mark.django_db
def test_email_change_request_uses_locked_member_state(
    mailoutbox, django_capture_on_commit_callbacks
):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_request_stale_state",
        email="old@example.com",
        membership_status="Email Active",
    )
    stale_member = Member.objects.get(pk=member.pk)
    member.email = "confirmed@example.com"
    member.save(update_fields=["email"])

    request = RequestFactory().post(
        reverse("members:request_email_change"), {"email": "new@example.com"}
    )
    request.user = stale_member
    SessionMiddleware(lambda req: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)

    with django_capture_on_commit_callbacks(execute=True):
        response = request_email_change(request)

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.pending_email == "new@example.com"
    confirmation_token = re.search(
        r"/members/email/confirm/([A-Za-z0-9_.:-]+)", mailoutbox[0].body
    ).group(1)
    token_data = signing.loads(confirmation_token, salt="members.email-change")
    assert token_data["current_email"] == "confirmed@example.com"
    assert token_data["password_fingerprint"] == _email_change_password_fingerprint(
        member
    )
    assert mailoutbox[1].to == ["confirmed@example.com"]


@pytest.mark.django_db
def test_email_confirmation_delivery_failure_sends_security_notice_and_reports_error(
    client, mailoutbox, django_capture_on_commit_callbacks
):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_delivery_failure",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)
    real_send = DevModeEmailMultiAlternatives.send

    def fail_confirmation_send(message, *args, **kwargs):
        if message.subject.startswith("Confirm your"):
            raise smtplib.SMTPRecipientsRefused(
                {"new@example.com": (550, b"Mailbox unavailable")}
            )
        return real_send(message, *args, **kwargs)

    with (
        patch.object(
            DevModeEmailMultiAlternatives,
            "send",
            autospec=True,
            side_effect=fail_confirmation_send,
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client.post(
            reverse("members:request_email_change"), {"email": "new@example.com"}
        )

    assert response.status_code == 503
    assert b"Email Change Not Completed" in response.content
    assert b"couldn't send the confirmation email" in response.content
    assert b"A confirmation link was sent" not in response.content
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["old@example.com"]
    assert mailoutbox[0].subject == "Manage2Soar email change requested"


@pytest.mark.django_db
def test_email_change_request_rejects_kiosk_session(client, mailoutbox):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_kiosk",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)
    session = client.session
    session["is_kiosk_authenticated"] = True
    session.save()

    response = client.post(
        reverse("members:request_email_change"), {"email": "new@example.com"}
    )

    assert response.status_code == 403
    member.refresh_from_db()
    assert member.pending_email == ""
    assert not mailoutbox


@pytest.mark.django_db
def test_email_change_request_rejects_email_beyond_model_length(client, mailoutbox):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_too_long",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)
    overlong_email = (
        "a" * 60 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com"
    )
    assert len(overlong_email) > 254

    response = client.post(
        reverse("members:request_email_change"), {"email": overlong_email}
    )

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])
    member.refresh_from_db()
    assert member.pending_email == ""
    assert not mailoutbox


@pytest.mark.django_db
def test_email_change_request_uses_canonical_url_in_confirmation(
    client, mailoutbox, django_capture_on_commit_callbacks
):
    config = configure_email_changes()
    config.canonical_url = "https://canonical.example.org"
    config.save(update_fields=["canonical_url"])
    member = Member.objects.create_user(
        username="email_canonical",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("members:request_email_change"), {"email": "new@example.com"}
        )

    assert response.status_code == 302
    expected_link = "https://canonical.example.org/members/email/confirm/"
    assert expected_link in mailoutbox[0].body
    assert expected_link in mailoutbox[0].alternatives[0][0]
    assert "testserver/members/email/confirm/" not in mailoutbox[0].body


@pytest.mark.django_db
def test_email_change_confirmation_uses_configured_domain_on_local_servers(
    client, mailoutbox, settings, django_capture_on_commit_callbacks
):
    configure_email_changes()
    settings.SITE_URL = ""
    member = Member.objects.create_user(
        username="email_local_host",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("members:request_email_change"), {"email": "new@example.com"}
        )

    assert response.status_code == 302
    assert "http://localhost:8001/members/email/confirm/" in mailoutbox[0].body


@pytest.mark.django_db
def test_email_change_requested_shows_pending_email(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_requested",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    client.force_login(member)

    response = client.get(reverse("members:email_change_requested"))

    assert response.status_code == 200
    assert b"Check Your Email" in response.content
    assert b"new@example.com" in response.content
    assert b"24 hours" in response.content
    assert b"Back to My Profile" in response.content


@pytest.mark.django_db
def test_email_change_requested_rejects_kiosk_session(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_requested_kiosk",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    client.force_login(member)
    session = client.session
    session["is_kiosk_authenticated"] = True
    session.save()

    response = client.get(reverse("members:email_change_requested"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_email_change_requested_without_pending_email_returns_to_member_profile(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_requested_without_pending",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.get(reverse("members:email_change_requested"))

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])


@pytest.mark.django_db
def test_invalid_email_change_request_returns_to_member_profile(client, mailoutbox):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_invalid_request",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.post(
        reverse("members:request_email_change"), {"email": "invalid"}
    )

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])
    assert not mailoutbox


@pytest.mark.django_db
def test_same_email_change_request_returns_to_member_profile(client, mailoutbox):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_same_request",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.post(
        reverse("members:request_email_change"), {"email": "old@example.com"}
    )

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])
    assert not mailoutbox


@pytest.mark.django_db
def test_email_confirmation_get_does_not_change_email():
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_get", email="old@example.com", membership_status="Email Active"
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    response = Client().get(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"


@pytest.mark.django_db
def test_email_confirmation_post_requires_csrf():
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_csrf", email="old@example.com", membership_status="Email Active"
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    response = Client(enforce_csrf_checks=True).post(
        reverse("members:confirm_email_change", args=[token])
    )

    assert response.status_code == 403
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"


@pytest.mark.django_db
def test_email_confirmation_post_changes_email(
    mailoutbox, django_capture_on_commit_callbacks
):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_post", email="old@example.com", membership_status="Email Active"
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    with django_capture_on_commit_callbacks(execute=True):
        response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    assert response["Location"] == reverse("members:member_view", args=[member.pk])
    member.refresh_from_db()
    assert member.email == "new@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None
    assert mailoutbox[0].subject == "Your Manage2Soar email address changed"
    assert mailoutbox[0].to == ["old@example.com"]
    assert "new@example.com" in mailoutbox[0].body
    assert mailoutbox[0].alternatives[0][1] == "text/html"
    assert "new@example.com" in mailoutbox[0].alternatives[0][0]

    class GoogleLoginStrategy:
        storage = object()

        @staticmethod
        def setting(name, default=None, **kwargs):
            return getattr(settings, f"SOCIAL_AUTH_{name}", default)

    assert "email" in settings.SOCIAL_AUTH_PROTECTED_USER_FIELDS
    user_details(
        GoogleLoginStrategy(),
        {"email": "old@example.com"},
        backend="google-oauth2",
        user=member,
    )
    member.refresh_from_db()
    assert member.email == "new@example.com"


@pytest.mark.django_db
def test_email_confirmation_rejects_superseded_token_after_address_is_requested_again():
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_superseded",
        email="old@example.com",
        membership_status="Email Active",
    )
    old_token = set_pending_email(member, "reused@example.com")
    set_pending_email(member, "intermediate@example.com")
    current_token = set_pending_email(member, "reused@example.com")
    client = Client()

    assert (
        client.get(
            reverse("members:confirm_email_change", args=[old_token])
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("members:confirm_email_change", args=[old_token])
        ).status_code
        == 403
    )
    response = client.post(
        reverse("members:confirm_email_change", args=[current_token])
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.email == "reused@example.com"


@pytest.mark.django_db
def test_password_reset_invalidates_pending_email_confirmation(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_reset_password",
        email="old@example.com",
        password="old-password-123",
        membership_status="Email Active",
    )
    token = set_pending_email(member, "pending@example.com")

    uid = urlsafe_base64_encode(force_bytes(member.pk))
    reset_token = default_token_generator.make_token(member)
    reset_url = reverse(
        "password_reset_confirm", kwargs={"uidb64": uid, "token": reset_token}
    )
    reset_response = client.get(reset_url, follow=True)
    assert reset_response.status_code == 200
    password_form_url = reset_response.redirect_chain[-1][0]

    response = client.post(
        password_form_url,
        {
            "new_password1": "A-new-strong-password-123!",
            "new_password2": "A-new-strong-password-123!",
        },
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.check_password("A-new-strong-password-123!")
    assert (
        client.post(reverse("members:confirm_email_change", args=[token])).status_code
        == 403
    )
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "pending@example.com"


@pytest.mark.django_db
def test_password_reset_does_not_overwrite_concurrent_email_change(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_reset_race",
        email="old@example.com",
        password="Initial-password-123!",
        membership_status="Email Active",
    )
    member.pending_email = "pending@example.com"
    member.pending_email_requested_at = timezone.now()
    member.save(update_fields=["pending_email", "pending_email_requested_at"])

    uid = urlsafe_base64_encode(force_bytes(member.pk))
    reset_token = default_token_generator.make_token(member)
    reset_url = reverse(
        "password_reset_confirm", kwargs={"uidb64": uid, "token": reset_token}
    )
    reset_response = client.get(reset_url, follow=True)
    assert reset_response.status_code == 200
    password_form_url = reset_response.redirect_chain[-1][0]

    original_save = PasswordResetConfirmForm.save

    def confirm_email_before_password_save(form, commit=True):
        Member.objects.filter(pk=form.user.pk).update(
            email="confirmed@example.com",
            pending_email="",
            pending_email_requested_at=None,
        )
        return original_save(form, commit=commit)

    with patch.object(
        PasswordResetConfirmForm, "save", confirm_email_before_password_save
    ):
        response = client.post(
            password_form_url,
            {
                "new_password1": "A-new-strong-password-123!",
                "new_password2": "A-new-strong-password-123!",
            },
        )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.check_password("A-new-strong-password-123!")
    assert member.email == "confirmed@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None


@pytest.mark.django_db
def test_admin_email_change_invalidates_pending_email_confirmation(client):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_admin_change",
        email="old@example.com",
        membership_status="Email Active",
    )
    token = set_pending_email(member, "pending@example.com")
    form = CustomMemberChangeForm(
        data={
            "username": member.username,
            "email": "admin-updated@example.com",
            "first_name": member.first_name,
            "last_name": member.last_name,
            "membership_status": member.membership_status,
            "instructor": member.instructor,
            "towpilot": member.towpilot,
            "contact_visibility_email": "inherit",
            "contact_visibility_phone": "inherit",
            "contact_visibility_address": "inherit",
        },
        instance=member,
    )

    assert form.is_valid(), form.errors
    form.save()

    assert (
        client.post(reverse("members:confirm_email_change", args=[token])).status_code
        == 403
    )
    member.refresh_from_db()
    assert member.email == "admin-updated@example.com"
    assert member.pending_email == "pending@example.com"


@pytest.mark.django_db
def test_email_confirmation_rejects_consumed_token_after_address_is_requested_again():
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_consumed",
        email="old@example.com",
        membership_status="Email Active",
    )
    client = Client()
    consumed_token = set_pending_email(member, "reused@example.com")

    assert (
        client.post(
            reverse("members:confirm_email_change", args=[consumed_token])
        ).status_code
        == 302
    )
    member.refresh_from_db()
    intermediate_token = set_pending_email(member, "intermediate@example.com")
    assert (
        client.post(
            reverse("members:confirm_email_change", args=[intermediate_token])
        ).status_code
        == 302
    )
    member.refresh_from_db()
    current_token = set_pending_email(member, "reused@example.com")

    assert (
        client.post(
            reverse("members:confirm_email_change", args=[consumed_token])
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("members:confirm_email_change", args=[current_token])
        ).status_code
        == 302
    )
    member.refresh_from_db()
    assert member.email == "reused@example.com"


@pytest.mark.django_db
def test_email_change_request_allows_an_email_used_by_another_member(
    client, mailoutbox
):
    configure_email_changes()
    existing = Member.objects.create_user(
        username="existing_shared_email",
        email="shared@example.com",
        membership_status="Email Active",
    )
    member = Member.objects.create_user(
        username="email_shared",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.post(
        reverse("members:request_email_change"), {"email": existing.email}
    )

    assert response.status_code == 302
    assert response.url == reverse("members:email_change_requested")
    member.refresh_from_db()
    assert member.pending_email == existing.email
    assert mailoutbox[0].to == [existing.email]


@pytest.mark.django_db
def test_members_can_share_email_addresses_case_insensitively():
    configure_email_changes()
    Member.objects.create_user(
        username="case_email_existing",
        email="CaseEmail@example.com",
        membership_status="Email Active",
    )

    Member.objects.create_user(
        username="case_email_duplicate",
        email="caseemail@EXAMPLE.com",
        membership_status="Email Active",
    )

    assert Member.objects.filter(email__iexact="caseemail@example.com").count() == 2


@pytest.mark.django_db
def test_email_confirmation_allows_an_address_used_by_another_member(
    mailoutbox, django_capture_on_commit_callbacks
):
    configure_email_changes()
    existing = Member.objects.create_user(
        username="existing_confirmed_email",
        email="shared@example.com",
        membership_status="Email Active",
    )
    member = Member.objects.create_user(
        username="email_confirm_conflict",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = existing.email
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    with django_capture_on_commit_callbacks(execute=True):
        response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    assert response["Location"] == reverse("members:member_view", args=[member.pk])
    member.refresh_from_db()
    assert member.email == existing.email
    assert member.pending_email == ""
    assert mailoutbox[0].to == ["old@example.com"]


@pytest.mark.django_db
@pytest.mark.parametrize("token_suffix", ["tampered", "expired"])
def test_invalid_email_confirmation_does_not_change_email(token_suffix, monkeypatch):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_invalid",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)
    if token_suffix == "tampered":
        token += "tampered"
    else:
        monkeypatch.setattr("members.views.EMAIL_CHANGE_TOKEN_MAX_AGE", -1)

    response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 403
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"


@pytest.mark.django_db
def test_email_confirmation_rechecks_current_policy():
    config = configure_email_changes()
    member = Member.objects.create_user(
        username="email_disabled",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)
    policies = config.member_profile_field_policies
    policies["email"] = "disabled"
    config.member_profile_field_policies = policies
    config.save(update_fields=["member_profile_field_policies"])

    response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 403
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"
