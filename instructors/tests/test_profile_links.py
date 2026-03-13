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


@pytest.mark.django_db
def test_instruction_record_profile_photo_links_to_member_profile(client):
    _ensure_full_member_status()
    student = _make_member("record_student_photo")
    student.profile_photo = "members/profile/record_student_photo.jpg"
    student.save(update_fields=["profile_photo"])

    profile_url = reverse("members:member_view", kwargs={"member_id": student.pk})

    client.force_login(student)
    response = client.get(
        reverse("instructors:member_instruction_record", args=[student.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    # One link is the profile button; the second should wrap the profile image bubble.
    assert content.count(profile_url) >= 2
