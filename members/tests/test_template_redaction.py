import pytest
from django.urls import reverse

from members.models import Member


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
def test_removing_full_redaction_explains_field_visibility_restoration(client):
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
    assert "Restore Sharing Choices" in content
    assert "per-field choices and club defaults" in content
    assert "fields set to Hide will remain private" in content
    assert "will be visible to other members again" not in content
