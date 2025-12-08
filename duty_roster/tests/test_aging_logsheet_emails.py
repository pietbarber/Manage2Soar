"""
Tests for aging logsheet email notifications.
Tests HTML/text email rendering for aging logsheets.
"""

from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from logsheet.models import Airfield, Logsheet
from members.models import Member
from siteconfig.models import SiteConfiguration


class AgingLogsheetEmailTests(TestCase):
    """Test HTML email rendering for aging logsheet notifications."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
        )

        # Create airfield
        self.airfield = Airfield.objects.create(name="Test Field", identifier="TST")

        # Create a member who is duty officer
        self.member = Member.objects.create_user(
            username="pilot@test.com",
            email="pilot@test.com",
            first_name="Test",
            last_name="Pilot",
        )
        self.member.membership_status = "Full Member"
        self.member.save()

        # Create an aging incomplete logsheet (10 days old)
        old_date = timezone.now().date() - timedelta(days=10)
        self.logsheet = Logsheet.objects.create(
            log_date=old_date,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
            finalized=False,
        )

        # Clear any existing emails
        mail.outbox = []

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_rendering(self):
        """Test that HTML email template renders correctly for aging logsheets."""
        # Call the management command
        out = StringIO()
        call_command("notify_aging_logsheets", stdout=out)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content exists
        self.assertEqual(len(email.alternatives), 1)
        html_content = email.alternatives[0][0]
        self.assertIn("text/html", email.alternatives[0][1])

        # Verify HTML structure and content
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("Logsheet", html_content)  # Title contains "Logsheet"
        self.assertIn("Hello Test", html_content)  # Uses first name only

        # Verify plain text fallback also has content
        self.assertIn("Test", email.body)
        self.assertIn("logsheet", email.body.lower())

        # Verify subject mentions logsheets
        self.assertIn("logsheet", email.subject.lower())

        # Verify recipient
        self.assertIn("pilot@test.com", email.to)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_with_multiple_logsheets(self):
        """Test HTML email rendering when member has multiple aging logsheets."""
        # Create another aging logsheet for the same member
        old_date_2 = timezone.now().date() - timedelta(days=8)
        Logsheet.objects.create(
            log_date=old_date_2,
            airfield=self.airfield,
            duty_officer=self.member,
            created_by=self.member,
            finalized=False,
        )

        # Call the management command
        out = StringIO()
        call_command("notify_aging_logsheets", stdout=out)

        # Should still only send one email per member
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content
        html_content = email.alternatives[0][0]
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("Hello Test", html_content)  # Uses first name

        # Verify plain text version
        self.assertIn("Test", email.body)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_no_email_for_recent_logsheets(self):
        """Test that no email is sent for recently created logsheets."""
        # Update logsheet to be recent (within threshold)
        self.logsheet.log_date = timezone.now().date() - timedelta(days=2)
        self.logsheet.save()

        # Call the management command
        out = StringIO()
        call_command("notify_aging_logsheets", stdout=out)

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0)
