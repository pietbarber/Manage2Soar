import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from members.models import Member

User = get_user_model()


@pytest.mark.django_db
def test_member_can_toggle_own_redaction(client):
    m = Member.objects.create(
        username="self", email="self@example.com", membership_status="Full Member"
    )
    # login as the member
    client.force_login(m)
    url = reverse("members:toggle_redaction", args=[m.id])
    # initial should be False
    assert not m.redact_contact
    resp = client.post(url, follow=True)
    m.refresh_from_db()
    assert resp.status_code == 200
    assert m.redact_contact


@pytest.mark.django_db
def test_other_member_cannot_toggle(client):
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
def test_superuser_can_toggle_anyone(client):
    subj = Member.objects.create(
        username="subj2", email="s2@example.com", membership_status="Full Member"
    )
    admin = User.objects.create(username="admin", is_superuser=True, is_staff=True)
    client.force_login(admin)
    url = reverse("members:toggle_redaction", args=[subj.id])
    resp = client.post(url, follow=True)
    subj.refresh_from_db()
    assert resp.status_code == 200
    assert subj.redact_contact
