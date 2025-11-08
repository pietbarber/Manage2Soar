import pytest
from django.urls import reverse

from members.models import Member
from notifications.models import Notification


@pytest.mark.django_db
def test_toggle_creates_notification_for_rostermeister(client):
    # Create a rostermeister and a normal member (Member is the AUTH_USER_MODEL)
    rm_member = Member.objects.create(
        username="rm_member", member_manager=True, membership_status="Full Member"
    )
    member = Member.objects.create(username="user1", membership_status="Full Member")

    # Login as the member and POST to toggle
    client.force_login(member)
    url = reverse("members:toggle_redaction", kwargs={"member_id": member.id})
    resp = client.post(url, follow=True)
    assert resp.status_code == 200

    # There should be at least one Notification for the rostermeister Member object
    assert Notification.objects.filter(user=rm_member).exists()


@pytest.mark.django_db
def test_toggle_dedupe_notifications(client):
    # Create rostermeister and member
    rm_member = Member.objects.create(
        username="rm2", member_manager=True, membership_status="Full Member"
    )
    member = Member.objects.create(username="user2", membership_status="Full Member")

    client.force_login(member)
    url = reverse("members:toggle_redaction", kwargs={"member_id": member.id})

    # First toggle -> creates notification
    resp1 = client.post(url, follow=True)
    assert resp1.status_code == 200

    # Second toggle immediately -> should NOT create a second notification due to dedupe
    resp2 = client.post(url, follow=True)
    assert resp2.status_code == 200

    notes = Notification.objects.filter(
        user=rm_member, url__contains=f"members/{member.id}"
    )
    assert notes.count() == 1
