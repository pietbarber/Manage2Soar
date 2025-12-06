"""
Tests for instruction report email delivery.

Tests the email notifications sent after an instructor fills out an instruction report:
- Email sent to student
- CC to instructors mailing list if configured
- New qualifications included
- Update vs new report distinction
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import override_settings

from instructors.models import (
    ClubQualificationType,
    InstructionReport,
    LessonScore,
    MemberQualification,
    TrainingLesson,
)
from instructors.utils import send_instruction_report_email
from members.models import Member
from siteconfig.models import MailingList, MailingListCriterion, SiteConfiguration


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
def instructor_member(db):
    """Create test instructor member."""
    return Member.objects.create(
        username="john_instructor",
        first_name="John",
        last_name="Instructor",
        email="john.instructor@example.com",
        membership_status="Full Member",
        instructor=True,
        is_active=True,
    )


@pytest.fixture
def second_instructor(db):
    """Create a second instructor for testing CC list."""
    return Member.objects.create(
        username="jane_instructor",
        first_name="Jane",
        last_name="Trainer",
        email="jane.trainer@example.com",
        membership_status="Full Member",
        instructor=True,
        is_active=True,
    )


@pytest.fixture
def student_member(db):
    """Create test student member."""
    return Member.objects.create(
        username="sally_student",
        first_name="Sally",
        last_name="Student",
        email="sally.student@example.com",
        membership_status="Student",
        is_active=True,
    )


@pytest.fixture
def student_no_email(db):
    """Create test student without email."""
    return Member.objects.create(
        username="no_email_student",
        first_name="NoEmail",
        last_name="Student",
        membership_status="Student",
        email="",
        is_active=True,
    )


@pytest.fixture
def training_lesson(db):
    """Create a test training lesson."""
    return TrainingLesson.objects.create(
        code="1a",
        title="Preflight Inspection",
        description="How to inspect the glider before flight.",
    )


@pytest.fixture
def instruction_report(db, student_member, instructor_member):
    """Create a test instruction report."""
    return InstructionReport.objects.create(
        student=student_member,
        instructor=instructor_member,
        report_date=date.today(),
        report_text="<p>Good flight today. Student is progressing well.</p>",
    )


@pytest.fixture
def lesson_score(db, instruction_report, training_lesson):
    """Create a lesson score for the instruction report."""
    return LessonScore.objects.create(
        report=instruction_report,
        lesson=training_lesson,
        score="3",  # Solo Standard
    )


@pytest.fixture
def qualification_type(db):
    """Create a test qualification type."""
    return ClubQualificationType.objects.create(
        code="SOLO",
        name="Solo Approved",
        tooltip="Student is approved for solo flights.",
    )


@pytest.fixture
def member_qualification(db, student_member, qualification_type, instructor_member):
    """Create a member qualification for testing."""
    return MemberQualification.objects.create(
        member=student_member,
        qualification=qualification_type,
        is_qualified=True,
        instructor=instructor_member,
        date_awarded=date.today(),
    )


@pytest.fixture
def instructors_mailing_list(db):
    """Create an instructors mailing list."""
    return MailingList.objects.create(
        name="instructors",
        description="All instructors",
        is_active=True,
        criteria=[MailingListCriterion.INSTRUCTOR],
    )


@pytest.fixture
def active_membership_status(db):
    """Create an active membership status for MailingList queries."""
    from siteconfig.models import MembershipStatus

    # Create the membership statuses that the MailingList queries need
    MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={"is_active": True, "sort_order": 10},
    )
    MembershipStatus.objects.get_or_create(
        name="Student",
        defaults={"is_active": True, "sort_order": 20},
    )


class TestInstructionReportEmail:
    """Tests for send_instruction_report_email function."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_email_sent_to_student(self, site_config, instruction_report, lesson_score):
        """Test that instruction report email is sent to student."""
        mail.outbox.clear()

        result = send_instruction_report_email(instruction_report, is_update=False)

        assert result == 1
        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert instruction_report.student.email in email.to
        assert "Instruction Report" in email.subject
        assert instruction_report.student.first_name in email.subject

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_email_contains_lesson_scores(
        self, site_config, instruction_report, lesson_score
    ):
        """Test that email contains lesson scores."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        # Check HTML content
        assert lesson_score.lesson.code in email.alternatives[0][0]
        assert lesson_score.lesson.title in email.alternatives[0][0]

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_email_contains_instructor_notes(self, site_config, instruction_report):
        """Test that email contains instructor notes."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        # Check HTML content for report text
        assert "Good flight today" in email.alternatives[0][0]

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_update_subject_prefix(self, site_config, instruction_report):
        """Test that update email has 'Updated:' prefix."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report, is_update=True)

        email = mail.outbox[0]
        assert email.subject.startswith("Updated:")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_update_banner_in_email(self, site_config, instruction_report):
        """Test that update email contains update banner."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report, is_update=True)

        email = mail.outbox[0]
        # Check HTML content for update notice
        assert "update" in email.alternatives[0][0].lower()
        assert "previously submitted" in email.alternatives[0][0].lower()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_new_qualification_in_email(
        self, site_config, instruction_report, member_qualification
    ):
        """Test that new qualification is included in email."""
        mail.outbox.clear()

        send_instruction_report_email(
            instruction_report,
            new_qualifications=[member_qualification],
        )

        email = mail.outbox[0]
        # Check HTML content for qualification
        assert member_qualification.qualification.name in email.alternatives[0][0]
        assert "Awarded" in email.alternatives[0][0]

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_no_email_for_student_without_email(
        self, site_config, student_no_email, instructor_member
    ):
        """Test that no email is sent if student has no email address."""
        report = InstructionReport.objects.create(
            student=student_no_email,
            instructor=instructor_member,
            report_date=date.today(),
        )
        mail.outbox.clear()

        result = send_instruction_report_email(report)

        assert result == 0
        assert len(mail.outbox) == 0

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_cc_instructors_mailing_list(
        self,
        site_config,
        instruction_report,
        instructors_mailing_list,
        instructor_member,
        second_instructor,
        active_membership_status,
    ):
        """Test that instructors mailing list is CC'd."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        # Student should be in TO
        assert instruction_report.student.email in email.to
        # Instructors should be in CC (at least one)
        assert email.cc is not None
        assert len(email.cc) > 0

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_student_not_in_cc_if_also_instructor(
        self,
        site_config,
        instructors_mailing_list,
        instructor_member,
        active_membership_status,
    ):
        """Test that student is not CC'd if they happen to be on instructors list."""
        # Make the instructor a student for this report
        student_instructor = instructor_member
        other_instructor = Member.objects.create(
            username="other_instructor",
            first_name="Other",
            last_name="Instructor",
            email="other@example.com",
            membership_status="Full Member",
            instructor=True,
            is_active=True,
        )
        report = InstructionReport.objects.create(
            student=student_instructor,
            instructor=other_instructor,
            report_date=date.today(),
        )
        mail.outbox.clear()

        send_instruction_report_email(report)

        email = mail.outbox[0]
        # Student should be in TO
        assert student_instructor.email in email.to
        # Student should NOT be in CC
        if email.cc:
            assert student_instructor.email not in email.cc

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_no_cc_when_no_instructors_list(self, site_config, instruction_report):
        """Test that no CC is added when no instructors mailing list exists."""
        # Ensure no instructors mailing list exists
        MailingList.objects.filter(name__iexact="instructors").delete()
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        assert email.cc is None or len(email.cc) == 0

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_simulator_session_noted(
        self, site_config, student_member, instructor_member
    ):
        """Test that simulator session is noted in email."""
        report = InstructionReport.objects.create(
            student=student_member,
            instructor=instructor_member,
            report_date=date.today(),
            simulator=True,
        )
        mail.outbox.clear()

        send_instruction_report_email(report)

        email = mail.outbox[0]
        # Check for simulator mention in HTML
        assert "simulator" in email.alternatives[0][0].lower()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_from_email_uses_domain(self, site_config, instruction_report):
        """Test that from email uses configured domain."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        assert f"noreply@{site_config.domain_name}" == email.from_email

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
    )
    def test_logbook_url_in_email(self, site_config, instruction_report):
        """Test that logbook URL is included in email."""
        mail.outbox.clear()

        send_instruction_report_email(instruction_report)

        email = mail.outbox[0]
        expected_url = f"/instructors/logbook/{instruction_report.student.id}/"
        assert expected_url in email.alternatives[0][0]
