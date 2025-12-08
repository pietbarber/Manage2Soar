"""
Tests for visitor contact form email notifications.
Tests HTML/text email rendering for visitor contact submissions.
"""

from django.core import mail
from django.test import TestCase, override_settings

from cms.models import VisitorContact
from cms.views import _notify_member_managers_of_contact
from members.models import Member
from siteconfig.models import SiteConfiguration


class VisitorContactEmailTests(TestCase):
    """Test HTML email rendering for visitor contact form submissions."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
        )

        # Create member managers
        self.member_manager = Member.objects.create_user(
            username="manager@test.com",
            email="manager@test.com",
            first_name="Manager",
            last_name="Person",
        )
        self.member_manager.member_manager = True
        self.member_manager.membership_status = "Full Member"
        self.member_manager.save()

        # Clear any existing emails
        mail.outbox = []

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_rendering(self):
        """Test that HTML email template renders correctly for visitor contacts."""
        # Create a visitor contact submission
        contact = VisitorContact.objects.create(
            name="John Visitor",
            email="john@example.com",
            phone="555-1234",
            subject="Question about membership",
            message="I'm interested in joining your club. Can you send me information?",
        )

        # Trigger the notification
        _notify_member_managers_of_contact(contact)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content exists
        self.assertEqual(len(email.alternatives), 1)
        html_content = email.alternatives[0][0]
        self.assertIn("text/html", email.alternatives[0][1])

        # Verify HTML structure and content
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("Visitor Contact", html_content)
        self.assertIn("John Visitor", html_content)
        self.assertIn("john@example.com", html_content)
        self.assertIn("Question about membership", html_content)

        # Verify plain text fallback also has content
        self.assertIn("John Visitor", email.body)
        self.assertIn("john@example.com", email.body)

        # Verify subject
        self.assertIn("Visitor Contact", email.subject)

        # Verify recipient
        self.assertIn("manager@test.com", email.to)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_with_long_message(self):
        """Test HTML email rendering with longer message content."""
        contact = VisitorContact.objects.create(
            name="Jane Visitor",
            email="jane@example.com",
            phone="555-9999",
            subject="Flight training inquiry",
            message=(
                "Hello, I have been interested in glider flying for several years "
                "and would like to know more about your training program. What are "
                "the requirements to get started? Do you offer trial flights? "
                "What is the typical timeline for getting a glider pilot license?"
            ),
        )

        _notify_member_managers_of_contact(contact)

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Verify contact info appears
        self.assertIn("Jane Visitor", html_content)
        self.assertIn("jane@example.com", html_content)
        self.assertIn("Flight training inquiry", html_content)
        self.assertIn("trial flights", html_content)

        # Verify plain text version
        self.assertIn("Jane", email.body)
        self.assertIn("trial flights", email.body)

    @override_settings(DEFAULT_FROM_EMAIL="noreply@testclub.com", EMAIL_DEV_MODE=False)
    def test_no_email_when_no_managers(self):
        """Test that no email is sent when no member managers exist."""
        # Remove member manager privilege
        Member.objects.filter(member_manager=True).update(member_manager=False)
        Member.objects.filter(webmaster=True).update(webmaster=False)

        contact = VisitorContact.objects.create(
            name="No Manager",
            email="nomanager@example.com",
            phone="555-2222",
            subject="Test",
            message="This should not send an email",
        )

        _notify_member_managers_of_contact(contact)

        # Check that no email was sent
        self.assertEqual(len(mail.outbox), 0)
