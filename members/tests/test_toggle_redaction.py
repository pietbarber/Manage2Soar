import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from members.models import Member
from siteconfig.models import SiteConfiguration

User = get_user_model()


@pytest.mark.django_db
def test_legacy_redaction_endpoint_does_not_change_privacy_preferences(client):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    m = Member.objects.create(
        username="self", email="self@example.com", membership_status="Full Member"
    )
    client.force_login(m)
    url = reverse("members:toggle_redaction", args=[m.id])
    resp = client.post(url, follow=True)
    m.refresh_from_db()
    assert resp.status_code == 200
    assert not m.redact_contact
    assert m.contact_visibility == {}


@pytest.mark.django_db
def test_other_member_cannot_use_legacy_redaction_endpoint(client):
    subj = Member.objects.create(
        username="subj", email="s@example.com", membership_status="Full Member"
    )
    other = Member.objects.create(
        username="other", email="o@example.com", membership_status="Full Member"
    )
    client.force_login(other)
    url = reverse("members:toggle_redaction", args=[subj.id])
    resp = client.post(url)
    # should return 403
    assert resp.status_code == 403


@pytest.mark.django_db
def test_superuser_cannot_use_legacy_redaction_endpoint(client):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="testclub.com",
        club_abbreviation="TC",
    )
    subj = Member.objects.create(
        username="subj2", email="s2@example.com", membership_status="Full Member"
    )
    admin = User.objects.create(username="admin", is_superuser=True, is_staff=True)
    client.force_login(admin)
    url = reverse("members:toggle_redaction", args=[subj.id])
    resp = client.post(url, follow=True)
    subj.refresh_from_db()
    assert resp.status_code == 200
    assert not subj.redact_contact
    assert subj.contact_visibility == {}
