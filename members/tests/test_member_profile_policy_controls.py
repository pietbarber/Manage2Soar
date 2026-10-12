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
