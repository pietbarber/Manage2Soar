"""
Email utilities with dev mode support.

This module provides email sending functions that respect EMAIL_DEV_MODE settings,
redirecting all emails to configured address(es) during development/testing.

Note: EMAIL_DEV_MODE works regardless of the DEBUG setting. However, when DEBUG=True,
Django uses the console email backend which only prints emails to console (not sending
them), so dev mode redirection has no practical effect in that case. EMAIL_DEV_MODE
is primarily useful for staging/production environments where real SMTP is configured.
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import send_mail as django_send_mail


def get_dev_mode_info():
    """Get dev mode configuration status.

    Returns:
        tuple: (is_enabled, list_of_redirect_addresses)
    """
    enabled = getattr(settings, "EMAIL_DEV_MODE", False)
    redirect_to = getattr(settings, "EMAIL_DEV_MODE_REDIRECT_TO", "")
    # Support comma-separated list of addresses
    if redirect_to:
        redirect_list = [
            addr.strip() for addr in redirect_to.split(",") if addr.strip()
        ]
    else:
        redirect_list = []
    return enabled, redirect_list


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
    EMAIL_DEV_MODE_REDIRECT_TO address(es). The original recipients are
    preserved in the subject line for debugging.

    Args:
        Same as django.core.mail.send_mail

    Returns:
        int: Number of successfully delivered messages (1 or 0)

    Raises:
        ValueError: If dev mode is enabled but no redirect address is configured
    """
    dev_mode, redirect_list = get_dev_mode_info()

    if dev_mode:
        if not redirect_list:
            raise ValueError(
                "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set. "
                "Set EMAIL_DEV_MODE_REDIRECT_TO or disable EMAIL_DEV_MODE."
            )

        # Preserve original recipients in subject for debugging
        # Truncate long recipient lists to avoid email server subject line limits
        MAX_RECIPIENTS_IN_SUBJECT = 3
        if not recipient_list:
            original_recipients = "no recipients"
        elif len(recipient_list) > MAX_RECIPIENTS_IN_SUBJECT:
            shown = recipient_list[:MAX_RECIPIENTS_IN_SUBJECT]
            remaining = len(recipient_list) - MAX_RECIPIENTS_IN_SUBJECT
            original_recipients = ", ".join(shown) + f", ... and {remaining} more"
        else:
            original_recipients = ", ".join(recipient_list)
        subject = f"[DEV MODE] {subject} (TO: {original_recipients})"
        recipient_list = redirect_list

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
    EMAIL_DEV_MODE_REDIRECT_TO address(es).

    Args:
        datatuple: Sequence of (subject, message, from_email, recipient_list) tuples
        Other args same as django.core.mail.send_mass_mail

    Returns:
        int: Number of successfully delivered messages
    """
    from django.core.mail import send_mass_mail as django_send_mass_mail

    dev_mode, redirect_list = get_dev_mode_info()

    if dev_mode:
        if not redirect_list:
            raise ValueError(
                "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set. "
                "Set EMAIL_DEV_MODE_REDIRECT_TO or disable EMAIL_DEV_MODE."
            )

        # Redirect all emails
        # Truncate long recipient lists to avoid email server subject line limits
        MAX_RECIPIENTS_IN_SUBJECT = 3
        modified_datatuple = []
        for subject, message, from_email, recipient_list in datatuple:
            if not recipient_list:
                original_recipients = "no recipients"
            elif len(recipient_list) > MAX_RECIPIENTS_IN_SUBJECT:
                shown = recipient_list[:MAX_RECIPIENTS_IN_SUBJECT]
                remaining = len(recipient_list) - MAX_RECIPIENTS_IN_SUBJECT
                original_recipients = ", ".join(shown) + f", ... and {remaining} more"
            else:
                original_recipients = ", ".join(recipient_list)
            modified_subject = f"[DEV MODE] {subject} (TO: {original_recipients})"
            modified_datatuple.append(
                (modified_subject, message, from_email, redirect_list)
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
    EMAIL_DEV_MODE_REDIRECT_TO address(es).

    Use this class when you need to construct EmailMessage objects directly
    instead of using send_mail(). This is useful for HTML emails with attachments
    or when you need more control over the email structure.

    Example:
        from utils.email import DevModeEmailMessage

        msg = DevModeEmailMessage(
            subject="Welcome!",
            body="Your account is ready.",
            from_email="noreply@example.com",
            to=["user@example.com"],
        )
        msg.send()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_dev_mode()

    def _apply_dev_mode(self):
        """Apply dev mode redirection if enabled."""
        dev_mode, redirect_list = get_dev_mode_info()

        if dev_mode:
            if not redirect_list:
                raise ValueError(
                    "EMAIL_DEV_MODE is enabled but EMAIL_DEV_MODE_REDIRECT_TO is not set. "
                    "Set EMAIL_DEV_MODE_REDIRECT_TO or disable EMAIL_DEV_MODE."
                )

            # Collect all original recipients
            all_recipients = (
                list(self.to or []) + list(self.cc or []) + list(self.bcc or [])
            )

            # Handle empty recipients case
            if not all_recipients:
                recipients_info = "TO: (no recipients)"
            else:
                # Truncate long recipient lists
                MAX_RECIPIENTS_IN_SUBJECT = 3
                if len(all_recipients) > MAX_RECIPIENTS_IN_SUBJECT:
                    shown = all_recipients[:MAX_RECIPIENTS_IN_SUBJECT]
                    remaining = len(all_recipients) - MAX_RECIPIENTS_IN_SUBJECT
                    recipients_info = (
                        f"TO: {', '.join(shown)}, ... and {remaining} more"
                    )
                else:
                    # Build detailed recipient info for short lists
                    original_to = ", ".join(self.to) if self.to else "none"
                    original_cc = ", ".join(self.cc) if self.cc else ""
                    original_bcc = ", ".join(self.bcc) if self.bcc else ""

                    recipients_info = f"TO: {original_to}"
                    if original_cc:
                        recipients_info += f", CC: {original_cc}"
                    if original_bcc:
                        recipients_info += f", BCC: {original_bcc}"

            self.subject = f"[DEV MODE] {self.subject} ({recipients_info})"
            self.to = redirect_list
            self.cc = []
            self.bcc = []
