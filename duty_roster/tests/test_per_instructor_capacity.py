"""
Tests for per-instructor capacity and unassigned-slot behaviour when a surge
instructor is present (Issue #665).

Covers:
- InstructionRequestForm.save(): slots are unassigned when both instructors present
- InstructionRequestForm.clean(): capacity blocks when total slots are full
- instructor_respond view: per-instructor capacity check on accept
- _check_surge_instructor_needed: does not re-trigger when surge already assigned
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse

from duty_roster.forms import InstructionRequestForm
from duty_roster.models import DutyAssignment, InstructionSlot
from siteconfig.models import SiteConfiguration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_site_config(instruction_surge_threshold=4):
    return SiteConfiguration.objects.create(
        club_name="Sky Club",
        domain_name="sky.org",
        club_abbreviation="SC",
        instructors_email="instructors@sky.org",
        instruction_surge_threshold=instruction_surge_threshold,
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


def _make_assignment(primary, date_offset=60, surge=None):
    test_date = date.today() + timedelta(days=date_offset)
    a = DutyAssignment.objects.create(date=test_date, instructor=primary)
    if surge:
        a.surge_instructor = surge
        a.save(update_fields=["surge_instructor"])
    return a


def _make_accepted_slot(assignment, student, instructor):
    return InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=instructor,
        instructor_response="accepted",
        status="confirmed",
    )


# ---------------------------------------------------------------------------
# InstructionRequestForm.save() — slot assignment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_creates_unassigned_slot_when_both_instructors_present(
    django_user_model,
):
    """When both primary and surge are assigned, new sign-up slot has instructor=None."""
    _make_site_config()
    primary = _make_member(django_user_model, "cp_p1", instructor=True)
    surge = _make_member(django_user_model, "cp_s1", instructor=True)
    student = _make_member(django_user_model, "cp_st1")
    assignment = _make_assignment(primary, date_offset=60, surge=surge)

    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=student,
    )
    assert form.is_valid(), form.errors
    slot = form.save()
    assert slot.instructor is None


@pytest.mark.django_db
def test_signup_assigns_primary_when_no_surge(django_user_model):
    """When only the primary instructor is assigned, slot.instructor = primary."""
    _make_site_config()
    primary = _make_member(django_user_model, "cp_p2", instructor=True)
    student = _make_member(django_user_model, "cp_st2")
    assignment = _make_assignment(primary, date_offset=61)  # no surge

    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=student,
    )
    assert form.is_valid(), form.errors
    slot = form.save()
    assert slot.instructor == primary


@pytest.mark.django_db
def test_signup_assigns_surge_when_only_surge_present(django_user_model):
    """Edge case: only surge instructor assigned (no primary) → slot.instructor = surge."""
    _make_site_config()
    surge = _make_member(django_user_model, "cp_s2", instructor=True)
    student = _make_member(django_user_model, "cp_st3")
    # Create assignment with no primary; set surge manually
    test_date = date.today() + timedelta(days=62)
    assignment = DutyAssignment.objects.create(
        date=test_date, instructor=None, surge_instructor=surge
    )

    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=student,
    )
    assert form.is_valid(), form.errors
    slot = form.save()
    assert slot.instructor == surge


# ---------------------------------------------------------------------------
# InstructionRequestForm.clean() — capacity blocking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_blocked_when_both_instructors_at_capacity(django_user_model):
    """Student cannot sign up when total accepted == 2 * threshold (both instructors full)."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_p3", instructor=True)
    surge = _make_member(django_user_model, "cp_s3", instructor=True)
    assignment = _make_assignment(primary, date_offset=63, surge=surge)

    # Fill both instructors' combined capacity (2 * 2 = 4 accepted slots)
    for i in range(4):
        s = _make_member(django_user_model, f"cp_full_{i}")
        instr = primary if i < 2 else surge
        _make_accepted_slot(assignment, s, instr)

    new_student = _make_member(django_user_model, "cp_new1")
    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=new_student,
    )
    assert not form.is_valid()
    errors = str(form.errors)
    assert "fully booked" in errors


@pytest.mark.django_db
def test_signup_allowed_when_surge_present_and_capacity_not_reached(django_user_model):
    """Student can sign up if total accepted < 2 * threshold, even if primary is full."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_p4", instructor=True)
    surge = _make_member(django_user_model, "cp_s4", instructor=True)
    assignment = _make_assignment(primary, date_offset=64, surge=surge)

    # Fill only primary (2 accepted); surge still has room → total = 2 < 4
    for i in range(2):
        s = _make_member(django_user_model, f"cp_half_{i}")
        _make_accepted_slot(assignment, s, primary)

    new_student = _make_member(django_user_model, "cp_new2")
    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=new_student,
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_signup_blocked_when_single_instructor_at_capacity(django_user_model):
    """Student cannot sign up when single instructor has accepted >= threshold."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_p5", instructor=True)
    assignment = _make_assignment(primary, date_offset=65)  # no surge

    for i in range(2):
        s = _make_member(django_user_model, f"cp_sing_{i}")
        _make_accepted_slot(assignment, s, primary)

    new_student = _make_member(django_user_model, "cp_new3")
    form = InstructionRequestForm(
        {"instruction_types": [], "student_notes": ""},
        assignment=assignment,
        student=new_student,
    )
    assert not form.is_valid()
    errors = str(form.errors)
    assert "fully booked" in errors


