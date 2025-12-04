"""Tests for the dev mode email utility."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from utils.email import (
    DevModeEmailMessage,
    get_dev_mode_info,
    send_mail,
    send_mass_mail,
)


class DevModeEmailTests(TestCase):
    """Tests for email dev mode functionality."""

    @override_settings(EMAIL_DEV_MODE=False, EMAIL_DEV_MODE_REDIRECT_TO="")
    def test_get_dev_mode_info_disabled(self):
        """Dev mode should be disabled when EMAIL_DEV_MODE=False."""
        enabled, redirect_list = get_dev_mode_info()
        self.assertFalse(enabled)
        self.assertEqual(redirect_list, [])

    @override_settings(
        EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="test@example.com"
    )
    def test_get_dev_mode_info_enabled(self):
        """Dev mode settings should be readable when enabled."""
        enabled, redirect_list = get_dev_mode_info()
        self.assertTrue(enabled)
        self.assertEqual(redirect_list, ["test@example.com"])

    @override_settings(
        EMAIL_DEV_MODE=True,
        EMAIL_DEV_MODE_REDIRECT_TO="dev1@example.com, dev2@example.com",
    )
    def test_get_dev_mode_info_multiple_addresses(self):
        """Dev mode should support comma-separated addresses."""
        enabled, redirect_list = get_dev_mode_info()
        self.assertTrue(enabled)
        self.assertEqual(redirect_list, ["dev1@example.com", "dev2@example.com"])

    @override_settings(EMAIL_DEV_MODE=False)
    @patch("utils.email.django_send_mail")
    def test_send_mail_normal_mode(self, mock_send):
        """Normal mode should send to original recipients."""
        mock_send.return_value = 1

        send_mail(
            subject="Test Subject",
            message="Test body",
            from_email="from@example.com",
            recipient_list=["user1@example.com", "user2@example.com"],
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["subject"], "Test Subject")
        self.assertEqual(
            call_kwargs["recipient_list"], ["user1@example.com", "user2@example.com"]
        )

    @override_settings(
        EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="dev@example.com"
    )
    @patch("utils.email.django_send_mail")
    def test_send_mail_dev_mode_redirects(self, mock_send):
        """Dev mode should redirect all emails to configured address."""
        mock_send.return_value = 1

        send_mail(
            subject="Test Subject",
            message="Test body",
            from_email="from@example.com",
            recipient_list=["user1@example.com", "user2@example.com"],
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        # Subject should include dev mode prefix and original recipients
        self.assertIn("[DEV MODE]", call_kwargs["subject"])
        self.assertIn("user1@example.com", call_kwargs["subject"])
        self.assertIn("user2@example.com", call_kwargs["subject"])
        # Should be redirected to dev address
        self.assertEqual(call_kwargs["recipient_list"], ["dev@example.com"])

    @override_settings(EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="")
    def test_send_mail_dev_mode_no_redirect_raises(self):
        """Dev mode without redirect address should raise ValueError."""
        with self.assertRaises(ValueError) as context:
            send_mail(
                subject="Test",
                message="Test",
                from_email="from@example.com",
                recipient_list=["user@example.com"],
            )
        self.assertIn("EMAIL_DEV_MODE_REDIRECT_TO", str(context.exception))

    @override_settings(
        EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="dev@example.com"
    )
    def test_dev_mode_email_message_redirects(self):
        """DevModeEmailMessage should redirect to dev address."""
        msg = DevModeEmailMessage(
            subject="Test Subject",
            body="Test body",
            from_email="from@example.com",
            to=["user1@example.com", "user2@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        # Should be redirected
        self.assertEqual(msg.to, ["dev@example.com"])
        self.assertEqual(msg.cc, [])
        self.assertEqual(msg.bcc, [])
        # Subject should include original recipients (first 3 shown, rest truncated)
        self.assertIn("[DEV MODE]", msg.subject)
        self.assertIn("user1@example.com", msg.subject)
        self.assertIn("user2@example.com", msg.subject)
        self.assertIn("cc@example.com", msg.subject)
        # With 4 total recipients, the 4th is truncated
        self.assertIn("and 1 more", msg.subject)

    @override_settings(EMAIL_DEV_MODE=False)
    def test_dev_mode_email_message_normal_mode(self):
        """DevModeEmailMessage should behave like normal EmailMessage when dev mode disabled."""
        msg = DevModeEmailMessage(
            subject="Test Subject",
            body="Test body",
            from_email="from@example.com",
            to=["user1@example.com", "user2@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        # Should NOT be redirected - recipients unchanged
        self.assertEqual(msg.to, ["user1@example.com", "user2@example.com"])
        self.assertEqual(msg.cc, ["cc@example.com"])
        self.assertEqual(msg.bcc, ["bcc@example.com"])
        # Subject should NOT be modified
        self.assertEqual(msg.subject, "Test Subject")
        self.assertNotIn("[DEV MODE]", msg.subject)


class SendMassMailTests(TestCase):
    """Tests for send_mass_mail dev mode functionality."""

    @override_settings(EMAIL_DEV_MODE=False)
    @patch("django.core.mail.send_mass_mail")
    def test_send_mass_mail_normal_mode(self, mock_send):
        """Normal mode should send to original recipients."""
        mock_send.return_value = 2

        datatuple = [
            ("Subject 1", "Body 1", "from@example.com", ["user1@example.com"]),
            ("Subject 2", "Body 2", "from@example.com", ["user2@example.com"]),
        ]
        send_mass_mail(datatuple)

        mock_send.assert_called_once()
        sent_datatuple = mock_send.call_args[0][0]
        self.assertEqual(sent_datatuple[0][0], "Subject 1")
        self.assertEqual(sent_datatuple[0][3], ["user1@example.com"])
        self.assertEqual(sent_datatuple[1][0], "Subject 2")
        self.assertEqual(sent_datatuple[1][3], ["user2@example.com"])

    @override_settings(
        EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="dev@example.com"
    )
    @patch("django.core.mail.send_mass_mail")
    def test_send_mass_mail_dev_mode_redirects(self, mock_send):
        """Dev mode should redirect all emails to configured address."""
        mock_send.return_value = 2

        datatuple = [
            ("Subject 1", "Body 1", "from@example.com", ["user1@example.com"]),
            ("Subject 2", "Body 2", "from@example.com", ["user2@example.com"]),
        ]
        send_mass_mail(datatuple)

        mock_send.assert_called_once()
        sent_datatuple = mock_send.call_args[0][0]
        # Subject should include dev mode prefix and original recipients
        self.assertIn("[DEV MODE]", sent_datatuple[0][0])
        self.assertIn("user1@example.com", sent_datatuple[0][0])
        self.assertIn("[DEV MODE]", sent_datatuple[1][0])
        self.assertIn("user2@example.com", sent_datatuple[1][0])
        # All emails should be redirected to dev address
        self.assertEqual(sent_datatuple[0][3], ["dev@example.com"])
        self.assertEqual(sent_datatuple[1][3], ["dev@example.com"])

    @override_settings(EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="")
    def test_send_mass_mail_dev_mode_no_redirect_raises(self):
        """Dev mode without redirect address should raise ValueError."""
        datatuple = [
            ("Subject", "Body", "from@example.com", ["user@example.com"]),
        ]
        with self.assertRaises(ValueError) as context:
            send_mass_mail(datatuple)
        self.assertIn("EMAIL_DEV_MODE_REDIRECT_TO", str(context.exception))
