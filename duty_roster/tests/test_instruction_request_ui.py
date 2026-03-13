from datetime import date, timedelta

import pytest
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from siteconfig.models import MembershipStatus


def _ensure_full_member_status():
    MembershipStatus.objects.update_or_create(
        name="Full Member",
        defaults={"is_active": True},
    )


def _make_member(django_user_model, username, instructor=False, **extra):
    extra.setdefault("email", f"{username}@example.com")
    return django_user_model.objects.create_user(
        username=username,
        password="password",
        membership_status="Full Member",
        instructor=instructor,
        **extra,
    )


def _make_assignment(primary, surge=None, date_offset=30):
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=date_offset),
        instructor=primary,
    )
    if surge:
        assignment.surge_instructor = surge
        assignment.save(update_fields=["surge_instructor"])
    return assignment


@pytest.mark.django_db
def test_instructor_requests_shows_profile_link_long_note_and_revert_action(
    client, django_user_model
):
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "ui_primary", instructor=True)
    student = _make_member(django_user_model, "ui_student")
    assignment = _make_assignment(primary, date_offset=40)

    long_note = (
        "I need focused practice on pattern discipline, radio calls, and "
        "crosswind corrections for a full tow and landing sequence."
    )
    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="confirmed",
        instructor_response="accepted",
        student_notes=long_note,
    )

    client.force_login(primary)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert reverse("members:member_view", kwargs={"member_id": student.pk}) in content
    assert long_note in content
    assert (
        reverse(
            "duty_roster:revert_instruction_response",
            kwargs={"slot_id": slot.pk},
        )
        in content
    )


@pytest.mark.django_db
def test_revert_instruction_response_moves_accepted_slot_back_to_pending(
    client, django_user_model
):
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "revert_primary", instructor=True)
    surge = _make_member(django_user_model, "revert_surge", instructor=True)
    student = _make_member(django_user_model, "revert_student")
    assignment = _make_assignment(primary, surge=surge, date_offset=50)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="confirmed",
        instructor_response="accepted",
        instructor_note="Accepted, see you then",
    )

    client.force_login(primary)
    response = client.post(
        reverse("duty_roster:revert_instruction_response", kwargs={"slot_id": slot.pk})
    )

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:instructor_requests"))

    slot.refresh_from_db()
    assert slot.instructor_response == "pending"
    assert slot.status == "pending"
    assert slot.instructor is None
    assert slot.instructor_note == ""
    assert slot.instructor_response_at is None


@pytest.mark.django_db
def test_revert_instruction_response_forbidden_for_unassigned_instructor(
    client, django_user_model
):
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "forbid_primary", instructor=True)
    surge = _make_member(django_user_model, "forbid_surge", instructor=True)
    outsider = _make_member(django_user_model, "forbid_outsider", instructor=True)
    student = _make_member(django_user_model, "forbid_student")
    assignment = _make_assignment(primary, surge=surge, date_offset=60)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="confirmed",
        instructor_response="accepted",
    )

    client.force_login(outsider)
    response = client.post(
        reverse("duty_roster:revert_instruction_response", kwargs={"slot_id": slot.pk})
    )

    assert response.status_code == 403
    slot.refresh_from_db()
    assert slot.instructor_response == "accepted"
    assert slot.status == "confirmed"


@pytest.mark.django_db
def test_my_instruction_requests_shows_full_student_note_content(
    client, django_user_model
):
    _ensure_full_member_status()
    student = _make_member(django_user_model, "myreq_student")
    primary = _make_member(django_user_model, "myreq_primary", instructor=True)
    assignment = _make_assignment(primary, date_offset=35)

    long_note = (
        "Please help me with tow positioning and coordinated turns because "
        "I am preparing for upcoming solo requirements and consistency checks."
    )
    InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="pending",
        instructor_response="pending",
        student_notes=long_note,
    )

    client.force_login(student)
    response = client.get(reverse("duty_roster:my_instruction_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "My Request" in content
    assert long_note in content
