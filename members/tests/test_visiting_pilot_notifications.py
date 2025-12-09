"""
Tests for visiting pilot notification system.
Tests the signals and notification functionality for member managers.
"""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from members.models import Member
from members.signals import _notify_member_managers_of_visiting_pilot
from notifications.models import Notification
from siteconfig.models import SiteConfiguration


class VisitingPilotNotificationTests(TestCase):
    """Test notification system for visiting pilot registrations."""

    def setUp(self):
        """Set up test data."""
        # Create site configuration
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
            visiting_pilot_auto_approve=True,
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

        # Create webmaster as fallback
        self.webmaster = Member.objects.create_user(
            username="webmaster@test.com",
            email="webmaster@test.com",
            first_name="Web",
            last_name="Master",
        )
        self.webmaster.webmaster = True
        self.webmaster.membership_status = "Full Member"
        self.webmaster.save()

        # Clear any existing emails
        mail.outbox = []

    def test_visiting_pilot_signal_triggered_on_creation(self):
        """Test that signal is triggered when visiting pilot is created."""
        with patch(
            "members.signals._notify_member_managers_of_visiting_pilot"
        ) as mock_notify:
            visiting_pilot = Member.objects.create_user(
                username="visitor@test.com",
                email="visitor@test.com",
                first_name="Visiting",
                last_name="Pilot",
                home_club="Remote Soaring Club",
                SSA_member_number="12345",
                glider_rating="private",
                membership_status="Affiliate Member",
            )
            # Verify the notification function was called
            mock_notify.assert_called_once_with(visiting_pilot)

    def test_visiting_pilot_signal_not_triggered_for_regular_members(self):
        """Test that signal is NOT triggered for regular member creation."""
        with patch(
            "members.signals._notify_member_managers_of_visiting_pilot"
        ) as mock_notify:
            Member.objects.create_user(
                username="regular@test.com",
                email="regular@test.com",
                first_name="Regular",
                last_name="Member",
                membership_status="Full Member",  # Not visiting pilot status
            )

            # Verify the notification function was NOT called
            mock_notify.assert_not_called()

    def test_visiting_pilot_signal_not_triggered_when_disabled(self):
        """Test that signal is NOT triggered when visiting pilot feature is disabled."""
        # Disable visiting pilot feature
        self.config.visiting_pilot_enabled = False
        self.config.save()

        with patch(
            "members.signals._notify_member_managers_of_visiting_pilot"
        ) as mock_notify:
            Member.objects.create_user(
                username="visitor@test.com",
                email="visitor@test.com",
                first_name="Visiting",
                last_name="Pilot",
                membership_status="Affiliate Member",
            )

            # Verify the notification function was NOT called
            mock_notify.assert_not_called()

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_email_notification_sent_to_member_managers(self):
        """Test that email notifications are sent to member managers."""
        # Verify member managers exist and are set up correctly
        member_managers = Member.objects.filter(member_manager=True, is_active=True)
        self.assertEqual(
            member_managers.count(), 2, "Should have 2 member managers in test setup"
        )

        Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            home_club="Remote Soaring Club",
            SSA_member_number="12345",
            glider_rating="private",
            membership_status="Affiliate Member",
        )

        # Signal should automatically trigger notification

        # Check that email was sent (one email with multiple recipients)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email details
        self.assertIn("New Visiting Pilot Registration", email.subject)
        self.assertIn("Visiting Pilot", email.subject)
        self.assertIn("visitor@test.com", email.body)
        self.assertIn("Remote Soaring Club", email.body)
        self.assertIn("12345", email.body)
        self.assertIn("automatically approved", email.body)

        # Verify recipients (should include both member managers)
        expected_recipients = {"manager1@test.com", "manager2@test.com"}
        actual_recipients = set(email.to)
        self.assertEqual(expected_recipients, actual_recipients)

    @override_settings(DEFAULT_FROM_EMAIL="noreply@testclub.com", EMAIL_DEV_MODE=False)
    def test_email_notification_manual_approval_content(self):
        """Test email content when manual approval is required."""
        # Set manual approval
        self.config.visiting_pilot_auto_approve = False
        self.config.save()

        Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Manual",
            last_name="Approval",
            home_club="Remote Soaring Club",
            SSA_member_number="54321",
            glider_rating="private",
            membership_status="Affiliate Member",
        )

        # Signal should automatically trigger notification

        # Check email content for manual approval
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("requires manual approval", email.body)
        self.assertIn("Set 'Active' status", email.body)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_rendering(self):
        """Test that HTML email template renders correctly."""
        Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            home_club="Remote Soaring Club",
            SSA_member_number="12345",
            glider_rating="private",
            membership_status="Affiliate Member",
        )

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify HTML content exists
        self.assertEqual(len(email.alternatives), 1)
        html_content = email.alternatives[0][0]
        self.assertIn("text/html", email.alternatives[0][1])

        # Verify HTML structure and content
        self.assertIn("Test Soaring Club", html_content)
        self.assertIn("New Visiting Pilot Registration", html_content)
        self.assertIn("Visiting Pilot", html_content)
        self.assertIn("visitor@test.com", html_content)
        self.assertIn("Remote Soaring Club", html_content)
        self.assertIn("12345", html_content)
        self.assertIn("automatically approved", html_content)

        # Verify plain text fallback also has content
        self.assertIn("Visiting Pilot", email.body)
        self.assertIn("Remote Soaring Club", email.body)

    @override_settings(
        DEFAULT_FROM_EMAIL="noreply@testclub.com",
        SITE_URL="https://testclub.com",
        EMAIL_DEV_MODE=False,
    )
    def test_html_email_manual_approval_rendering(self):
        """Test HTML email rendering for manual approval case."""
        self.config.visiting_pilot_auto_approve = False
        self.config.save()

        Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Manual",
            last_name="Approval",
            home_club="Remote Soaring Club",
            SSA_member_number="54321",
            glider_rating="private",
            membership_status="Affiliate Member",
        )

        # Check HTML content
        email = mail.outbox[0]
        html_content = email.alternatives[0][0]

        # Verify manual approval message appears in HTML
        self.assertIn("requires manual approval", html_content)
        self.assertIn("Set 'Active' status", html_content)
        self.assertIn("Manual Approval", html_content)

        # Also check plain text version
        self.assertIn("requires manual approval", email.body)

    def test_in_app_notifications_created(self):
        """Test that in-app notifications are created for member managers."""
        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            home_club="Remote Soaring Club",
            membership_status="Affiliate Member",
        )

        # Call notification function directly
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Check that notifications were created
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 2)  # One for each manager

        # Verify notification content
        for notification in notifications:
            self.assertIn("Visiting Pilot", notification.message)
            self.assertIn("Remote Soaring Club", notification.message)
            self.assertTrue(notification.user.member_manager)

    def test_fallback_to_webmasters_when_no_member_managers(self):
        """Test fallback to webmasters when no member managers exist."""
        # Remove member manager privilege from both managers
        self.member_manager_1.member_manager = False
        self.member_manager_1.save()
        self.member_manager_2.member_manager = False
        self.member_manager_2.save()

        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function directly
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Check that notification was sent to webmaster
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 1)
        notification = notifications.first()
        if notification:  # Guard against None
            self.assertEqual(notification.user, self.webmaster)

    def test_no_notifications_when_no_managers_or_webmasters(self):
        """Test graceful handling when no managers or webmasters exist."""
        # Remove privileges from all users
        Member.objects.filter(member_manager=True).update(member_manager=False)
        Member.objects.filter(webmaster=True).update(webmaster=False)

        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function directly - should not raise exceptions
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Check that no notifications were created
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 0)

    def test_notification_deduplication(self):
        """Test that duplicate notifications are not created."""
        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function twice
        _notify_member_managers_of_visiting_pilot(visiting_pilot)
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Should only have notifications from first call
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 2)  # One per manager, not duplicated

    @patch("members.signals.logger")
    def test_error_handling_no_site_config(self, mock_logger):
        """Test graceful error handling when site config is missing."""
        # Delete site configuration
        SiteConfiguration.objects.all().delete()

        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function - should not raise exceptions
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Verify error was logged
        mock_logger.error.assert_called()

    @override_settings(DEFAULT_FROM_EMAIL="")
    def test_no_email_when_not_configured(self):
        """Test that no email is sent when email is not configured."""
        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function directly
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Check that no email was sent
        self.assertEqual(len(mail.outbox), 0)

        # But in-app notifications should still be created
        notifications = Notification.objects.filter(dismissed=False)
        self.assertEqual(notifications.count(), 2)

    def test_email_sanitization(self):
        """Test that user input is properly sanitized in email subject line."""
        # Signal should automatically trigger notification
        with override_settings(
            DEFAULT_FROM_EMAIL="noreply@test.com", EMAIL_DEV_MODE=False
        ):
            Member.objects.create_user(
                username="visitor@test.com",
                email="visitor@test.com",
                first_name="Visiting\r\nInjection",
                last_name="Pilot\nTest",
                home_club="Club\rWith\nBadChars",
                SSA_member_number="123\n45",
                glider_rating="private",
                membership_status="Affiliate Member",
            )

        # Check that email was sent and subject is sanitized
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify subject line is sanitized (no \r or \n allowed in subject)
        self.assertNotIn("\r", email.subject)
        self.assertNotIn("\n", email.subject)
        # Should be sanitized name in subject
        self.assertIn("Visiting Injection Pilot Test", email.subject)

    @patch("notifications.models.Notification.objects.create")
    def test_notification_creation_error_handling(self, mock_create):
        """Test error handling when notification creation fails."""
        # Make notification creation raise an exception
        mock_create.side_effect = Exception("Database error")

        visiting_pilot = Member.objects.create_user(
            username="visitor@test.com",
            email="visitor@test.com",
            first_name="Visiting",
            last_name="Pilot",
            membership_status="Affiliate Member",
        )

        # Call notification function - should not raise exceptions
        _notify_member_managers_of_visiting_pilot(visiting_pilot)

        # Function should complete without raising the exception
