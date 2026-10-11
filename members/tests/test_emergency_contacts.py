from unittest.mock import patch

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test import Client, RequestFactory
from django.urls import reverse

from members.models import EmergencyContact, Member
from members.views import member_view
from siteconfig.models import SiteConfiguration, get_member_profile_field_policy


@pytest.fixture
def member():
    return Member.objects.create_superuser(
        username="contact_owner",
        email="owner@example.com",
        password="test-password",
    )


@pytest.fixture
def direct_policy():
    """Configure direct self-service edits for emergency contacts.

    The add/edit/remove endpoints are gated on the member profile field
    policy, which defaults to 'direct'. These flow tests explicitly configure
    the policy to make their required behavior clear.
    """
    config = SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    policies = config.member_profile_field_policies
    policies["emergency_contacts"] = "direct"
    config.save(update_fields=["member_profile_field_policies"])
    return config


@pytest.fixture
def client_for(member):
    client = Client()
    client.force_login(member)
    return client


@pytest.mark.django_db
def test_member_can_add_and_edit_emergency_contact(member, client_for, direct_policy):
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
def test_removing_final_contact_requires_confirmation(
    member, client_for, direct_policy
):
    member.emergency_contact = "Legacy emergency contact"
    member.save(update_fields=["emergency_contact"])
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
    member.refresh_from_db()
    assert not member.emergency_contact


@pytest.mark.django_db
def test_contact_delete_locks_member_before_recounting(
    member, client_for, direct_policy
):
    contact = EmergencyContact.objects.create(member=member, name="First Contact")
    remaining_contact = EmergencyContact.objects.create(
        member=member, name="Second Contact"
    )
    delete_url = reverse(
        "members:emergency_contact_delete", args=[member.pk, contact.pk]
    )

    # The reviewer flagged that merely asserting select_for_update() was called
    # is insufficient: it does not prove the lock is still held when the
    # recount and delete run. Record the active transaction depth at both the
    # lock acquisition and the delete, and assert the delete happens inside
    # the same (still-open) transaction as the lock.
    original_select_for_update = QuerySet.select_for_update
    select_state: dict = {}

    def select_for_update_side_effect(*args, **kwargs):
        select_state["atomic_blocks"] = len(connection.atomic_blocks)
        select_state["autocommit"] = connection.autocommit
        return original_select_for_update(*args, **kwargs)

    original_delete = EmergencyContact.delete
    delete_holder: dict = {}

    def tracked_delete(self, *args, **kwargs):
        delete_holder["atomic_blocks"] = len(connection.atomic_blocks)
        delete_holder["autocommit"] = connection.autocommit
        return original_delete(self, *args, **kwargs)

    baseline_blocks = len(connection.atomic_blocks)

    with (
        patch.object(
            QuerySet,
            "select_for_update",
            autospec=True,
            side_effect=select_for_update_side_effect,
        ) as select_for_update,
        patch.object(EmergencyContact, "delete", tracked_delete),
    ):
        response = client_for.post(delete_url, {})

    assert response.status_code == 302
    select_for_update.assert_called_once()

    # Lock was acquired inside an explicit (non-autocommit) transaction.
    assert select_state["autocommit"] is False
    assert select_state["atomic_blocks"] >= 1

    # The delete must execute while the lock's transaction is still open:
    # same depth as the lock acquisition, and strictly deeper than the
    # baseline the request started from. Against the old code the view's
    # atomic block closed before the delete, so delete ran one level shallower.
    delete_state = delete_holder
    assert delete_state["autocommit"] is False
    assert delete_state["atomic_blocks"] == select_state["atomic_blocks"]
    assert delete_state["atomic_blocks"] >= baseline_blocks + 1

    assert not EmergencyContact.objects.filter(pk=contact.pk).exists()
    assert EmergencyContact.objects.filter(pk=remaining_contact.pk).exists()


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
def test_profile_reuses_site_configuration_for_all_policies(member, direct_policy):
    request = RequestFactory().get(reverse("members:member_view", args=[member.pk]))
    request.user = member
    with (
        patch("members.views.render", return_value=None),
        patch(
            "members.views.get_member_profile_field_policy",
            wraps=get_member_profile_field_policy,
        ) as policy_lookup,
    ):
        member_view.__wrapped__(request, member.pk)

    assert [call.args[0] for call in policy_lookup.call_args_list] == [
        "profile_photo",
        "biography",
        "emergency_contacts",
        "contact_visibility",
        "password",
    ]
    site_configs = [call.args[1] for call in policy_lookup.call_args_list]
    assert site_configs[0] is not None
    assert all(site_config is site_configs[0] for site_config in site_configs)


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
