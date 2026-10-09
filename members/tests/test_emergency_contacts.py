import pytest
from django.test import Client
from django.urls import reverse

from members.models import EmergencyContact, Member


@pytest.fixture
def member():
    return Member.objects.create_superuser(
        username="contact_owner",
        email="owner@example.com",
        password="test-password",
    )


@pytest.fixture
def client_for(member):
    client = Client()
    client.force_login(member)
    return client


@pytest.mark.django_db
def test_member_can_add_and_edit_emergency_contact(member, client_for):
    add_url = reverse("members:emergency_contact_add", args=[member.pk])
    response = client_for.post(
        add_url,
        {
            "name": "Emergency Person",
            "relationship": "Sibling",
            "home_phone": "",
            "mobile_phone": "555-0100",
            "preferred_contact_method": "mobile_phone",
            "preferred_contact_details": "Text first",
            "address": "",
        },
    )
    contact = member.emergency_contacts.get()

    assert response.status_code == 302
    assert contact.name == "Emergency Person"

    response = client_for.post(
        reverse("members:emergency_contact_edit", args=[member.pk, contact.pk]),
        {
            "name": "Updated Person",
            "relationship": "Parent",
            "home_phone": "555-0101",
            "mobile_phone": "",
            "preferred_contact_method": "home_phone",
            "preferred_contact_details": "",
            "address": "1 Soaring Way",
        },
    )
    contact.refresh_from_db()

    assert response.status_code == 302
    assert contact.name == "Updated Person"
    assert contact.home_phone == "555-0101"


@pytest.mark.django_db
def test_member_cannot_edit_another_members_emergency_contact(member, client_for):
    other = Member.objects.create_superuser(
        username="other_owner",
        email="other@example.com",
        password="test-password",
    )
    contact = EmergencyContact.objects.create(member=other, name="Private Contact")

    response = client_for.get(
        reverse("members:emergency_contact_edit", args=[other.pk, contact.pk])
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_endpoint_checks_ownership_before_contact_lookup(member, client_for):
    other = Member.objects.create_user(
        username="other_owner",
        email="other@example.com",
    )
    contact = EmergencyContact.objects.create(member=other, name="Private Contact")

    existing_contact_response = client_for.get(
        reverse("members:emergency_contact_delete", args=[other.pk, contact.pk])
    )
    nonexistent_contact_response = client_for.get(
        reverse("members:emergency_contact_delete", args=[other.pk, contact.pk + 1])
    )

    assert existing_contact_response.status_code == 403
    assert nonexistent_contact_response.status_code == 403


@pytest.mark.django_db
def test_removing_final_contact_requires_confirmation(member, client_for):
    contact = EmergencyContact.objects.create(member=member, name="Final Contact")
    delete_url = reverse(
        "members:emergency_contact_delete", args=[member.pk, contact.pk]
    )

    response = client_for.post(delete_url, {})
    assert response.status_code == 200
    assert EmergencyContact.objects.filter(pk=contact.pk).exists()

    response = client_for.post(delete_url, {"confirmation": "NO EMERGENCY CONTACT"})
    assert response.status_code == 302
    assert not EmergencyContact.objects.filter(pk=contact.pk).exists()


@pytest.mark.django_db
def test_profile_renders_multiple_contacts_with_formatted_phone_numbers(
    member, client_for
):
    EmergencyContact.objects.create(
        member=member,
        name="Home Contact",
        home_phone="6615550100",
    )
    EmergencyContact.objects.create(
        member=member,
        name="Mobile Contact",
        mobile_phone="6615550101",
    )

    response = client_for.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert b"Home Contact" in response.content
    assert b"Mobile Contact" in response.content
    assert b"+1 661-555-0100" in response.content
    assert b"+1 661-555-0101" in response.content


@pytest.mark.django_db
def test_profile_displays_preferred_method_and_details_separately(member, client_for):
    EmergencyContact.objects.create(
        member=member,
        name="Preferred Contact",
        mobile_phone="555-0100",
        preferred_contact_method="mobile_phone",
        preferred_contact_details="Text after 5 PM",
    )

    response = client_for.get(reverse("members:member_view", args=[member.pk]))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Preferred method: Mobile phone" in content
    assert "Additional preferred contact details: Text after 5 PM" in content
    assert "Preferred: Text after 5 PM" not in content


@pytest.mark.django_db
def test_profile_falls_back_to_legacy_emergency_contact(member, client_for):
    member.emergency_contact = "Legacy Contact: 555-0100"
    member.save(update_fields=["emergency_contact"])

    response = client_for.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert b"Legacy Contact: 555-0100" in response.content
