"""
Tests for membership application submission email notifications.
Tests HTML/text email rendering for new membership applications.
"""

from django.core import mail
from django.test import TestCase, override_settings

from members.models import Member
from members.models_applications import MembershipApplication
from members.signals import notify_membership_managers_of_new_application
from siteconfig.models import SiteConfiguration


class ApplicationSubmissionEmailTests(TestCase):
    """Test HTML email rendering for membership application submissions."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
        )

        # Create member managers
        self.member_manager_1 = Member.objects.create_user(
            username="manager1@test.com",
            email="manager1@test.com",
            first_name="Manager",
            last_name="One",
        )
        self.member_manager_1.member_manager = True
        self.member_manager_1.membership_status = "Full Member"
        self.member_manager_1.save()

        self.member_manager_2 = Member.objects.create_user(
            username="manager2@test.com",
            email="manager2@test.com",
            first_name="Manager",
            last_name="Two",
        )
        self.member_manager_2.member_manager = True
        self.member_manager_2.membership_status = "Full Member"
        self.member_manager_2.save()

        # Clear any existing emails
        mail.outbox = []

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_rendering(self):
        """Test that HTML email template renders correctly for new applications."""
        # Create a test application
        application = MembershipApplication.objects.create(
            first_name="John",
            last_name="Applicant",
            email="john@example.com",
            phone="555-1234",
            address_line1="123 Main St",
            city="Anytown",
            state="CA",
            zip_code="12345",
            emergency_contact_name="Jane Applicant",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-5678",
            soaring_goals="I want to learn glider flying",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        # Trigger the notification
        notify_membership_managers_of_new_application(application)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content exists
        self.assertEqual(len(email.alternatives), 1)
        html_content = email.alternatives[0][0]
        self.assertIn("text/html", email.alternatives[0][1])

        # Verify HTML structure and content
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("New Membership Application", html_content)
        self.assertIn("John Applicant", html_content)
        self.assertIn("john@example.com", html_content)
        self.assertIn("555-1234", html_content)

        # Verify plain text fallback also has content
        self.assertIn("John Applicant", email.body)
        self.assertIn("john@example.com", email.body)

        # Verify recipients
        expected_recipients = {"manager1@test.com", "manager2@test.com"}
        actual_recipients = set(email.to)
        self.assertEqual(expected_recipients, actual_recipients)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_with_middle_initial(self):
        """Test HTML email rendering with middle initial."""
        application = MembershipApplication.objects.create(
            first_name="Jane",
            last_name="Pilot",
            middle_initial="Q",
            email="jane@example.com",
            phone="555-9999",
            address_line1="456 Oak Ave",
            city="Springfield",
            state="IL",
            zip_code="62701",
            emergency_contact_name="John Pilot",
            emergency_contact_relationship="Spouse",
            emergency_contact_phone="555-8888",
            soaring_goals="Cross-country soaring",
            agrees_to_terms=True,
            agrees_to_safety_rules=True,
            agrees_to_financial_obligations=True,
        )

        notify_membership_managers_of_new_application(application)

        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Verify applicant name appears in HTML
        self.assertIn("Jane", html_content)
        self.assertIn("Pilot", html_content)
        self.assertIn("Springfield", html_content)

        # Also check plain text version
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
        )

        notify_membership_managers_of_new_application(application)

        # Check that no email was sent
        self.assertEqual(len(mail.outbox), 0)
