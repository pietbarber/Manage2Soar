"""
Tests for instruction request notification emails.

Tests the student_signup_notification email with:
- Different content for students vs rated pilots
- Student progress display for students
- Flight currency display for rated pilots
- HTML and plain text templates
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.utils import timezone

from duty_roster.models import DutyAssignment, InstructionSlot
from duty_roster.signals import send_student_signup_notification
from instructors.models import (
    ClubQualificationType,
    MemberQualification,
    StudentProgressSnapshot,
)
from logsheet.models import Airfield, Flight, Glider, Logsheet
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
    )


@pytest.fixture
def instructor(db):
    """Create an instructor member."""
    return Member.objects.create(
        username="instructor",
        first_name="Jane",
        last_name="Instructor",
        email="instructor@example.com",
        membership_status="Full Member",
    )


@pytest.fixture
def student_member(db):
    """Create a student member (no ratings)."""
    return Member.objects.create(
        username="student",
        first_name="John",
        last_name="Student",
        email="student@example.com",
        phone="555-1234",
        membership_status="Full Member",
    )


@pytest.fixture
def rated_pilot(db):
    """Create a rated pilot member."""
    return Member.objects.create(
        username="rated_pilot",
        first_name="Mike",
        last_name="Pilot",
        email="pilot@example.com",
        phone="555-5678",
        membership_status="Full Member",
    )


@pytest.fixture
def private_pilot_qualification(db):
    """Create a private pilot qualification type."""
    return ClubQualificationType.objects.create(
        code="PPL",
        name="Private Pilot License",
        applies_to="rated",
    )


@pytest.fixture
def student_progress(student_member):
    """Create progress snapshot for student."""
    return StudentProgressSnapshot.objects.create(
        student=student_member,
        solo_progress=0.65,
        checkride_progress=0.40,
        sessions=12,
        last_updated=timezone.now(),
    )


@pytest.fixture
def glider(db):
    """Create a test glider."""
    return Glider.objects.create(
        n_number="N123",
        make="Schleicher",
        model="ASK-21",
    )


@pytest.fixture
def logsheet(db):
    """Create a finalized logsheet for flight history."""
    return Logsheet.objects.create(
        log_date=date.today() - timedelta(days=15),
        airfield=Airfield.objects.create(name="Test Field", identifier="KXYZ"),
        created_by=Member.objects.create(
            username="creator",
            first_name="Log",
            last_name="Creator",
            email="creator@example.com",
            membership_status="Full Member",
        ),
        finalized=True,
    )


@pytest.fixture
def duty_assignment(instructor, db):
    """Create a duty assignment for instruction."""
    return DutyAssignment.objects.create(
        date=date.today() + timedelta(days=7),
        instructor=instructor,
    )


@pytest.mark.django_db
class TestStudentInstructionRequestEmail:
    """Tests for student instruction request emails (with progress)."""

    def test_student_email_shows_progress(
        self, site_config, duty_assignment, student_member, student_progress
    ):
        """Student email should show training progress, not currency."""
        # Create instruction slot
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student_member,
        )

        # Send notification
        send_student_signup_notification(slot)

        # Check email was sent (may be 1 or 2 depending on surge instructor)
        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Check subject
        assert "instruction request" in email.subject.lower()

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        assert html_content is not None

        # HTML should contain training progress
        assert "Training Progress" in html_content
        assert "Solo Progress" in html_content
        assert "Checkride Progress" in html_content
        assert "65%" in html_content  # Solo progress
        assert "40%" in html_content  # Checkride progress

        # HTML should NOT contain flight currency
        assert "Flight Currency" not in html_content
        assert "Last Flight" not in html_content

        # Check plain text version
        assert "TRAINING PROGRESS" in email.body
        assert "Solo Progress: 65%" in email.body
        assert "Checkride Progress: 40%" in email.body

    def test_student_email_without_progress(
        self, site_config, duty_assignment, student_member
    ):
        """Student without progress snapshot should still get proper email."""
        # Create instruction slot (no progress snapshot)
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student_member,
        )

        # Send notification
        send_student_signup_notification(slot)

        # Check email was sent (may be 1 or 2 depending on surge instructor)
        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        assert html_content is not None

        # Email should contain student details
        assert student_member.full_display_name in html_content
        assert student_member.email in html_content

        # Should NOT show progress or currency sections (student has neither)
        assert "Training Progress" not in html_content
        assert "Flight Currency" not in html_content


@pytest.mark.django_db
class TestRatedPilotInstructionRequestEmail:
    """Tests for rated pilot instruction request emails (with currency)."""

    def test_rated_pilot_email_shows_currency(
        self,
        site_config,
        duty_assignment,
        rated_pilot,
        private_pilot_qualification,
        glider,
        logsheet,
    ):
        """Rated pilot email should show flight currency, not progress."""
        # Give pilot a rating
        MemberQualification.objects.create(
            member=rated_pilot,
            qualification=private_pilot_qualification,
            is_qualified=True,
        )

        # Create some flight history
        Flight.objects.create(
            logsheet=logsheet,
            pilot=rated_pilot,
            glider=glider,
            flight_type="solo",
        )

        # Create another logsheet with instructor flight
        airfield = Airfield.objects.first()  # Reuse the one from the fixture
        log_creator = Member.objects.filter(username="creator").first()
        instructor_logsheet = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=30),
            airfield=airfield,
            created_by=log_creator,
            finalized=True,
        )
        instructor_member = Member.objects.create(
            username="flight_instructor",
            first_name="Bob",
            last_name="CFI",
            email="cfi@example.com",
            membership_status="Full Member",
        )
        Flight.objects.create(
            logsheet=instructor_logsheet,
            pilot=rated_pilot,
            instructor=instructor_member,
            glider=glider,
            flight_type="dual",
        )

        # Create instruction slot
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=rated_pilot,
        )

        # Send notification
        send_student_signup_notification(slot)

        # Check email was sent
        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        assert html_content is not None

        # HTML should contain flight currency
        assert "Flight Currency" in html_content
        assert "Last Flight" in html_content
        assert "Last Instructor Flight" in html_content

        # HTML should NOT contain training progress
        assert "Training Progress" not in html_content
        assert "Solo Progress" not in html_content
        assert "Checkride Progress" not in html_content

        # Check plain text version
        assert "FLIGHT CURRENCY" in email.body
        assert "Last Flight:" in email.body
        assert "Last Instructor Flight:" in email.body

        # Should not show progress
        assert "TRAINING PROGRESS" not in email.body

    def test_rated_pilot_no_flight_history(
        self, site_config, duty_assignment, rated_pilot, private_pilot_qualification
    ):
        """Rated pilot without flight history should show appropriate message."""
        # Give pilot a rating
        MemberQualification.objects.create(
            member=rated_pilot,
            qualification=private_pilot_qualification,
            is_qualified=True,
        )

        # Create instruction slot (no flight history)
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=rated_pilot,
        )

        # Send notification
        send_student_signup_notification(slot)

        # Check email was sent
        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        assert html_content is not None

        # Should show currency section with zero flights
        assert "Flight Currency" in html_content
        assert "Total Flights:" in html_content
        assert ">0<" in html_content  # Value in table cell

        # Plain text should show it on one line
        assert "FLIGHT CURRENCY" in email.body
        assert "Total Flights: 0" in email.body

    def test_both_qualification_type_treated_as_rated(
        self, site_config, duty_assignment, rated_pilot, db
    ):
        """Qualification with applies_to='both' should treat member as rated."""
        # Create a qualification that applies to both
        both_qual = ClubQualificationType.objects.create(
            code="ASK-BACK",
            name="ASK-21 Back Seat Checkout",
            applies_to="both",
        )

        # Give pilot this qualification
        MemberQualification.objects.create(
            member=rated_pilot,
            qualification=both_qual,
            is_qualified=True,
        )

        # Create instruction slot
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=rated_pilot,
        )

        # Send notification
        send_student_signup_notification(slot)

        # Check email was sent
        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        assert html_content is not None

        # Should show flight currency (treated as rated)
        assert "Flight Currency" in html_content
        assert "Training Progress" not in html_content


@pytest.mark.django_db
class TestEmailContent:
    """Tests for general email content."""

    def test_email_contains_student_details(
        self, site_config, duty_assignment, student_member
    ):
        """Email should always contain student contact details."""
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student_member,
        )

        send_student_signup_notification(slot)

        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        # Check student details in HTML
        assert student_member.full_display_name in html_content
        assert student_member.email in html_content
        assert student_member.phone in html_content

        # Check student details in plain text
        assert student_member.full_display_name in email.body
        assert student_member.email in email.body
        assert student_member.phone in email.body

    def test_email_contains_instruction_date(
        self, site_config, duty_assignment, student_member
    ):
        """Email should contain the instruction date."""
        slot = InstructionSlot.objects.create(
            assignment=duty_assignment,
            student=student_member,
        )

        send_student_signup_notification(slot)

        assert len(mail.outbox) >= 1
        email = mail.outbox[0]

        # Format the date as it appears in the template
        formatted_date = duty_assignment.date.strftime("%B %d, %Y").replace(" 0", " ")

        # Get HTML content
        html_content = None
        for alternative in email.alternatives:
            if alternative[1] == "text/html":
                html_content = alternative[0]
                break

        # Check date appears in email
        assert (
            formatted_date in html_content
            or duty_assignment.date.strftime("%B %d, %Y") in html_content
        )
