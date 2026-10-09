from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from members.utils.permissions import can_view_contact_field, contact_field_visibility
from members.utils.vcard_tools import generate_vcard, generate_vcard_qr
from siteconfig.models import MembershipStatus


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
        country="US",
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


def test_vcard_escapes_text_values_and_uses_crlf_line_endings():
    member = SimpleNamespace(
        first_name="Jane\nNOTE:Injected",
        last_name="Doe;Smith, Jr.\\",
        email="jane@example.com\r\nNOTE:Injected",
        phone="555-0100",
        mobile_phone="",
        glider_rating="student",
        address="1 Main St; Unit 2\nNOTE:Injected",
        city="Lancaster",
        state_code="CA",
        state_freeform="",
        zip_code="93534",
        country="US",
    )

    vcard = generate_vcard(member)

    assert "N:Doe\\;Smith\\, Jr.\\\\;Jane\\nNOTE:Injected;;;" in vcard
    assert "EMAIL;TYPE=INTERNET,HOME:jane@example.com\\nNOTE:Injected" in vcard
    assert "ADR;TYPE=HOME:;;1 Main St\\; Unit 2\\nNOTE:Injected;" in vcard
    assert "\r\nNOTE:Injected" not in vcard
    assert "\n" not in vcard.replace("\r\n", "")
    assert vcard.endswith("\r\n")


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
def test_profile_privacy_checkboxes_show_effective_member_preferences():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    member = Member.objects.create_user(
        username="privacy_owner",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "share"},
    )
    client = Client()
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.id]))

    assert response.status_code == 200
    assert b'name="share_email" id="share_email">' in response.content
    assert b'name="share_phone" id="share_phone" checked' in response.content
    assert b'name="share_address" id="share_address" checked' in response.content


@pytest.mark.django_db
def test_staff_contact_legend_shows_regular_member_visibility():
    viewer = Member.objects.create_user(
        username="privacy_admin",
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
    )
    subject = Member.objects.create_user(
        username="hidden_member",
        first_name="Hidden",
        last_name="Member",
        contact_visibility={"email": "hide"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_view", args=[subject.pk]))

    assert response.status_code == 200
    email_status = next(
        status
        for status in response.context["staff_contact_status"]
        if status["label"] == "Email"
    )
    assert email_status == {
        "label": "Email",
        "shared": False,
        "source": "member choice: Hide",
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
