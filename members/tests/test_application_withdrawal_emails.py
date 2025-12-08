"""
Tests for membership application withdrawal email notifications.
Tests HTML/text email rendering for withdrawn applications.
"""

from django.core import mail
from django.test import TestCase, override_settings

from members.models import Member
from members.models_applications import MembershipApplication
from members.signals import notify_membership_managers_of_withdrawal
from siteconfig.models import SiteConfiguration


class ApplicationWithdrawalEmailTests(TestCase):
    """Test HTML email rendering for membership application withdrawals."""

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
        """Test that HTML email template renders correctly for withdrawals."""
        # Create a test application
        application = MembershipApplication.objects.create(
            first_name="John",
            last_name="Withdrew",
            email="john@example.com",
            phone="555-1234",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Withdrew",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-5678",
            soaring_goals="Changed my mind about soaring",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
            status="withdrawn",
        )

        # Trigger the notification
        notify_membership_managers_of_withdrawal(application)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content exists
        self.assertEqual(len(email.alternatives), 1)
        html_content = email.alternatives[0][0]
        self.assertIn("text/html", email.alternatives[0][1])

        # Verify HTML structure and content
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("Application Withdrawn", html_content)
        self.assertIn("John Withdrew", html_content)
        self.assertIn("john@example.com", html_content)

        # Verify plain text fallback also has content
        self.assertIn("John Withdrew", email.body)
        self.assertIn("john@example.com", email.body)
        self.assertIn("WITHDRAWN", email.body)  # Text template uses all caps

        # Verify subject
        self.assertIn("Withdrawn", email.subject)

        # Verify recipient
        self.assertIn("manager@test.com", email.to)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_with_withdrawal_reason(self):
        """Test HTML email rendering with withdrawal reason."""
        application = MembershipApplication.objects.create(
            first_name="Jane",
            last_name="Changed",
            email="jane@example.com",
            phone="555-9999",
            address_line1="456 Oak Ave",
            city="Springfield",
            state="IL",
            zip_code="62701",
            emergency_contact_name="John Changed",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-8888",
            soaring_goals="Going to a different club",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
            status="withdrawn",
        )

        notify_membership_managers_of_withdrawal(application)

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Verify applicant info appears
        self.assertIn("Jane Changed", html_content)
        self.assertIn("jane@example.com", html_content)

        # Verify plain text version
        self.assertIn("Jane", email.body)

    @override_settings(DEFAULT_FROM_EMAIL="noreply@testclub.com", EMAIL_DEV_MODE=False)
    def test_no_email_when_no_managers(self):
        """Test that no email is sent when no member managers exist."""
        # Remove member manager privilege
        Member.objects.filter(member_manager=True).update(member_manager=False)
        Member.objects.filter(webmaster=True).update(webmaster=False)

        application = MembershipApplication.objects.create(
            first_name="No",
            last_name="Manager",
            email="nomanager@example.com",
            phone="555-2222",
            address_line1="123 Test St",
            city="Nowhere",
            state="XX",
            zip_code="00000",
            emergency_contact_name="Contact",
            emergency_contact_relationship="Friend",
            emergency_contact_phone="555-3333",
            soaring_goals="Learn to fly",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
            status="withdrawn",
        )

        notify_membership_managers_of_withdrawal(application)

        # Check that no email was sent
        self.assertEqual(len(mail.outbox), 0)
