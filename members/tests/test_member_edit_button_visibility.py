import pytest
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(username, **kwargs):
    defaults = {
        "password": "password",
        "membership_status": "Full Member",
        "email": f"{username}@example.com",
    }
    defaults.update(kwargs)
    return Member.objects.create_user(username=username, **defaults)


@pytest.mark.django_db
def test_superuser_sees_edit_member_button(client):
    _ensure_full_member_status()
    subject = _make_member("subject_superuser_view")
    superuser = _make_member("viewer_superuser")
    superuser.is_superuser = True
    superuser.is_staff = True
    superuser.save(update_fields=["is_superuser", "is_staff"])

    client.force_login(superuser)
    response = client.get(reverse("members:member_view", args=[subject.id]))
    edit_url = reverse("admin:members_member_change", args=[subject.id])

    assert response.status_code == 200
    assert edit_url in response.content.decode()


@pytest.mark.django_db
def test_member_manager_sees_edit_member_button(client):
    _ensure_full_member_status()
    subject = _make_member("subject_mm_view")
    member_manager = _make_member("viewer_member_manager", member_manager=True)

    client.force_login(member_manager)
    response = client.get(reverse("members:member_view", args=[subject.id]))
    edit_url = reverse("admin:members_member_change", args=[subject.id])

    assert response.status_code == 200
    assert edit_url in response.content.decode()


@pytest.mark.django_db
def test_instructor_does_not_see_edit_member_button(client):
    _ensure_full_member_status()
    subject = _make_member("subject_instructor_view")
    instructor = _make_member("viewer_instructor", instructor=True)

    client.force_login(instructor)
    response = client.get(reverse("members:member_view", args=[subject.id]))
    edit_url = reverse("admin:members_member_change", args=[subject.id])

    assert response.status_code == 200
    assert edit_url not in response.content.decode()


@pytest.mark.django_db
def test_regular_member_does_not_see_edit_member_button(client):
    _ensure_full_member_status()
    subject = _make_member("subject_regular_view")
    regular_member = _make_member("viewer_regular")

    client.force_login(regular_member)
    response = client.get(reverse("members:member_view", args=[subject.id]))
    edit_url = reverse("admin:members_member_change", args=[subject.id])

    assert response.status_code == 200
    assert edit_url not in response.content.decode()
