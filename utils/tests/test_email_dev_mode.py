"""Tests for the dev mode email utility."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from utils.email import DevModeEmailMessage, get_dev_mode_info, send_mail


class DevModeEmailTests(TestCase):
    """Tests for email dev mode functionality."""

    def test_get_dev_mode_info_disabled_by_default(self):
        """Dev mode should be disabled by default."""
        enabled, redirect_to = get_dev_mode_info()
        self.assertFalse(enabled)
        self.assertEqual(redirect_to, "")

    @override_settings(
        EMAIL_DEV_MODE=True, EMAIL_DEV_MODE_REDIRECT_TO="test@example.com"
    )
    def test_get_dev_mode_info_enabled(self):
        """Dev mode settings should be readable when enabled."""
        enabled, redirect_to = get_dev_mode_info()
        self.assertTrue(enabled)
        self.assertEqual(redirect_to, "test@example.com")

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
        call_kwargs = mock_send.call_args
        self.assertEqual(call_kwargs[1]["subject"], "Test Subject")
        self.assertEqual(
            call_kwargs[1]["recipient_list"], ["user1@example.com", "user2@example.com"]
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
        call_kwargs = mock_send.call_args
        # Subject should include dev mode prefix and original recipients
        self.assertIn("[DEV MODE]", call_kwargs[1]["subject"])
        self.assertIn("user1@example.com", call_kwargs[1]["subject"])
        self.assertIn("user2@example.com", call_kwargs[1]["subject"])
        # Should be redirected to dev address
        self.assertEqual(call_kwargs[1]["recipient_list"], ["dev@example.com"])

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
        # Subject should include original recipients
        self.assertIn("[DEV MODE]", msg.subject)
        self.assertIn("user1@example.com", msg.subject)
        self.assertIn("cc@example.com", msg.subject)
        self.assertIn("bcc@example.com", msg.subject)
