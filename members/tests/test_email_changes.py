import pytest
from django.core import signing
from django.test import Client
from django.urls import reverse

from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import (
    MembershipStatus,
    SiteConfiguration,
    default_member_profile_field_policies,
)


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
    return signing.dumps(
        {"member_id": member.pk, "email": email},
        salt="members.email-change",
    )


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
    client, mailoutbox
):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_request",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

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

    response = client.post(
        reverse("members:request_email_change"), {"email": overlong_email}
    )

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])
    member.refresh_from_db()
    assert member.pending_email == ""
    assert not mailoutbox


@pytest.mark.django_db
def test_email_change_request_uses_canonical_url_in_confirmation(client, mailoutbox):
    config = configure_email_changes()
    config.canonical_url = "https://canonical.example.org"
    config.save(update_fields=["canonical_url"])
    member = Member.objects.create_user(
        username="email_canonical",
        email="old@example.com",
        membership_status="Email Active",
    )
    client.force_login(member)

    response = client.post(
        reverse("members:request_email_change"), {"email": "new@example.com"}
    )

    assert response.status_code == 302
    expected_link = "https://canonical.example.org/members/email/confirm/"
    assert expected_link in mailoutbox[0].body
    assert expected_link in mailoutbox[0].alternatives[0][0]
    assert "testserver/members/email/confirm/" not in mailoutbox[0].body


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
def test_email_confirmation_post_changes_email(mailoutbox):
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_post", email="old@example.com", membership_status="Email Active"
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    assert response.url == reverse("members:member_view", args=[member.pk])
    member.refresh_from_db()
    assert member.email == "new@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None
    assert mailoutbox[0].subject == "Your Manage2Soar email address changed"
    assert mailoutbox[0].to == ["old@example.com"]
    assert "new@example.com" in mailoutbox[0].body
    assert mailoutbox[0].alternatives[0][1] == "text/html"
    assert "new@example.com" in mailoutbox[0].alternatives[0][0]


@pytest.mark.django_db
def test_email_confirmation_allows_an_email_shared_by_another_member():
    configure_email_changes()
    Member.objects.create_user(
        username="existing_shared_email",
        email="shared@example.com",
        membership_status="Email Active",
    )
    member = Member.objects.create_user(
        username="email_shared",
        email="old@example.com",
        membership_status="Email Active",
    )
    member.pending_email = "shared@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.email == "shared@example.com"


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
