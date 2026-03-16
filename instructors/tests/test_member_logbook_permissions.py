import pytest
from django.urls import reverse

from members.models import Member
from siteconfig.models import MembershipStatus


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(username, instructor=False, glider_rating="student"):
    return Member.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        glider_rating=glider_rating,
        email=f"{username}@example.com",
    )


@pytest.mark.django_db
def test_member_can_view_own_logbook(client):
    _ensure_full_member_status()
    student = _make_member("logbook_self")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_instructor_can_view_student_logbook(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_instructor", instructor=True)
    student = _make_member("logbook_student")

    client.force_login(instructor)
    response = client.get(
        reverse("instructors:member_logbook_member", args=[student.pk])
    )

    assert response.status_code == 200
    assert response.context["member"].pk == student.pk


@pytest.mark.django_db
def test_non_instructor_cannot_view_another_members_logbook(client):
    _ensure_full_member_status()
    member_a = _make_member("logbook_member_a")
    member_b = _make_member("logbook_member_b")

    client.force_login(member_a)
    response = client.get(
        reverse("instructors:member_logbook_member", args=[member_b.pk])
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_invalid_member_logbook_returns_404(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_instructor_404", instructor=True)

    client.force_login(instructor)
    response = client.get(reverse("instructors:member_logbook_member", args=[999999]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_member_can_export_own_logbook_csv(client):
    _ensure_full_member_status()
    student = _make_member("logbook_csv_self")

    client.force_login(student)
    response = client.get(reverse("instructors:member_logbook_export_csv"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_instructor_can_export_student_logbook_csv(client):
    _ensure_full_member_status()
    instructor = _make_member("logbook_csv_instructor", instructor=True)
    student = _make_member("logbook_csv_student")

    client.force_login(instructor)
    response = client.get(
        reverse("instructors:member_logbook_export_csv_member", args=[student.pk])
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_non_instructor_cannot_export_another_members_logbook_csv(client):
    _ensure_full_member_status()
    member_a = _make_member("logbook_csv_member_a")
    member_b = _make_member("logbook_csv_member_b")

    client.force_login(member_a)
    response = client.get(
        reverse("instructors:member_logbook_export_csv_member", args=[member_b.pk])
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_instruction_record_shows_logbook_link(client):
    _ensure_full_member_status()
    student = _make_member("instruction_record_logbook_link")

    client.force_login(student)
    response = client.get(
        reverse("instructors:member_instruction_record", args=[student.pk])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("instructors:member_logbook_member", args=[student.pk]) in content


@pytest.mark.django_db
def test_progress_dashboard_dropdown_shows_logbook_link(client):
    _ensure_full_member_status()
    instructor = _make_member(
        "progress_dashboard_instructor", instructor=True, glider_rating="rated"
    )
    student = _make_member("progress_dashboard_student", glider_rating="student")

    client.force_login(instructor)
    response = client.get(reverse("instructors:instructors-dashboard"))

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("instructors:member_logbook_member", args=[student.pk]) in content