# ---------------------------------------------------------------------------
# instructor_respond view — per-instructor capacity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_instructor_blocked_when_at_own_capacity_with_surge(client, django_user_model):
    """Primary instructor cannot accept a student once their own queue is full."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_vp1", instructor=True)
    surge = _make_member(django_user_model, "cp_vs1", instructor=True)
    student = _make_member(django_user_model, "cp_vst1")
    new_student = _make_member(django_user_model, "cp_vst2")
    assignment = _make_assignment(primary, date_offset=66, surge=surge)

    # Fill primary's capacity (2 students)
    for i in range(2):
        s = _make_member(django_user_model, f"cp_vcap_{i}")
        _make_accepted_slot(assignment, s, primary)

    # Pending slot for new_student (still unassigned)
    pending_slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=new_student,
        instructor=None,
        instructor_response="pending",
        status="pending",
    )

    client.force_login(primary)
    url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": pending_slot.id})
    response = client.post(url, {"action": "accept"})

    assert response.status_code == 302
    pending_slot.refresh_from_db()
    # Should NOT have been accepted
    assert pending_slot.instructor_response == "pending"


@pytest.mark.django_db
def test_instructor_can_accept_when_under_capacity_with_surge(
    client, django_user_model
):
    """Primary instructor can accept a student when below their own capacity."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_vp2", instructor=True)
    surge = _make_member(django_user_model, "cp_vs2", instructor=True)
    student = _make_member(django_user_model, "cp_vst3")
    assignment = _make_assignment(primary, date_offset=67, surge=surge)

    pending_slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=None,
        instructor_response="pending",
        status="pending",
    )

    client.force_login(primary)
    url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": pending_slot.id})
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "accept"})

    assert response.status_code == 302
    pending_slot.refresh_from_db()
    assert pending_slot.instructor_response == "accepted"
    assert pending_slot.instructor == primary


@pytest.mark.django_db
def test_surge_instructor_blocked_when_at_own_capacity(client, django_user_model):
    """Surge instructor cannot accept once their own queue is full."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_vp3", instructor=True)
    surge = _make_member(django_user_model, "cp_vs3", instructor=True)
    new_student = _make_member(django_user_model, "cp_vst4")
    assignment = _make_assignment(primary, date_offset=68, surge=surge)

    # Fill surge's capacity
    for i in range(2):
        s = _make_member(django_user_model, f"cp_vsurgecap_{i}")
        _make_accepted_slot(assignment, s, surge)

    pending_slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=new_student,
        instructor=None,
        instructor_response="pending",
        status="pending",
    )

    client.force_login(surge)
    url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": pending_slot.id})
    response = client.post(url, {"action": "accept"})

    assert response.status_code == 302
    pending_slot.refresh_from_db()
    assert pending_slot.instructor_response == "pending"


@pytest.mark.django_db
def test_no_capacity_limit_without_surge(client, django_user_model):
    """Per-instructor capacity check does NOT apply when there is no surge instructor."""
    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_vp4", instructor=True)
    student = _make_member(django_user_model, "cp_vst5")
    # Fill 'capacity' but no surge assigned
    assignment = _make_assignment(primary, date_offset=69)  # no surge
    for i in range(2):
        s = _make_member(django_user_model, f"cp_nosurgecap_{i}")
        _make_accepted_slot(assignment, s, primary)

    pending_slot = InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=primary,
        instructor_response="pending",
        status="pending",
    )

    client.force_login(primary)
    url = reverse("duty_roster:instructor_respond", kwargs={"slot_id": pending_slot.id})
    with patch("duty_roster.views.send_mail") as mock_send:
        mock_send.return_value = 1
        response = client.post(url, {"action": "accept"})

    assert response.status_code == 302
    pending_slot.refresh_from_db()
    # No surge → capacity check skipped → accept succeeds
    assert pending_slot.instructor_response == "accepted"


# ---------------------------------------------------------------------------
# _check_surge_instructor_needed — does not re-trigger with surge present
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_surge_check_does_not_notify_when_surge_already_assigned(django_user_model):
    """_check_surge_instructor_needed is a no-op when surge_instructor is already set."""
    from duty_roster.views import _check_surge_instructor_needed

    _make_site_config(instruction_surge_threshold=2)
    primary = _make_member(django_user_model, "cp_chk1", instructor=True)
    surge = _make_member(django_user_model, "cp_chk2", instructor=True)
    assignment = _make_assignment(primary, date_offset=70, surge=surge)

    # 3 accepted students — would normally trigger surge notification
    for i in range(3):
        s = _make_member(django_user_model, f"cp_chkst_{i}")
        _make_accepted_slot(assignment, s, primary)

    with patch("duty_roster.views._notify_surge_instructor_needed") as mock_notify:
        _check_surge_instructor_needed(assignment)
        mock_notify.assert_not_called()
