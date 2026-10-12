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
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"
    assert member.pending_email_requested_at is not None
    assert "TO: new@example.com" in mailoutbox[0].subject
    assert "/members/email/confirm/" in mailoutbox[0].body
    assert "TO: old@example.com" in mailoutbox[1].subject


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
def test_email_confirmation_post_changes_email():
    configure_email_changes()
    member = Member.objects.create_user(
        username="email_post", email="old@example.com", membership_status="Email Active"
    )
    member.pending_email = "new@example.com"
    member.save(update_fields=["pending_email"])
    token = make_email_token(member, member.pending_email)

    response = Client().post(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.email == "new@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None


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
