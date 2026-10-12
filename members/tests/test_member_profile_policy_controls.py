import pytest
from django.urls import reverse

from members.models import Biography, Member
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import (
    MembershipStatus,
    SiteConfiguration,
    default_member_profile_field_policies,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "control"),
    [
        ("profile_photo", b"Update Profile Photo"),
        ("email", b"Change Email"),
        ("biography", b"Edit Biography"),
        ("password", b"Change Password"),
        ("emergency_contacts", b"Add Emergency Contact"),
        ("contact_visibility", b'name="visibility_email"'),
    ],
)
def test_profile_self_service_controls_require_direct_policy(client, field, control):
    MembershipStatus.objects.create(name="Policy Member", is_active=True)
    clear_active_membership_statuses_cache()
    policies = default_member_profile_field_policies()
    policies[field] = "disabled"
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
        member_profile_field_policies=policies,
    )
    member = Member.objects.create_user(
        username=f"policy_{field}",
        password="password",
        membership_status="Policy Member",
    )
    Biography.objects.create(member=member, content="<p>Biography</p>")
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert control not in response.content


@pytest.mark.django_db
def test_biography_navigation_requires_direct_policy(client):
    MembershipStatus.objects.create(name="Policy Member", is_active=True)
    clear_active_membership_statuses_cache()
    policies = default_member_profile_field_policies()
    policies["biography"] = "disabled"
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
        member_profile_field_policies=policies,
    )
    member = Member.objects.create_user(
        username="policy_biography_navigation",
        password="password",
        membership_status="Policy Member",
    )
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert b"Edit my Biography" not in response.content


@pytest.mark.django_db
def test_profile_page_is_self_service_hub_for_direct_controls(client):
    MembershipStatus.objects.create(name="Policy Member", is_active=True)
    clear_active_membership_statuses_cache()
    policies = default_member_profile_field_policies()
    for field in (
        "profile_photo",
        "email",
        "biography",
        "password",
        "emergency_contacts",
        "contact_visibility",
    ):
        policies[field] = "direct"
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
        member_profile_field_policies=policies,
    )
    member = Member.objects.create_user(
        username="profile_hub",
        email="member@example.com",
        password="password",
        membership_status="Policy Member",
    )
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    assert reverse("members:request_email_change").encode() in response.content
    assert b'id="profile-editing"' not in response.content
    assert b"emailSettingsModal" in response.content
    assert reverse("members:set_password").encode() in response.content
    assert (
        reverse("members:biography_view", args=[member.pk]).encode() in response.content
    )
    assert b'aria-labelledby="privacySettingsModalLabel"' in response.content


@pytest.mark.django_db
def test_email_change_control_is_not_shown_to_other_members(client):
    MembershipStatus.objects.create(name="Policy Member", is_active=True)
    clear_active_membership_statuses_cache()
    SiteConfiguration.objects.create(
        club_name="Test Club", domain_name="testclub.com", club_abbreviation="TC"
    )
    viewer = Member.objects.create_user(
        username="profile_viewer",
        password="password",
        membership_status="Policy Member",
    )
    subject = Member.objects.create_user(
        username="profile_subject",
        password="password",
        membership_status="Policy Member",
    )
    client.force_login(viewer)

    response = client.get(reverse("members:member_view", args=[subject.pk]))

    assert response.status_code == 200
    assert b"Change Email" not in response.content
    assert b"emailSettingsModal" not in response.content
