"""
Regression tests for DutyAssignment.active_instruction_slots (issue #668).

Verifies that cancelled instruction requests are excluded from the property
used to count and list students in the calendar agenda and day modal templates.
"""

from datetime import date, timedelta

import pytest

from duty_roster.models import DutyAssignment, InstructionSlot
from members.models import Member


@pytest.fixture
def tomorrow():
    return date.today() + timedelta(days=1)


@pytest.fixture
def instructor(db):
    return Member.objects.create(
        username="test_instructor",
        first_name="Jane",
        last_name="Instructor",
        email="instructor@example.com",
        membership_status="Full Member",
        instructor=True,
    )


@pytest.fixture
def assignment(db, tomorrow, instructor):
    return DutyAssignment.objects.create(
        date=tomorrow,
        instructor=instructor,
    )


def _make_student(n):
    return Member.objects.create(
        username=f"student{n}",
        first_name=f"Student{n}",
        last_name="Test",
        email=f"student{n}@example.com",
        membership_status="Full Member",
    )


def _make_slot(assignment, student, status="pending"):
    return InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        status=status,
    )


class TestActiveInstructionSlots:
    """DutyAssignment.active_instruction_slots excludes cancelled slots."""

    def test_active_slots_excludes_cancelled(self, db, assignment):
        """Cancelled slot must not appear in active_instruction_slots."""
        student_a = _make_student(1)
        student_b = _make_student(2)
        _make_slot(assignment, student_a, status="pending")
        _make_slot(assignment, student_b, status="cancelled")

        active = list(assignment.active_instruction_slots)
        student_ids = [s.student_id for s in active]

        assert student_a.pk in student_ids
        assert student_b.pk not in student_ids

    def test_active_slots_count_matches_list(self, db, assignment):
        """Count must equal length of list — the root cause of issue #668."""
        student_a = _make_student(1)
        student_b = _make_student(2)
        student_c = _make_student(3)
        _make_slot(assignment, student_a, status="pending")
        _make_slot(assignment, student_b, status="confirmed")
        _make_slot(assignment, student_c, status="cancelled")  # should not be counted

        active = list(assignment.active_instruction_slots)
        assert (
            len(active) == 2
        ), "Count must only include non-cancelled slots (issue #668)"

    def test_all_cancelled_returns_empty(self, db, assignment):
        """When all requests are cancelled the queryset must be empty so the
        'Students Requesting Instruction' section is hidden in the template."""
        student_a = _make_student(1)
        student_b = _make_student(2)
        _make_slot(assignment, student_a, status="cancelled")
        _make_slot(assignment, student_b, status="cancelled")

        assert not assignment.active_instruction_slots.exists()

    def test_no_slots_returns_empty(self, db, assignment):
        """Assignment with no instruction requests at all must return empty."""
        assert not assignment.active_instruction_slots.exists()

    def test_select_related_student_populated(self, db, assignment):
        """active_instruction_slots must have student already fetched to avoid
        N+1 queries when templates access slot.student.full_display_name."""
        student = _make_student(1)
        _make_slot(assignment, student, status="pending")

        slots = list(assignment.active_instruction_slots)
        assert len(slots) == 1
        # Accessing student on a select_related queryset must not hit the DB again.
        # (The object is already cached on the instance.)
        assert slots[0].student_id == student.pk
        assert slots[0].student.full_display_name  # should not raise or re-query
