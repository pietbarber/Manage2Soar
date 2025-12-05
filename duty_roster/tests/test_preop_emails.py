"""
Tests for send_duty_preop_emails management command.

Tests the HTML email generation with all the new features:
- HTML and plain text templates
- Students requesting instruction
- Members planning to fly (ops intent)
- Site configuration (logo, club name)
- Role titles from siteconfig
"""

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from duty_roster.models import DutyAssignment, InstructionSlot, OpsIntent
from logsheet.models import Glider, MaintenanceDeadline, MaintenanceIssue, Towplane
from members.models import Member
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
def members(db):
    """Create test members for duty assignments."""
    instructor = Member.objects.create(
        username="john_instructor",
        first_name="John",
        last_name="Instructor",
        email="john@example.com",
        membership_status="Full Member",
    )
    tow_pilot = Member.objects.create(
        username="jane_towpilot",
        first_name="Jane",
        last_name="Towpilot",
        email="jane@example.com",
        membership_status="Full Member",
    )
    duty_officer = Member.objects.create(
        username="bob_officer",
        first_name="Bob",
        last_name="Officer",
        email="bob@example.com",
        membership_status="Full Member",
    )
    student = Member.objects.create(
        username="sally_student",
        first_name="Sally",
        last_name="Student",
        email="sally@example.com",
        membership_status="Student",
    )
    private_owner = Member.objects.create(
        username="pete_private",
        first_name="Pete",
        last_name="Private",
        email="pete@example.com",
        membership_status="Full Member",
    )
    return {
        "instructor": instructor,
        "tow_pilot": tow_pilot,
        "duty_officer": duty_officer,
        "student": student,
        "private_owner": private_owner,
    }


@pytest.fixture
def tomorrow():
    """Return tomorrow's date."""
    return date.today() + timedelta(days=1)


@pytest.fixture
def duty_assignment(db, members, tomorrow):
    """Create a duty assignment for tomorrow."""
    return DutyAssignment.objects.create(
        date=tomorrow,
        is_scheduled=True,
        instructor=members["instructor"],
        tow_pilot=members["tow_pilot"],
        duty_officer=members["duty_officer"],
    )


@pytest.fixture
def glider(db):
    """Create a test glider."""
    return Glider.objects.create(
        competition_number="TS",
        n_number="N12345",
        make="Schleicher",
        model="ASK-21",
    )


@pytest.fixture
def towplane(db):
    """Create a test towplane."""
    return Towplane.objects.create(
        n_number="N54321",
        name="Test Towplane",
    )


