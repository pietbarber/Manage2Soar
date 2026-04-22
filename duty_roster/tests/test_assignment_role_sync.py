from datetime import date

import pytest
from django.core.management import call_command

from duty_roster.models import DutyAssignment, DutyAssignmentRole
from members.models import Member


@pytest.fixture
def instructor_member():
    return Member.objects.create_user(
        username="sync_instructor",
        email="sync_instructor@example.com",
        password="pass",
        membership_status="Full Member",
        instructor=True,
    )


@pytest.fixture
def tow_member():
    return Member.objects.create_user(
        username="sync_tow",
        email="sync_tow@example.com",
        password="pass",
        membership_status="Full Member",
        towpilot=True,
    )


@pytest.mark.django_db
def test_assignment_post_save_syncs_legacy_role_rows(instructor_member):
    assignment = DutyAssignment.objects.create(
        date=date(2026, 4, 5),
        instructor=instructor_member,
    )

    role_row = DutyAssignmentRole.objects.get(
        assignment=assignment, role_key="instructor"
    )
    assert role_row.member == instructor_member
    assert role_row.legacy_role_key == "instructor"


@pytest.mark.django_db
def test_assignment_post_save_removes_legacy_row_when_field_cleared(instructor_member):
    assignment = DutyAssignment.objects.create(
        date=date(2026, 4, 12),
        instructor=instructor_member,
    )
    assert DutyAssignmentRole.objects.filter(
        assignment=assignment,
        role_key="instructor",
    ).exists()

    assignment.instructor = None
    assignment.save(update_fields=["instructor"])

    assert not DutyAssignmentRole.objects.filter(
        assignment=assignment,
        role_key="instructor",
    ).exists()


@pytest.mark.django_db
def test_get_member_for_role_prefers_normalized_row_over_legacy(
    instructor_member, tow_member
):
    assignment = DutyAssignment.objects.create(
        date=date(2026, 4, 19),
        instructor=instructor_member,
    )

    DutyAssignmentRole.objects.update_or_create(
        assignment=assignment,
        role_key="instructor",
        defaults={"member": tow_member, "legacy_role_key": "instructor"},
    )

    assert assignment.get_member_for_role("instructor") == tow_member


@pytest.mark.django_db
def test_backfill_assignment_role_rows_command_repairs_missing_rows(instructor_member):
    assignment = DutyAssignment.objects.create(
        date=date(2026, 4, 26),
        instructor=instructor_member,
    )
    DutyAssignmentRole.objects.filter(
        assignment=assignment, role_key="instructor"
    ).delete()

    call_command("backfill_assignment_role_rows")

    repaired = DutyAssignmentRole.objects.get(
        assignment=assignment, role_key="instructor"
    )
    assert repaired.member == instructor_member
