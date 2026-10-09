import pytest

from members.models import EmergencyContact, Member
from members.models_applications import MembershipApplication


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