@pytest.mark.django_db
class TestSendDutyPreopEmails:
    """Tests for the send_duty_preop_emails management command."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_sends_html_email(self, site_config, duty_assignment, tomorrow):
        """Test that command sends HTML email with proper structure."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        # Check email was sent
        assert len(mail.outbox) == 1
        email = mail.outbox[0]

        # Check basic email properties
        assert f"Pre-Ops Report for {tomorrow}" in email.subject
        assert email.from_email == "noreply@test.com"
        assert len(email.to) == 3  # instructor, tow_pilot, duty_officer

        # Check HTML content exists
        assert len(email.alternatives) == 1
        html_content = email.alternatives[0][0]
        assert "text/html" in email.alternatives[0][1]

        # Check HTML structure
        assert "Pre-Operations Report" in html_content
        assert "Test Soaring Club" in html_content
        assert "Assigned Duty Crew" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_duty_crew(self, site_config, duty_assignment, members, tomorrow):
        """Test that all duty crew members are listed in the email."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Check crew members are listed
        assert "John Instructor" in html_content
        assert "Jane Towpilot" in html_content
        assert "Bob Officer" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_instruction_requests(
        self, site_config, duty_assignment, members, tomorrow
    ):
        """Test that students requesting instruction are listed."""
        # Create an instruction request
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=members["student"],
            status="confirmed",
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        assert "Students Requesting Instruction" in html_content
        assert "Sally Student" in html_content
        assert "confirmed" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_ops_intent(
        self, site_config, duty_assignment, members, glider, tomorrow
    ):
        """Test that members planning to fly are listed."""
        # Create an ops intent
        OpsIntent.objects.create(
            member=members["private_owner"],
            date=tomorrow,
            available_as=["private"],
            glider=glider,
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        assert "Members Planning to Fly" in html_content
        assert "Pete Private" in html_content
        assert "Private glider" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_grounded_aircraft(
        self, site_config, duty_assignment, glider, towplane, tomorrow
    ):
        """Test that grounded aircraft are listed."""
        # Create grounded issues
        MaintenanceIssue.objects.create(
            glider=glider,
            description="Canopy crack",
            grounded=True,
            resolved=False,
        )
        MaintenanceIssue.objects.create(
            towplane=towplane,
            description="Engine issue",
            grounded=True,
            resolved=False,
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        assert "Grounded Aircraft" in html_content
        assert "Canopy crack" in html_content
        assert "Engine issue" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_maintenance_deadlines(
        self, site_config, duty_assignment, glider, tomorrow
    ):
        """Test that upcoming maintenance deadlines are listed."""
        MaintenanceDeadline.objects.create(
            glider=glider,
            description="Annual inspection",
            due_date=tomorrow + timedelta(days=15),
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        assert "Maintenance Deadlines" in html_content
        assert "Annual inspection" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_includes_duty_roster_url(self, site_config, duty_assignment, tomorrow):
        """Test that the duty roster URL is included."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        assert "View Duty Roster" in html_content
        assert "https://test.manage2soar.com/duty_roster/calendar/" in html_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_no_emojis_in_output(self, site_config, duty_assignment, tomorrow):
        """Test that no emojis are present in the email."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]
        text_content = email.body

        # Common emojis that were in the old version
        emojis = ["🚨", "👥", "🎓", "🛩️", "📋", "💪", "🛑", "🗓️", "❌", "✅", "⚠️"]
        for emoji in emojis:
            assert emoji not in html_content, f"Found emoji {emoji} in HTML"
            assert emoji not in text_content, f"Found emoji {emoji} in text"

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_no_scheduled_ops(self, site_config, tomorrow):
        """Test that command handles no scheduled ops gracefully."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        output = out.getvalue()
        assert "No scheduled ops" in output
        assert len(mail.outbox) == 0

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_plain_text_fallback(self, site_config, duty_assignment, tomorrow):
        """Test that plain text version is included for email clients that don't support HTML."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        text_content = email.body

        # Check plain text has required sections
        assert "ASSIGNED DUTY CREW" in text_content
        assert "John Instructor" in text_content
        assert "View the full duty roster" in text_content

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=True,
        EMAIL_DEV_MODE_REDIRECT_TO="dev@example.com",
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_dev_mode_redirect(self, site_config, duty_assignment, tomorrow):
        """Test that dev mode redirects emails properly."""
        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        # In dev mode, email goes to dev address
        assert email.to == ["dev@example.com"]
        # Subject includes dev mode indicator
        assert "[DEV MODE]" in email.subject

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        SITE_URL="https://test.manage2soar.com",
    )
    def test_from_email_fallback(self, site_config, duty_assignment, tomorrow):
        """Test that from_email falls back to domain from site config."""
        # Remove DEFAULT_FROM_EMAIL to test fallback
        with override_settings(DEFAULT_FROM_EMAIL=None):
            out = StringIO()
            call_command(
                "send_duty_preop_emails",
                date=tomorrow.strftime("%Y-%m-%d"),
                stdout=out,
            )

            email = mail.outbox[0]
            assert "noreply@test.manage2soar.com" in email.from_email

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_cc_students_requesting_instruction(
        self, site_config, duty_assignment, members, tomorrow
    ):
        """Test that students requesting instruction are CC'd on the email."""
        # Create an instruction slot for the student
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=members["student"],
            status="confirmed",
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        # Student should be CC'd
        assert members["student"].email in email.cc

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_cc_ops_intent_members(
        self, site_config, duty_assignment, members, glider, tomorrow
    ):
        """Test that members with ops intent are CC'd on the email."""
        # Create an ops intent
        OpsIntent.objects.create(
            member=members["private_owner"],
            date=tomorrow,
            available_as=["private"],
            glider=glider,
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        # Private owner should be CC'd
        assert members["private_owner"].email in email.cc

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=False,
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_cc_excludes_duplicates_and_duty_crew(
        self, site_config, duty_assignment, members, tomorrow
    ):
        """Test that CC list excludes duplicates and members already in to_emails."""
        # Create instruction slot for the instructor (who is already in duty crew)
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=members["instructor"],  # Instructor is already a TO recipient
            status="confirmed",
        )
        # Also create a slot for a regular student
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=members["student"],
            status="pending",
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        # Instructor should NOT be in CC (already in TO)
        assert members["instructor"].email not in email.cc
        # Student should be in CC
        assert members["student"].email in email.cc

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_DEV_MODE=True,
        EMAIL_DEV_MODE_REDIRECT_TO="dev@example.com",
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_URL="https://test.manage2soar.com",
    )
    def test_cc_in_dev_mode(self, site_config, duty_assignment, members, tomorrow):
        """Test that CC functionality works correctly in dev mode."""
        # Create an instruction slot
        InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=members["student"],
            status="confirmed",
        )

        out = StringIO()
        call_command(
            "send_duty_preop_emails",
            date=tomorrow.strftime("%Y-%m-%d"),
            stdout=out,
        )

        email = mail.outbox[0]
        # In dev mode, TO should be redirected
        assert email.to == ["dev@example.com"]
        # In dev mode, CC should be cleared (redirected to TO)
        assert email.cc == []
        # Subject should indicate dev mode and include original recipients info
        assert "[DEV MODE]" in email.subject
        assert "TO:" in email.subject
