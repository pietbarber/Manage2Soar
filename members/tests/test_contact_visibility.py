from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from members.models import Member
from members.utils.membership import clear_active_membership_statuses_cache
from members.utils.permissions import can_view_contact_field, contact_field_visibility
from members.utils.vcard_tools import generate_vcard, generate_vcard_qr
from siteconfig.models import (
    MembershipStatus,
    SiteConfiguration,
    default_member_profile_field_policies,
)


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


@pytest.mark.django_db
def test_legacy_redaction_migration_preserves_hide_all_preference():
    member = Member.objects.create_user(
        username="legacy_private",
        redact_contact=True,
        contact_visibility={"email": "share"},
    )
    migration = import_module(
        "members.migrations.0031_migrate_legacy_contact_redaction"
    )

    migration.migrate_legacy_contact_redaction(Member._meta.apps, None)

    member.refresh_from_db()
    assert not member.redact_contact
    assert member.contact_visibility == {
        "email": "hide",
        "phone": "hide",
        "address": "hide",
    }


@pytest.mark.django_db
def test_legacy_redaction_migration_reverse_restores_redaction_conservatively():
    # Records the forward migration produced (all three fields hidden) must be
    # re-redacted on rollback so members are not exposed.
    migrated = Member.objects.create_user(
        username="was_migrated",
        redact_contact=False,
        contact_visibility={"email": "hide", "phone": "hide", "address": "hide"},
    )
    # A member with any field not explicitly hidden is NOT the migration
    # signature and must be left untouched.
    untouched = Member.objects.create_user(
        username="left_alone",
        redact_contact=False,
        contact_visibility={"email": "hide", "phone": "share", "address": "hide"},
    )
    # A member with no per-field preferences at all must be left untouched.
    no_preference = Member.objects.create_user(
        username="no_pref", redact_contact=False, contact_visibility={}
    )

    migration = import_module(
        "members.migrations.0031_migrate_legacy_contact_redaction"
    )
    migration.reverse_migrate_legacy_contact_redaction(Member._meta.apps, None)

    migrated.refresh_from_db()
    assert migrated.redact_contact
    # contact_visibility preferences are preserved; only the override is restored
    assert migrated.contact_visibility == {
        "email": "hide",
        "phone": "hide",
        "address": "hide",
    }

    untouched.refresh_from_db()
    assert not untouched.redact_contact
    no_preference.refresh_from_db()
    assert not no_preference.redact_contact


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
@pytest.mark.parametrize(
    "viewer_privilege",
    [
        {"is_staff": True},
        {"member_manager": True},
        {"rostermeister": True},
    ],
)
def test_directory_keeps_hidden_contact_fields_redacted_for_privileged_viewers(
    viewer_privilege,
):
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="directory_viewer",
        membership_status="Privacy Active",
        **viewer_privilege,
    )
    Member.objects.create_user(
        username="field_hidden_subject",
        email="field-hidden@example.com",
        phone="555-0100",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "hide"},
    )
    Member.objects.create_user(
        username="fully_redacted_subject",
        email="fully-redacted@example.com",
        phone="555-0101",
        membership_status="Privacy Active",
        redact_contact=True,
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_list"))

    assert response.status_code == 200
    assert b"field-hidden@example.com" not in response.content
    assert b"555-0100" not in response.content
    assert b"fully-redacted@example.com" not in response.content
    assert b"555-0101" not in response.content


@pytest.mark.django_db
def test_member_can_set_and_inherit_contact_visibility():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    # The endpoint is gated on the member self-service policy, so establish a
    # club configuration that enables direct updates to contact visibility.
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    member = Member.objects.create_user(
        username="privacy_member",
        membership_status="Privacy Active",
        contact_visibility={"phone": "share"},
    )
    client = Client()
    client.force_login(member)

    response = client.post(
        reverse("members:update_contact_visibility", args=[member.id]),
        {
            "visibility_email": "hide",
            "visibility_phone": "share",
            "visibility_address": "inherit",
        },
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.contact_visibility == {
        "email": "hide",
        "phone": "share",
    }


@pytest.mark.django_db
def test_profile_privacy_controls_show_member_overrides():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    member = Member.objects.create_user(
        username="privacy_owner",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide", "phone": "share"},
    )
    client = Client()
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.id]))

    assert response.status_code == 200
    assert response.context["privacy_settings"] == [
        {
            "field": "email",
            "label": "Email",
            "preference": "hide",
            "shared": False,
        },
        {
            "field": "phone",
            "label": "Phone numbers",
            "preference": "share",
            "shared": True,
        },
        {
            "field": "address",
            "label": "Postal address",
            "preference": "inherit",
            "shared": True,
        },
    ]
    assert b'name="visibility_email" id="visibility_email"' in response.content
    assert b'<option value="hide" selected>Hide</option>' in response.content
    assert (
        b'<option value="inherit" selected>Inherit club default</option>'
        in response.content
    )


