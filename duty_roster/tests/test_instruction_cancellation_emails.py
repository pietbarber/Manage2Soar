"""Tests for instructor cancellation notification emails."""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import override_settings

from duty_roster.models import DutyAssignment, InstructionSlot
from duty_roster.views import _notify_instructor_cancellation
from members.models import Member
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create site configuration for email rendering context."""
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
    )


@pytest.fixture
def instructor(db):
    """Create instructor recipient."""
    return Member.objects.create(
        username="instructor",
        first_name="Jane",
        last_name="Instructor",
        email="instructor@example.com",
        membership_status="Full Member",
        instructor=True,
    )


@pytest.fixture
def student(db):
    """Create student who cancels instruction."""
    return Member.objects.create(
        username="student",
        first_name="Sam",
        last_name="Student",
        email="student@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def accepted_slot(db, instructor, student):
    """Create an accepted instruction slot with an assigned instructor."""
    assignment = DutyAssignment.objects.create(
        date=date.today() + timedelta(days=7),
        instructor=instructor,
    )
    return InstructionSlot.objects.create(
        assignment=assignment,
        student=student,
        instructor=instructor,
        status="confirmed",
        instructor_response="accepted",
    )


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_DEV_MODE=False,
    DEFAULT_FROM_EMAIL="noreply@test.manage2soar.com",
    SITE_URL="https://test.manage2soar.com",
)
def test_notify_instructor_cancellation_sends_multipart_email(
    site_config, accepted_slot, instructor, student
):
    """Cancellation notification should include text body and HTML alternative."""
    _notify_instructor_cancellation(accepted_slot)

    assert len(mail.outbox) == 1
    email = mail.outbox[0]

    assert instructor.email in email.to
    assert "Instruction Cancellation" in email.subject
    assert student.full_display_name in email.body
    assert "View Duty Roster" in email.body

    assert len(email.alternatives) == 1
    html_content, mime_type = email.alternatives[0]
    assert mime_type == "text/html"
    assert "Instruction Cancelled" in html_content
    assert student.full_display_name in html_content
