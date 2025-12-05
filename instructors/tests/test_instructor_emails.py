"""
Tests for instructor email notifications.

Tests the email notifications for:
- Student signup notification to instructors (signal-based)
- Accept/reject confirmation to students (signal-based)
- 48-hour summary email (management command)
"""

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from duty_roster.models import DutyAssignment, InstructionSlot
from instructors.models import StudentProgressSnapshot
from members.models import Member
from notifications.models import Notification
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create site configuration for tests."""
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        club_nickname="Test Club",
        domain_name="test.manage2soar.com",
        club_abbreviation="TSC",
        duty_officer_title="Duty Officer",
        assistant_duty_officer_title="Assistant DO",
        towpilot_title="Tow Pilot",
        instructor_title="Instructor",
    )


@pytest.fixture
def instructor(db):
    """Create test instructor member."""
    return Member.objects.create(
        username="john_instructor",
        first_name="John",
        last_name="Instructor",
        email="john@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def surge_instructor(db):
    """Create surge instructor member."""
    return Member.objects.create(
        username="jane_surge",
        first_name="Jane",
        last_name="Surge",
        email="jane@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def student(db):
    """Create test student member."""
    return Member.objects.create(
        username="sally_student",
        first_name="Sally",
        last_name="Student",
        email="sally@example.com",
        membership_status="Student",
    )


@pytest.fixture
def tomorrow():
    """Return tomorrow's date."""
    return date.today() + timedelta(days=1)


@pytest.fixture
def in_two_days():
    """Return date 2 days from now."""
    return date.today() + timedelta(days=2)


@pytest.fixture
def duty_assignment(db, instructor, surge_instructor, tomorrow):
    """Create a duty assignment for tomorrow."""
    return DutyAssignment.objects.create(
        date=tomorrow,
        is_scheduled=True,
        instructor=instructor,
        surge_instructor=surge_instructor,
    )


@pytest.fixture
def duty_assignment_in_two_days(db, instructor, in_two_days):
    """Create a duty assignment 2 days from now."""
    return DutyAssignment.objects.create(
        date=in_two_days,
        is_scheduled=True,
        instructor=instructor,
    )


@pytest.fixture
def student_progress(db, student):
    """Create progress snapshot for student."""
    return StudentProgressSnapshot.objects.create(
        student=student,
        solo_progress=0.65,
        checkride_progress=0.3,
        sessions=12,
    )


