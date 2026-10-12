import pytest
from django.urls import reverse

from members.models import Member
from notifications.models import Notification
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_retired_redaction_endpoint_does_not_create_notifications(client):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    rm_member = Member.objects.create(
        username="rm_member", member_manager=True, membership_status="Full Member"
    )
    member = Member.objects.create(username="user1", membership_status="Full Member")

    client.force_login(member)
    url = reverse("members:toggle_redaction", kwargs={"member_id": member.id})
    resp = client.post(url, follow=True)
    assert resp.status_code == 200

    assert not Notification.objects.filter(user=rm_member).exists()


@pytest.mark.django_db
def test_retired_redaction_endpoint_does_not_duplicate_notifications(client):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    rm_member = Member.objects.create(
        username="rm2", member_manager=True, membership_status="Full Member"
    )
    member = Member.objects.create(username="user2", membership_status="Full Member")

    client.force_login(member)
    url = reverse("members:toggle_redaction", kwargs={"member_id": member.id})

    resp1 = client.post(url, follow=True)
    assert resp1.status_code == 200

    resp2 = client.post(url, follow=True)
    assert resp2.status_code == 200

    notes = Notification.objects.filter(
        user=rm_member, url__contains=f"members/{member.id}"
    )
    assert notes.count() == 0
