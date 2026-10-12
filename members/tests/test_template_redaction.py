import pytest
from django.urls import reverse

from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_redacted_member_shows_redacted_for_non_privileged_client(client):
    # Create subject who has redacted their contact info
    subject = Member.objects.create(
        username="redactsubj",
        email="r@example.com",
        redact_contact=True,
        membership_status="Full Member",
    )
    # create a non-privileged viewer
    viewer = Member.objects.create(
        username="viewer", email="v@example.com", membership_status="Full Member"
    )

    client.force_login(viewer)
    url = reverse("members:member_view", args=[subject.id])
    resp = client.get(url)
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    # The template should show the string 'Redacted' for suppressed contact fields
    assert "Redacted" in content


@pytest.mark.django_db
def test_profile_uses_per_field_controls_without_legacy_redaction(client):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    member = Member.objects.create(
        username="redaction_owner",
        email="owner@example.com",
        redact_contact=True,
        contact_visibility={"email": "hide"},
        membership_status="Full Member",
    )
    client.force_login(member)

    response = client.get(reverse("members:member_view", args=[member.id]))
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert 'name="visibility_email"' in content
    assert "Restore Sharing Choices" not in content
    assert "redactConfirmModal" not in content
