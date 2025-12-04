"""
Email utilities with dev mode support.

This module provides email sending functions that respect EMAIL_DEV_MODE settings,
redirecting all emails to a configured address during development/testing.
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import send_mail as django_send_mail


def get_dev_mode_info():
    """Get dev mode configuration status.

    Returns:
        tuple: (is_enabled, redirect_to_address)
    """
    enabled = getattr(settings, "EMAIL_DEV_MODE", False)
    redirect_to = getattr(settings, "EMAIL_DEV_MODE_REDIRECT_TO", "")
    return enabled, redirect_to


def send_mail(
    subject,
    message,
    from_email,
    recipient_list,
    fail_silently=False,
    auth_user=None,
    auth_password=None,
    connection=None,
    html_message=None,
):
    """Send email with dev mode support.

    When EMAIL_DEV_MODE is enabled, all emails are redirected to
    EMAIL_DEV_MODE_REDIRECT_TO address. The original recipients are
    preserved in the subject line for debugging.

    Args:
        Same as django.core.mail.send_mail

    Returns:
        int: Number of successfully delivered messages (1 or 0)

    Raises:
        ValueError: If dev mode is enabled but no redirect address is configured
    """
    dev_mode, redirect_to = get_dev_mode_info()

    if dev_mode:
        if not redirect_to:
            raise ValueError(
                "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set. "
                "Set EMAIL_DEV_MODE_REDIRECT_TO or disable EMAIL_DEV_MODE."
            )

        # Preserve original recipients in subject for debugging
        original_recipients = ", ".join(recipient_list)
        subject = f"[DEV MODE] {subject} (TO: {original_recipients})"
        recipient_list = [redirect_to]

    return django_send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipient_list,
        fail_silently=fail_silently,
        auth_user=auth_user,
        auth_password=auth_password,
        connection=connection,
        html_message=html_message,
    )


def send_mass_mail(
    datatuple, fail_silently=False, auth_user=None, auth_password=None, connection=None
):
    """Send multiple emails with dev mode support.

    When EMAIL_DEV_MODE is enabled, all emails are redirected to
    EMAIL_DEV_MODE_REDIRECT_TO address.

    Args:
        datatuple: Sequence of (subject, message, from_email, recipient_list) tuples
        Other args same as django.core.mail.send_mass_mail

    Returns:
        int: Number of successfully delivered messages
    """
    from django.core.mail import send_mass_mail as django_send_mass_mail

    dev_mode, redirect_to = get_dev_mode_info()

    if dev_mode:
        if not redirect_to:
            raise ValueError(
                "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set. "
                "Set EMAIL_DEV_MODE_REDIRECT_TO or disable EMAIL_DEV_MODE."
            )

        # Redirect all emails
        modified_datatuple = []
        for subject, message, from_email, recipient_list in datatuple:
            original_recipients = ", ".join(recipient_list)
            modified_subject = f"[DEV MODE] {subject} (TO: {original_recipients})"
            modified_datatuple.append(
                (modified_subject, message, from_email, [redirect_to])
            )
        datatuple = modified_datatuple

    return django_send_mass_mail(
        datatuple,
        fail_silently=fail_silently,
        auth_user=auth_user,
        auth_password=auth_password,
        connection=connection,
    )


class DevModeEmailMessage(EmailMessage):
    """EmailMessage subclass with dev mode support.

    When EMAIL_DEV_MODE is enabled, emails are redirected to
    EMAIL_DEV_MODE_REDIRECT_TO address.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_dev_mode()

    def _apply_dev_mode(self):
        """Apply dev mode redirection if enabled."""
        dev_mode, redirect_to = get_dev_mode_info()

        if dev_mode:
            if not redirect_to:
                raise ValueError(
                    "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set."
                )

            # Preserve original recipients
            original_to = ", ".join(self.to) if self.to else "none"
            original_cc = ", ".join(self.cc) if self.cc else ""
            original_bcc = ", ".join(self.bcc) if self.bcc else ""

            recipients_info = f"TO: {original_to}"
            if original_cc:
                recipients_info += f", CC: {original_cc}"
            if original_bcc:
                recipients_info += f", BCC: {original_bcc}"

            self.subject = f"[DEV MODE] {self.subject} ({recipients_info})"
            self.to = [redirect_to]
            self.cc = []
            self.bcc = []
