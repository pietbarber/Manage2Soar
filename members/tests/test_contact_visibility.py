from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core import signing
from django.test import Client
from django.urls import reverse

from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from members.utils.permissions import can_view_contact_field, contact_field_visibility
from members.utils.vcard_tools import generate_vcard_qr
from siteconfig.models import MembershipStatus, SiteConfiguration


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "preference", "default", "expected"),
    [
        ("email", {}, True, True),
        ("phone", {}, False, False),
        ("address", {}, True, True),
        ("email", {"email": "share"}, False, True),
        ("phone", {"phone": "share"}, False, True),
        ("address", {"address": "share"}, False, True),
        ("email", {"email": "hide"}, True, False),
        ("phone", {"phone": "hide"}, True, False),
        ("address", {"address": "hide"}, True, False),
    ],
)
def test_contact_visibility_uses_preference_or_club_default(
    field, preference, default, expected
):
    viewer = Member.objects.create_user(username="viewer")
    subject = Member.objects.create_user(
        username="subject", contact_visibility=preference
    )
    config = SimpleNamespace(**{f"share_member_{field}_by_default": default})

    assert can_view_contact_field(viewer, subject, field, config) is expected


@pytest.mark.django_db
def test_contact_visibility_legacy_redaction_and_privileged_bypass():
    viewer = Member.objects.create_user(username="viewer")
    subject = Member.objects.create_user(username="subject", redact_contact=True)
    admin = Member.objects.create_superuser(
        username="admin", email="admin@example.com", password="test-password"
    )
    config = SimpleNamespace(share_member_phone_by_default=True)

    assert not can_view_contact_field(viewer, subject, "phone", config)
    assert can_view_contact_field(subject, subject, "phone", config)
    assert can_view_contact_field(admin, subject, "phone", config)


@pytest.mark.django_db
def test_contact_visibility_reports_effective_source():
    subject = Member.objects.create_user(
        username="subject",
        contact_visibility={"email": "hide"},
    )
    config = SimpleNamespace(
        share_member_email_by_default=True,
        share_member_phone_by_default=False,
        share_member_address_by_default=True,
    )

    assert contact_field_visibility(subject, "email", config) == {
        "shared": False,
        "source": "member choice: Hide",
    }
    assert contact_field_visibility(subject, "phone", config) == {
        "shared": False,
        "source": "club default: Hide",
    }


def test_qr_vcard_omits_hidden_contact_fields():
    member = SimpleNamespace(
        first_name="Privacy",
        last_name="Member",
        email="hidden@example.com",
        phone="555-0100",
        mobile_phone="555-0101",
        glider_rating="student",
        address="1 Hidden Way",
        city="Lancaster",
        state_code="CA",
        state_freeform="",
        zip_code="93534",
    )
    payload = {}

    class FakeQr:
        def save(self, buffer, format_name):
            buffer.write(b"qr")

    def capture_vcard(value):
        payload["vcard"] = value
        return FakeQr()

    with patch("members.utils.vcard_tools.qrcode.make", side_effect=capture_vcard):
        generate_vcard_qr(
            member,
            contact_visibility={"email": False, "phone": True, "address": False},
        )

    assert "hidden@example.com" not in payload["vcard"]
    assert "555-0100" in payload["vcard"]
    assert "555-0101" in payload["vcard"]
    assert "1 Hidden Way" not in payload["vcard"]


@pytest.mark.django_db
def test_privileged_vcard_respects_member_visibility():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="vcard_manager",
        membership_status="Privacy Active",
        member_manager=True,
    )
    subject = Member.objects.create_user(
        username="vcard_private_member",
        email="hidden-vcard@example.com",
        phone="555-0100",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "share"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_vcard", args=[subject.id]))

    assert response.status_code == 200
    assert b"hidden-vcard@example.com" not in response.content
    assert b"555-0100" in response.content


@pytest.mark.django_db
def test_directory_omits_hidden_email_from_content_and_data_attribute():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="regular_viewer", membership_status="Privacy Active"
    )
    subject = Member.objects.create_user(
        username="private_member",
        first_name="Private",
        last_name="Member",
        email="hidden@example.com",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "hide"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert subject.full_display_name.encode() in response.content
    assert b"hidden@example.com" not in response.content
    assert b'data-email="hidden@example.com"' not in response.content


@pytest.mark.django_db
def test_directory_keeps_hidden_email_redacted_for_privileged_viewers():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="directory_manager",
        membership_status="Privacy Active",
        member_manager=True,
    )
    Member.objects.create_user(
        username="private_manager_view",
        first_name="Private",
        last_name="Member",
        email="hidden-manager@example.com",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "hide"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert b"hidden-manager@example.com" not in response.content


@pytest.mark.django_db
def test_member_can_update_contact_visibility():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    member = Member.objects.create_user(
        username="privacy_member", membership_status="Privacy Active"
    )
    client = Client()
    client.force_login(member)

    response = client.post(
        reverse("members:update_contact_visibility", args=[member.id]),
        {"share_email": "on", "share_address": "on"},
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.contact_visibility == {
        "email": "share",
        "phone": "hide",
        "address": "share",
    }


@pytest.mark.django_db
def test_vcard_download_filters_contact_fields_for_regular_member():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="vcard_viewer", membership_status="Privacy Active"
    )
    subject = Member.objects.create_user(
        username="vcard_subject",
        first_name="VCard",
        last_name="Subject",
        email="hidden@example.com",
        phone="555-0100",
        address="1 Hidden Way",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "share", "address": "hide"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_vcard", args=[subject.id]))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/vcard"
    assert b"hidden@example.com" not in response.content
    assert b"555-0100" in response.content
    assert b"1 Hidden Way" not in response.content


@pytest.mark.django_db
def test_email_change_requires_confirmation_before_replacing_email(mailoutbox):
    MembershipStatus.objects.create(name="Email Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example",
        club_abbreviation="TEST",
        member_profile_field_policies={"email": "direct"},
    )
    member = Member.objects.create_user(
        username="email_member",
        email="old@example.com",
        membership_status="Email Active",
    )
    client = Client()
    client.force_login(member)

    response = client.post(
        reverse("members:request_email_change"), {"email": "new@example.com"}
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.email == "old@example.com"
    assert member.pending_email == "new@example.com"
    assert [message.to for message in mailoutbox] == [
        ["new@example.com"],
        ["old@example.com"],
    ]

    token = signing.dumps(
        {"member_id": member.pk, "email": "new@example.com"},
        salt="members.email-change",
    )
    client.logout()
    response = client.get(reverse("members:confirm_email_change", args=[token]))

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.email == "new@example.com"
    assert member.pending_email == ""
    assert member.pending_email_requested_at is None
