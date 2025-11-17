"""
Signals for member-related notifications.
Notifies membership managers about important member events.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from notifications.models import Notification
from siteconfig.models import SiteConfiguration

from .models import Member

logger = logging.getLogger(__name__)


def _create_notification_if_not_exists(user, message, url=None):
    """Create notification if similar one doesn't already exist (dedupe)."""
    try:
        from notifications.models import Notification

        # Check if we already have an undismissed notification for this user
        # with the same message to prevent spam
        existing = Notification.objects.filter(
            user=user, dismissed=False, message=message
        ).exists()
        if existing:
            logger.debug(
                "Notification suppressed (duplicate) for user=%s, message=%s",
                getattr(user, "pk", None),
                message[:50],
            )
            return None

        return Notification.objects.create(user=user, message=message, url=url)
    except ImportError:
        # Notifications app not available
        return None


def _notify_member_managers_of_visiting_pilot(member):
    """
    Send notifications to member managers about new visiting pilot registration.
    Based on the membership manager workflow requirements.
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error("SiteConfiguration not found - cannot send notifications")
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for visiting pilot notification"
            )
            return

        # Prepare notification content
        auto_approved = getattr(config, "visiting_pilot_auto_approve", False)
        status_text = "activated" if auto_approved else "pending approval"

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{member.first_name} {member.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = member.email.replace("\r", "").replace("\n", " ")
                safe_home_club = (
                    (member.home_club or "Unknown Club")
                    .replace("\r", "")
                    .replace("\n", " ")
                )
                safe_ssa = (
                    (member.SSA_member_number or "Not provided")
                    .replace("\r", "")
                    .replace("\n", " ")
                )

                subject = f"New Visiting Pilot Registration: {safe_name[:50]}"

                message_lines = [
                    f"A new visiting pilot has registered through the club website.",
                    "",
                    "Visiting Pilot Details:",
                    f"- Name: {safe_name}",
                    f"- Email: {safe_email}",
                    f"- Home Club: {safe_home_club}",
                    f"- SSA Number: {safe_ssa}",
                    f"- Glider Rating: {member.get_glider_rating_display() or 'Not specified'}",
                    f"- Status: {status_text.title()}",
                    f"- Registration Time: {member.date_joined.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                ]

                if auto_approved:
                    message_lines.extend(
                        [
                            "This visiting pilot has been automatically approved and can now:",
                            "- Be added to flight logs by duty officers",
                            "- Appear in pilot/instructor/tow pilot dropdowns",
                            "",
                            "No further action required unless there are concerns.",
                        ]
                    )
                else:
                    message_lines.extend(
                        [
                            "This registration requires manual approval. To activate:",
                            "1. Review the visiting pilot's information below",
                            "2. Log into the admin interface",
                            "3. Navigate to Members and find this visiting pilot",
                            "4. Set 'Active' status to enable flight logging",
                            "",
                        ]
                    )

                message_lines.extend(
                    [
                        "Admin Interface Links:",
                        f"- Manage Member: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/admin/members/member/{member.pk}/change/",
                        f"- All Visiting Pilots: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/admin/members/member/?membership_status__exact={config.visiting_pilot_status}",
                        "",
                        "This message was sent automatically by the club website visiting pilot system.",
                    ]
                )

                message = "\n".join(message_lines)

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        fail_silently=False,  # We want to know if email fails
                    )

            except Exception as e:
                # Log the error but don't fail the registration
                logger.error(f"Failed to send visiting pilot notification email: {e}")

        # In-app notifications
        try:
            notification_message = (
                f"New visiting pilot registered: {member.first_name} {member.last_name} "
                f"({member.home_club or 'Unknown Club'}) - {status_text}"
            )

            try:
                notification_url = reverse(
                    "admin:members_member_change", args=[member.pk]
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create visiting pilot notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the registration
        logger.error(
            f"Failed to notify member managers of visiting pilot registration: {e}"
        )


@receiver(post_save, sender=Member)
def notify_member_managers_of_visiting_pilot(sender, instance, created, **kwargs):
    """
    Signal handler that notifies member managers when a visiting pilot registers.

    This signal is triggered on Member post_save to check if a new visiting pilot
    has registered and needs approval notifications sent to member managers.
    """

    if not created:
        return  # Only notify on creation, not updates

    try:
        # Check if this is a visiting pilot by checking membership status
        config = SiteConfiguration.objects.first()
        if not config or not config.visiting_pilot_enabled:
            return

        # Check if this member is a visiting pilot
        if (
            hasattr(config, "visiting_pilot_status")
            and config.visiting_pilot_status
            and instance.membership_status == config.visiting_pilot_status
        ):
            logger.info(
                f"New visiting pilot detected: {instance.email} ({instance.first_name} {instance.last_name})"
            )
            _notify_member_managers_of_visiting_pilot(instance)

    except Exception as e:
        # Log the error but don't fail the member creation
        logger.error(f"Failed to process visiting pilot notification signal: {e}")
