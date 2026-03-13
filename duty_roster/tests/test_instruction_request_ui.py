from datetime import date, timedelta

import pytest
from django.contrib.messages import get_messages
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from duty_roster.models import DutyAssignment, InstructionSlot
from notifications.models import Notification
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
@override_settings(EMAIL_DEV_MODE=False)
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

    # Student receives in-system notification and outbound email.
    assert Notification.objects.filter(
        user=student,
        message__icontains="pending review",
    ).exists()
    assert len(mail.outbox) >= 1
    email = mail.outbox[-1]
    assert student.email in email.to
    assert "Update on your instruction request" in email.subject
    assert "back to pending review" in email.body
    assert "Accepted, see you then" in email.body


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


@pytest.mark.django_db
@override_settings(EMAIL_DEV_MODE=False)
def test_revert_instruction_response_single_instructor_clears_slot_instructor(
    client, django_user_model
):
    """When only one instructor is on the assignment, reverting to pending
    should still clear slot.instructor (consistent with initial pending state)."""
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "single_primary", instructor=True)
    student = _make_member(django_user_model, "single_student")
    # Single-instructor assignment (no surge)
    assignment = _make_assignment(primary, date_offset=55)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="confirmed",
        instructor_response="accepted",
        instructor_note="See you on the field",
    )

    client.force_login(primary)
    response = client.post(
        reverse("duty_roster:revert_instruction_response", kwargs={"slot_id": slot.pk})
    )

    assert response.status_code == 302
    slot.refresh_from_db()
    assert slot.instructor_response == "pending"
    assert slot.status == "pending"
    assert slot.instructor is None
    assert slot.instructor_note == ""
    assert slot.instructor_response_at is None


@pytest.mark.django_db
def test_revert_instruction_response_blocks_past_dates(client, django_user_model):
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "past_primary", instructor=True)
    student = _make_member(django_user_model, "past_student")
    assignment = _make_assignment(primary, date_offset=-2)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="confirmed",
        instructor_response="accepted",
    )

    client.force_login(primary)
    response = client.post(
        reverse("duty_roster:revert_instruction_response", kwargs={"slot_id": slot.pk})
    )

    assert response.status_code == 302
    assert response["Location"].endswith(reverse("duty_roster:instructor_requests"))

    slot.refresh_from_db()
    assert slot.instructor_response == "accepted"
    assert slot.status == "confirmed"


@pytest.mark.django_db
def test_revert_instruction_response_cancelled_message_is_neutral(
    client, django_user_model
):
    _ensure_full_member_status()
    primary = _make_member(django_user_model, "cancel_primary", instructor=True)
    student = _make_member(django_user_model, "cancel_student")
    assignment = _make_assignment(primary, date_offset=7)

    slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        status="cancelled",
        instructor_response="declined",
    )

    client.force_login(primary)
    response = client.post(
        reverse("duty_roster:revert_instruction_response", kwargs={"slot_id": slot.pk})
    )

    assert response.status_code == 302
    messages = [m.message for m in get_messages(response.wsgi_request)]
    assert "This request is already cancelled." in messages


@pytest.mark.django_db
def test_unassigned_instructor_can_view_student_request_details(
    client, django_user_model
):
    _ensure_full_member_status()
    assigned = _make_member(django_user_model, "assigned_instr", instructor=True)
    viewer = _make_member(django_user_model, "viewer_instr", instructor=True)
    student = _make_member(django_user_model, "detail_student")
    assignment = _make_assignment(assigned, date_offset=14)

    pending_note = "Need WINGS check items and pre-solo landing pattern practice."
    accepted_note = "Working toward consistency for checkride prep and radio calls."

    InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor_response="pending",
        status="pending",
        instruction_types=["wings", "pre_solo"],
        student_notes=pending_note,
    )
    InstructionSlot.objects.create(
        assignment=_make_assignment(assigned, date_offset=21),
        student=_make_member(django_user_model, "detail_student_accepted"),
        instructor=assigned,
        instructor_response="accepted",
        status="confirmed",
        instruction_types=["checkride_prep"],
        student_notes=accepted_note,
    )

    client.force_login(viewer)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert pending_note in content
    assert accepted_note in content
    assert "WINGS Program" in content
    assert "Pre-Solo Practice" in content
    assert "Checkride Preparation" in content


@pytest.mark.django_db
def test_unassigned_instructor_gets_read_only_controls(client, django_user_model):
    _ensure_full_member_status()
    assigned = _make_member(django_user_model, "readonly_assigned", instructor=True)
    viewer = _make_member(django_user_model, "readonly_viewer", instructor=True)
    student = _make_member(django_user_model, "readonly_student")
    assignment = _make_assignment(assigned, date_offset=18)

    pending_slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor_response="pending",
        status="pending",
        student_notes="Need a brief field check refresher.",
    )
    accepted_slot = InstructionSlot.objects.create(
        assignment=_make_assignment(assigned, date_offset=19),
        student=_make_member(django_user_model, "readonly_student_accepted"),
        instructor=assigned,
        instructor_response="accepted",
        status="confirmed",
        student_notes="Accepted student request details.",
    )

    client.force_login(viewer)
    response = client.get(reverse("duty_roster:instructor_requests"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Read only" in content
    assert (
        reverse("duty_roster:instructor_respond", kwargs={"slot_id": pending_slot.pk})
        not in content
    )
    assert (
        reverse(
            "duty_roster:revert_instruction_response",
            kwargs={"slot_id": accepted_slot.pk},
        )
        not in content
    )
