import pytest

from members.models import EmergencyContact, Member
from members.models_applications import MembershipApplication
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.admin import SiteConfigurationAdminForm
from siteconfig.models import (
    MembershipStatus,
    SiteConfiguration,
    default_member_profile_field_policies,
    get_member_profile_field_policy,
)


@pytest.mark.django_db
def test_emergency_contacts_are_structured_and_member_scoped():
    first_member = Member.objects.create_user(username="first_member")
    second_member = Member.objects.create_user(username="second_member")

    first_contact = EmergencyContact.objects.create(
        member=first_member,
        name="First Contact",
        relationship="Sibling",
        mobile_phone="555-0100",
    )
    EmergencyContact.objects.create(
        member=first_member,
        name="Second Contact",
        home_phone="555-0101",
    )
    EmergencyContact.objects.create(member=second_member, name="Other Member Contact")

    assert list(first_member.emergency_contacts.values_list("name", flat=True)) == [
        "First Contact",
        "Second Contact",
    ]
    assert first_contact.relationship == "Sibling"
    assert second_member.emergency_contacts.count() == 1


@pytest.mark.django_db
def test_approved_application_creates_structured_emergency_contact():
    application = MembershipApplication.objects.create(
        first_name="New",
        last_name="Member",
        email="new.member@example.com",
        phone="555-0200",
        address_line1="1 Soaring Way",
        city="Lancaster",
        state="CA",
        zip_code="93534",
        emergency_contact_name="Emergency Person",
        emergency_contact_relationship="Parent",
        emergency_contact_phone="555-0201",
        agrees_to_terms=True,
        agrees_to_safety_rules=True,
        agrees_to_financial_obligations=True,
    )

    member = application.approve_application()

    contact = member.emergency_contacts.get()
    assert contact.name == "Emergency Person"
    assert contact.relationship == "Parent"
    assert contact.mobile_phone == "555-0201"
    assert member.emergency_contact is None


def test_profile_policy_defaults_are_explicit_and_safe():
    policies = default_member_profile_field_policies()

    assert policies["username"] == "disabled"
    assert policies["email"] == "disabled"
    assert policies["emergency_contacts"] == "request"
    assert policies["password"] == "direct"
    assert policies["profile_photo"] == "direct"


@pytest.mark.django_db
def test_site_configuration_controls_profile_policy_safely():
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example",
        club_abbreviation="TEST",
        member_profile_field_policies={"phone": "direct", "address": "bogus"},
    )

    assert get_member_profile_field_policy("phone") == "direct"
    assert get_member_profile_field_policy("address") == "disabled"
    assert get_member_profile_field_policy("email") == "disabled"

    config = SiteConfiguration.objects.first()
    config.member_profile_self_service_enabled = False
    config.save(update_fields=["member_profile_self_service_enabled"])

    assert get_member_profile_field_policy("phone") == "disabled"


@pytest.mark.django_db
def test_admin_profile_policy_choices_exclude_paused_request_mode():
    form = SiteConfigurationAdminForm(
        instance=SiteConfiguration(member_profile_field_policies={"phone": "request"})
    )

    form.cleaned_data = {"member_profile_field_policies": {"phone": "request"}}
    assert form.clean_member_profile_field_policies() == {"phone": "disabled"}
    assert (
        "Request mode is not available"
        in form.fields["member_profile_field_policies"].help_text
    )


@pytest.mark.django_db
def test_direct_username_and_email_policies_expose_member_edit_paths():
    MembershipStatus.objects.create(name="Direct Active", is_active=True, sort_order=1)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example",
        club_abbreviation="TEST",
        member_profile_field_policies={"username": "direct", "email": "direct"},
    )
    member = Member.objects.create_user(
        username="editable_member",
        email="old@example.com",
        membership_status="Direct Active",
    )
    client = Client()
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.id]))

    assert response.status_code == 200
    assert b"username/change" not in response.content
    assert b"email/change" not in response.content

    response = client.get(reverse("members:account_settings"))

    assert response.status_code == 200
    assert b"username/change" in response.content
    assert b"email/change" in response.content

    response = client.post(
        reverse("members:update_username"), {"username": "renamed_member"}
    )

    assert response.status_code == 302
    member.refresh_from_db()
    assert member.username == "renamed_member"