@pytest.mark.django_db
class TestStudentSignupNotification:
    """Tests for student signup notification signals."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_sends_email_on_instruction_slot_creation(
        self, site_config, duty_assignment, student
    ):
        """Test that creating an InstructionSlot sends email to instructor."""
        mail.outbox.clear()

        # Create instruction slot - should trigger signal
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student,
            status="pending",
        )

        # Should send to both instructor and surge instructor
        assert len(mail.outbox) == 2

        # Check first email (to primary instructor)
        email = mail.outbox[0]
        assert "john@example.com" in email.to
        assert "Sally" in email.subject
        assert "instruction request" in email.subject.lower()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_email_contains_student_info(
        self, site_config, duty_assignment, student, student_progress
    ):
        """Test that notification email includes student progress info."""
        mail.outbox.clear()

        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student,
            status="pending",
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Check student name
        assert "Sally Student" in html_content

        # Check progress info is included
        assert "65%" in html_content  # solo progress
        assert "30%" in html_content  # checkride progress

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_creates_in_system_notification(
        self, site_config, duty_assignment, student, instructor
    ):
        """Test that signup also creates in-system notification."""
        Notification.objects.all().delete()

        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student,
            status="pending",
        )

        # Check notification was created for instructor
        notifications = Notification.objects.filter(user=instructor)
        assert notifications.exists()
        assert "Sally" in notifications.first().message

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_no_email_for_confirmed_slot(self, site_config, duty_assignment, student):
        """Test that confirmed slots (not new pending requests) don't trigger email."""
        mail.outbox.clear()

        # Create already-confirmed slot
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student,
            status="confirmed",
        )

        # Should not send signup notification (only pending triggers it)
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestAcceptRejectNotification:
    """Tests for accept/reject email notifications."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_sends_email_on_accept(
        self, site_config, duty_assignment, student, instructor
    ):
        """Test that accepting a slot sends email to student."""
        # Create slot without triggering signal (bypass signals for setup)
        slot = InstructionSlot(
            assignment=duty_assignment,
            student=student,
            status="pending",
            instructor_response="pending",
        )
        slot.save()  # This triggers signup notification

        mail.outbox.clear()

        # Accept the slot
        slot.accept(instructor, note="Looking forward to flying with you!")

        # Should send acceptance email to student
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert "sally@example.com" in email.to
        assert "confirmed" in email.subject.lower()

        # Check HTML content
        html_content = email.alternatives[0][0]
        assert "Looking forward to flying with you!" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_sends_email_on_reject(self, site_config, duty_assignment, student):
        """Test that rejecting a slot sends email to student."""
        slot = InstructionSlot(
            assignment=duty_assignment,
            student=student,
            status="pending",
            instructor_response="pending",
        )
        slot.save()

        mail.outbox.clear()

        # Reject the slot
        slot.reject(note="Sorry, schedule is full today")

        # Should send rejection email to student
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert "sally@example.com" in email.to

        # Check HTML content
        html_content = email.alternatives[0][0]
        assert "Sorry, schedule is full today" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_creates_in_system_notification_for_student(
        self, site_config, duty_assignment, student, instructor
    ):
        """Test that accept/reject creates in-system notification for student."""
        slot = InstructionSlot(
            assignment=duty_assignment,
            student=student,
            status="pending",
            instructor_response="pending",
        )
        slot.save()

        Notification.objects.filter(user=student).delete()

        slot.accept(instructor)

        # Check notification was created for student
        notifications = Notification.objects.filter(user=student)
        assert notifications.exists()
        assert "John" in notifications.first().message


@pytest.mark.django_db
class TestInstructorSummaryCommand:
    """Tests for send_instructor_summary_emails management command."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_sends_summary_email(
        self, site_config, duty_assignment_in_two_days, student, in_two_days
    ):
        """Test that summary command sends email to instructor."""
        # Create instruction slot for the day
        InstructionSlot.objects.create(
            assignment=duty_assignment_in_two_days,
            student=student,
            status="pending",
        )

        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        # Should send to instructor
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert "john@example.com" in email.to
        assert "student" in email.subject.lower()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_student_progress(
        self,
        site_config,
        duty_assignment_in_two_days,
        student,
        student_progress,
        in_two_days,
    ):
        """Test that summary includes student progress info."""
        InstructionSlot.objects.create(
            assignment=duty_assignment_in_two_days,
            student=student,
            status="confirmed",
        )

        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Check progress info
        assert "65%" in html_content
        assert "30%" in html_content
        assert "Sally Student" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_dry_run_mode(
        self, site_config, duty_assignment_in_two_days, student, in_two_days
    ):
        """Test that dry-run mode doesn't send emails."""
        InstructionSlot.objects.create(
            assignment=duty_assignment_in_two_days,
            student=student,
            status="pending",
        )

        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            dry_run=True,
            stdout=out,
        )

        # Should not send any emails
        assert len(mail.outbox) == 0
        assert "Would send" in out.getvalue()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_no_scheduled_ops(self, site_config, in_two_days):
        """Test behavior when no ops scheduled."""
        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        assert len(mail.outbox) == 0
        assert "No scheduled ops" in out.getvalue()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_subject_line_no_students(
        self, site_config, duty_assignment_in_two_days, in_two_days
    ):
        """Test subject line when no students scheduled."""
        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        assert "No students" in email.subject

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_club_branding(
        self, site_config, duty_assignment_in_two_days, in_two_days
    ):
        """Test that email includes club name."""
        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]
        assert "Test Soaring Club" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_pending_count_reminder(
        self, site_config, duty_assignment_in_two_days, student, in_two_days
    ):
        """Test that summary email includes pending count action reminder."""
        # Create a pending instruction slot
        InstructionSlot.objects.create(
            assignment=duty_assignment_in_two_days,
            student=student,
            status="pending",
        )

        mail.outbox.clear()

        out = StringIO()
        call_command(
            "send_instructor_summary_emails",
            date=in_two_days.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Check pending action reminder is shown
        assert "Action Required" in html_content
        assert "1 pending instruction request" in html_content