@pytest.mark.django_db
def test_contact_visibility_rejects_unsupported_policy():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    member = Member.objects.create_user(
        username="invalid_privacy_member",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide"},
    )
    client = Client()
    client.force_login(member)

    response = client.post(
        reverse("members:update_contact_visibility", args=[member.id]),
        {"visibility_email": "public"},
    )

    assert response.status_code == 400
    member.refresh_from_db()
    assert member.contact_visibility == {"email": "hide"}


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
def test_master_self_service_switch_blocks_member_edit_endpoints(client):
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
        member_profile_self_service_enabled=False,
    )
    member = Member.objects.create_user(
        username="self_service_member", membership_status="Privacy Active"
    )
    original_photo = member.profile_photo.name
    client.force_login(member)

    profile_response = client.get(reverse("members:member_view", args=[member.id]))
    assert profile_response.status_code == 200
    assert b"Change Password" not in profile_response.content
    assert b"Update Profile Photo" not in profile_response.content
    assert b'name="share_email"' not in profile_response.content
    assert b"Add Emergency Contact" not in profile_response.content

    profile_post = client.post(
        reverse("members:member_view", args=[member.id]),
        {"profile_photo": "ignored"},
    )
    password_post = client.post(
        reverse("members:set_password"),
        {"new_password1": "test-password", "new_password2": "test-password"},
    )
    visibility_post = client.post(
        reverse("members:update_contact_visibility", args=[member.id]),
        {"share_email": "on"},
    )
    emergency_post = client.post(
        reverse("members:emergency_contact_add", args=[member.id]),
        {"name": "Emergency Person", "mobile_phone": "555-0100"},
    )
    biography_post = client.post(
        reverse("members:biography_view", args=[member.id]),
        {"content": "<p>Not allowed</p>"},
    )
    legacy_post = client.post(
        reverse("members:toggle_redaction", args=[member.id]),
    )

    assert all(
        response.status_code == 302
        for response in (
            profile_post,
            password_post,
            visibility_post,
            emergency_post,
            biography_post,
            legacy_post,
        )
    )
    member.refresh_from_db()
    assert member.profile_photo.name == original_photo
    assert member.contact_visibility == {}
    assert member.emergency_contacts.count() == 0
    assert not member.redact_contact
    assert not member.biography.content


@pytest.mark.django_db
@pytest.mark.parametrize("policy", ["disabled", "request"])
def test_contact_visibility_endpoint_rejects_non_direct_policies(client, policy):
    MembershipStatus.objects.create(name="Policy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    policies = default_member_profile_field_policies()
    policies["contact_visibility"] = policy
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
        member_profile_field_policies=policies,
    )
    member = Member.objects.create_user(
        username=f"policy_{policy}", membership_status="Policy Active"
    )
    client.force_login(member)

    response = client.post(
        reverse("members:update_contact_visibility", args=[member.id]),
        {"share_email": "on"},
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.contact_visibility == {}


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
def test_vcard_filename_does_not_disclose_email_username_for_hidden_email():
    MembershipStatus.objects.create(name="Privacy Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    viewer = Member.objects.create_user(
        username="vcard_viewer", membership_status="Privacy Active"
    )
    subject = Member.objects.create_user(
        username="hidden@example.com",
        first_name="Private",
        last_name="Member",
        email="hidden@example.com",
        membership_status="Privacy Active",
        contact_visibility={"email": "hide"},
    )
    client = Client()
    client.force_login(viewer)

    response = client.get(reverse("members:member_vcard", args=[subject.pk]))

    assert response.status_code == 200
    assert "hidden@example.com" not in response["Content-Disposition"]
    assert response["Content-Disposition"] == (
        f'attachment; filename="member-{subject.pk}.vcf"'
    )
    assert b"hidden@example.com" not in response.content
