import pytest
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(username, instructor=False):
    return Member.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        email=f"{username}@example.com",
    )


@pytest.mark.django_db
def test_training_grid_shows_member_profile_icon_link(client):
    _ensure_full_member_status()
    student = _make_member("grid_student")

    client.force_login(student)
    response = client.get(
        reverse("instructors:member_training_grid", args=[student.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("members:member_view", kwargs={"member_id": student.pk}) in content


@pytest.mark.django_db
def test_instruction_record_shows_member_profile_icon_link(client):
    _ensure_full_member_status()
    student = _make_member("record_student")

    client.force_login(student)
    response = client.get(
        reverse("instructors:member_instruction_record", args=[student.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("members:member_view", kwargs={"member_id": student.pk}) in content
