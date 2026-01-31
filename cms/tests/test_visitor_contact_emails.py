"""
Tests for visitor contact form email notifications.
Tests HTML/text email rendering for visitor contact submissions.
Also tests honeypot spam prevention (Issue #590).
"""

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.forms import VisitorContactForm
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


class HoneypotSpamPreventionTests(TestCase):
    """Test honeypot spam prevention for visitor contact form (Issue #590)."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
        )

        # Create member manager to receive notifications
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

    def test_form_has_honeypot_field(self):
        """Test that the form includes the honeypot field."""
        form = VisitorContactForm()
        self.assertIn("website", form.fields)

    def test_honeypot_not_triggered_when_empty(self):
        """Test that valid submissions without honeypot work normally."""
        form_data = {
            "name": "Real Human",
            "email": "human@example.com",
            "phone": "555-1234",
            "subject": "Legitimate inquiry",
            "message": "I'm interested in joining your club.",
            "website": "",  # Empty honeypot
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertFalse(form.is_honeypot_triggered())

    def test_honeypot_triggered_when_filled(self):
        """Test that honeypot is triggered when field is filled."""
        form_data = {
            "name": "Spam Bot",
            "email": "bot@spam.com",
            "phone": "555-0000",
            "subject": "Buy our products",
            "message": "This is a legitimate message.",
            "website": "http://spam-website.com",  # Filled honeypot
        }
        form = VisitorContactForm(data=form_data)
        self.assertTrue(form.is_valid())  # Form is still valid
        self.assertTrue(form.is_honeypot_triggered())  # But honeypot was triggered

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_honeypot_prevents_submission_silently(self):
        """Test that honeypot triggers silent rejection - no record saved, no email."""
        form_data = {
            "name": "Spam Bot",
            "email": "bot@spam.com",
            "phone": "555-0000",
            "subject": "Buy our products",
            "message": "This is a legitimate message with enough characters.",
            "website": "http://spam-website.com",  # Filled honeypot
        }

        initial_count = VisitorContact.objects.count()

        response = self.client.post(reverse("contact"), form_data)

        # Should redirect to success (fool the bot)
        self.assertRedirects(response, reverse("contact_success"))

        # But no record should be saved
        self.assertEqual(VisitorContact.objects.count(), initial_count)

        # And no email should be sent
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_legitimate_submission_works(self):
        """Test that legitimate submissions without honeypot work normally."""
        form_data = {
            "name": "Real Human",
            "email": "human@example.com",
            "phone": "555-1234",
            "subject": "Legitimate inquiry",
            "message": "I'm interested in joining your club and learning to fly.",
            "website": "",  # Empty honeypot
        }

        initial_count = VisitorContact.objects.count()

        response = self.client.post(reverse("contact"), form_data)

        # Should redirect to success
        self.assertRedirects(response, reverse("contact_success"))

        # Record should be saved
        self.assertEqual(VisitorContact.objects.count(), initial_count + 1)

        # Email should be sent
        self.assertEqual(len(mail.outbox), 1)

        # Verify the saved record
        contact = VisitorContact.objects.latest("submitted_at")
        self.assertEqual(contact.name, "Real Human")
        self.assertEqual(contact.email, "human@example.com")
