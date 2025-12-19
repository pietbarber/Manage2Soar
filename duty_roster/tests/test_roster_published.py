"""
Tests for roster published notifications (Issue #423).

This module tests the functionality that sends ICS calendar invites
to members when a duty roster is published for an upcoming month.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from icalendar import Calendar

from duty_roster.models import DutyAssignment
from duty_roster.utils.email import send_roster_published_notifications
from duty_roster.utils.ics import generate_roster_ics
from siteconfig.models import SiteConfiguration


@pytest.fixture
def site_config(db):
    """Create a site configuration for testing."""
    return SiteConfiguration.objects.create(
        club_name="Test Soaring Club",
        domain_name="testsoaring.org",
        club_abbreviation="TSC",
        club_nickname="TSC",
    )


@pytest.fixture
def test_members(db, django_user_model):
    """Create test members for duty assignments."""
    duty_officer = django_user_model.objects.create_user(
        username="do_test",
        email="do@testsoaring.org",
        first_name="Duty",
        last_name="Officer",
        membership_status="Full Member",
    )
    instructor = django_user_model.objects.create_user(
        username="instructor_test",
        email="instructor@testsoaring.org",
        first_name="Flight",
        last_name="Instructor",
        membership_status="Full Member",
    )
    tow_pilot = django_user_model.objects.create_user(
        username="towpilot_test",
        email="towpilot@testsoaring.org",
        first_name="Tow",
        last_name="Pilot",
        membership_status="Full Member",
    )
    return {
        "duty_officer": duty_officer,
        "instructor": instructor,
        "tow_pilot": tow_pilot,
    }


@pytest.mark.django_db
class TestGenerateRosterIcs:
    """Tests for the generate_roster_ics function."""

    def test_generates_valid_ics(self, site_config):
        """Generated ICS content should be valid iCalendar format."""
        duty_date = date.today() + timedelta(days=14)
        ics_content = generate_roster_ics(
            duty_date=duty_date,
            role_title="Duty Officer",
            member_name="John Doe",
        )

        # Should be bytes
        assert isinstance(ics_content, bytes)

        # Should be valid iCalendar (decode bytes for from_ical)
        cal = Calendar.from_ical(ics_content.decode("utf-8"))
        assert cal is not None

        # Check calendar properties
        assert b"BEGIN:VCALENDAR" in ics_content
        assert b"BEGIN:VEVENT" in ics_content
        assert b"END:VEVENT" in ics_content
        assert b"END:VCALENDAR" in ics_content

    def test_contains_roster_notes(self, site_config):
        """ICS should contain roster-specific notes in description."""
        duty_date = date.today() + timedelta(days=14)
        ics_content = generate_roster_ics(
            duty_date=duty_date,
            role_title="Tow Pilot",
            member_name="Jane Smith",
        )

        # Should contain roster-specific text
        assert b"newly published roster" in ics_content

    def test_contains_correct_role_in_summary(self, site_config):
        """ICS should have the role title in the event summary."""
        duty_date = date.today() + timedelta(days=14)
        ics_content = generate_roster_ics(
            duty_date=duty_date,
            role_title="Instructor",
            member_name="Test Member",
        )

        assert b"Instructor" in ics_content
        assert b"Test Soaring Club" in ics_content

    def test_uid_is_stable_across_generations(self, site_config):
        """Same parameters should produce identical UIDs (no timestamp variation)."""
        duty_date = date.today() + timedelta(days=14)
        role_title = "Duty Officer"
        member_name = "John Doe"

        # Generate ICS twice with same parameters
        ics_content_1 = generate_roster_ics(
            duty_date=duty_date,
            role_title=role_title,
            member_name=member_name,
        )
        ics_content_2 = generate_roster_ics(
            duty_date=duty_date,
            role_title=role_title,
            member_name=member_name,
        )

        # Parse both calendars
        cal1 = Calendar.from_ical(ics_content_1.decode("utf-8"))
        cal2 = Calendar.from_ical(ics_content_2.decode("utf-8"))

        # Extract UIDs from VEVENT components
        uid1 = None
        uid2 = None
        for component in cal1.walk():
            if component.name == "VEVENT":
                uid1 = str(component.get("uid"))
                break
        for component in cal2.walk():
            if component.name == "VEVENT":
                uid2 = str(component.get("uid"))
                break

        # UIDs should be identical (stable, no timestamp)
        assert uid1 is not None
        assert uid2 is not None
        assert uid1 == uid2

        # UID should be based on date, role, and member (not contain random/timestamp)
        expected_uid = f"roster-{duty_date.isoformat()}-duty-officer-john-doe"
        assert uid1 == expected_uid


@pytest.mark.django_db
class TestSendRosterPublishedNotifications:
    """Tests for the send_roster_published_notifications function."""

    def test_sends_emails_to_assigned_members(self, site_config, test_members):
        """Should send emails to all members with duty assignments."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        # Create assignments
        assignment1 = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=test_members["duty_officer"],
            instructor=test_members["instructor"],
            tow_pilot=test_members["tow_pilot"],
        )
        assignment2 = DutyAssignment.objects.create(
            date=base_date + timedelta(days=7),
            duty_officer=test_members["duty_officer"],
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            result = send_roster_published_notifications(
                year, month, [assignment1, assignment2]
            )

            # Should have sent to 3 unique members
            assert result["member_count"] == 3
            assert result["sent_count"] == 3
            assert result["errors"] == []

    def test_attaches_ics_files_to_emails(self, site_config, test_members):
        """Each email should have ICS attachments for all duty assignments."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        # Create two assignments for same member
        assignment1 = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=test_members["duty_officer"],
        )
        assignment2 = DutyAssignment.objects.create(
            date=base_date + timedelta(days=7),
            duty_officer=test_members["duty_officer"],
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            result = send_roster_published_notifications(
                year, month, [assignment1, assignment2]
            )

            # Should have sent to 1 member
            assert result["member_count"] == 1

            # Check that attach was called with ICS files
            attach_calls = mock_email.attach.call_args_list
            ics_filenames = [call[0][0] for call in attach_calls]

            # Should have 2 ICS files attached (one per duty)
            assert len([f for f in ics_filenames if f.endswith(".ics")]) == 2

    def test_handles_members_without_email(self, site_config, django_user_model):
        """Members without email addresses should be skipped."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        # Create member without email
        member_no_email = django_user_model.objects.create_user(
            username="no_email",
            email="",  # No email
            first_name="No",
            last_name="Email",
            membership_status="Full Member",
        )

        assignment = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=member_no_email,
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            result = send_roster_published_notifications(year, month, [assignment])

            # Should not have sent any emails
            assert result["member_count"] == 0
            assert result["sent_count"] == 0

    def test_no_assignments_returns_empty_result(self, site_config):
        """Empty assignment list should return zero counts."""
        result = send_roster_published_notifications(2025, 2, [])

        assert result["sent_count"] == 0
        assert result["member_count"] == 0
        assert result["errors"] == []

    def test_groups_multiple_duties_for_same_member(self, site_config, test_members):
        """Member with multiple duties should receive single email with all ICS files."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        # Create 3 assignments for same member with different roles
        assignment1 = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=test_members["duty_officer"],
        )
        assignment2 = DutyAssignment.objects.create(
            date=base_date + timedelta(days=7),
            duty_officer=test_members["duty_officer"],
        )
        assignment3 = DutyAssignment.objects.create(
            date=base_date + timedelta(days=14),
            duty_officer=test_members["duty_officer"],
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            result = send_roster_published_notifications(
                year, month, [assignment1, assignment2, assignment3]
            )

            # Should send to 1 member with 3 duties
            assert result["member_count"] == 1
            assert result["sent_count"] == 1

            # Should have 3 ICS attachments
            attach_calls = mock_email.attach.call_args_list
            assert len(attach_calls) == 3

    def test_email_subject_contains_month(self, site_config, test_members):
        """Email subject should include the month and year."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        assignment = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=test_members["duty_officer"],
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email

            send_roster_published_notifications(year, month, [assignment])

            # Check subject
            call_args = mock_email_class.call_args
            subject = call_args[1]["subject"]
            assert "February 2025" in subject
            assert "Duty Assignments" in subject

    def test_handles_email_send_failure(self, site_config, test_members):
        """Should capture errors when email sending fails."""
        year, month = 2025, 2
        base_date = date(2025, 2, 8)

        assignment = DutyAssignment.objects.create(
            date=base_date,
            duty_officer=test_members["duty_officer"],
        )

        with patch("django.core.mail.EmailMultiAlternatives") as mock_email_class:
            mock_email = MagicMock()
            mock_email.send.side_effect = Exception("SMTP connection failed")
            mock_email_class.return_value = mock_email

            result = send_roster_published_notifications(year, month, [assignment])

            # Should have captured the error
            assert result["sent_count"] == 0
            assert len(result["errors"]) == 1
            assert "SMTP connection failed" in result["errors"][0]


@pytest.mark.django_db
class TestRosterPublishedEmailTemplates:
    """Tests for the roster published email templates."""

    def test_html_template_renders(self, site_config, test_members):
        """HTML template should render without errors."""
        from django.template.loader import render_to_string

        context = {
            "month_name": "February 2025",
            "year": 2025,
            "month": 2,
            "club_name": "Test Soaring Club",
            "club_nickname": "TSC",
            "club_logo_url": "https://example.com/logo.png",
            "site_url": "https://testsoaring.org",
            "duty_roster_url": "https://testsoaring.org/duty_roster/calendar/",
            "member": test_members["duty_officer"],
            "duties": [
                {
                    "date": date(2025, 2, 8),
                    "role": "Duty Officer",
                },
                {
                    "date": date(2025, 2, 15),
                    "role": "Duty Officer",
                },
            ],
            "duty_count": 2,
        }

        html = render_to_string("duty_roster/emails/roster_published.html", context)

        assert "Duty Roster Published" in html
        assert "February 2025" in html
        assert "Duty Officer" in html
        assert "2 duty assignments" in html
        # Check site URL is rendered (using href to avoid false positive security scan)
        assert 'href="https://testsoaring.org' in html

    def test_text_template_renders(self, site_config, test_members):
        """Text template should render without errors."""
        from django.template.loader import render_to_string

        context = {
            "month_name": "February 2025",
            "year": 2025,
            "month": 2,
            "club_name": "Test Soaring Club",
            "club_nickname": "TSC",
            "site_url": "https://testsoaring.org",
            "duty_roster_url": "https://testsoaring.org/duty_roster/calendar/",
            "member": test_members["duty_officer"],
            "duties": [
                {
                    "date": date(2025, 2, 8),
                    "role": "Duty Officer",
                },
            ],
            "duty_count": 1,
        }

        text = render_to_string("duty_roster/emails/roster_published.txt", context)

        assert "Duty Roster Published" in text
        assert "February 2025" in text
        assert "Duty Officer" in text
        assert "1 duty assignment" in text
