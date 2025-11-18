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
from .models_applications import MembershipApplication

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


def notify_membership_managers_of_new_application(application):
    """
    Send notifications to membership managers about new membership application.
    Called directly from views when a new application is submitted.
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
                "No member managers or webmasters found for membership application notification"
            )
            return

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{application.first_name} {application.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = application.email.replace("\r", "").replace("\n", " ")
                safe_phone = (
                    (application.phone or "Not provided")
                    .replace("\r", "")
                    .replace("\n", " ")
                )
                safe_city = f"{application.city}, {application.state}".replace(
                    "\r", ""
                ).replace("\n", " ")

                subject = f"New Membership Application: {safe_name[:50]}"

                message_lines = [
                    f"A new membership application has been submitted through the club website.",
                    "",
                    "Applicant Details:",
                    f"- Name: {safe_name}",
                    f"- Email: {safe_email}",
                    f"- Phone: {safe_phone}",
                    f"- Location: {safe_city}",
                    f"- Application ID: {application.application_id}",
                    f"- Submission Time: {application.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "Application Status: Pending Review",
                    "",
                    "To review this application:",
                    "1. Log into the member management interface",
                    "2. Navigate to Membership Applications",
                    "3. Review the applicant's information and background",
                    "4. Approve, reject, or request additional information",
                    "",
                    "Management Links:",
                    f"- Review Application: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/members/applications/{application.application_id}/",
                    f"- All Applications: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/members/applications/",
                    "",
                    "This message was sent automatically by the club website membership system.",
                ]

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
                # Log the error but don't fail the application submission
                logger.error(
                    f"Failed to send membership application notification email: {e}"
                )

        # In-app notifications
        try:
            notification_message = (
                f"New membership application: {application.first_name} {application.last_name} "
                f"({application.city}, {application.state}) - pending review"
            )

            try:
                notification_url = reverse(
                    "members:membership_application_detail",
                    args=[application.application_id],
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create membership application notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the application submission
        logger.error(f"Failed to notify member managers of membership application: {e}")


def notify_membership_managers_of_application(application):
    """
    Send notifications to membership managers about new membership applications.
    Called directly from views when an application is submitted.

    Args:
        application (MembershipApplication): The application that was submitted
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
                "No member managers or webmasters found for membership application notification"
            )
            return

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{application.first_name} {application.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = application.email.replace("\r", "").replace("\n", " ")

                subject = f"New Membership Application: {safe_name[:50]}"

                message_lines = [
                    f"A new membership application has been submitted through the club website.",
                    "",
                    "Applicant Details:",
                    f"- Name: {safe_name}",
                    f"- Email: {safe_email}",
                    f"- Phone: {application.phone or 'Not provided'}",
                    f"- City, State: {application.city}, {application.state}",
                    f"- Application ID: {application.application_id}",
                    f"- Submission Time: {application.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "Pilot Experience:",
                    f"- Current Pilot: {'Yes' if application.pilot_ratings else 'No'}",
                ]

                if application.pilot_ratings:
                    message_lines.append(f"- Ratings: {application.pilot_ratings}")
                if application.certificates_licenses:
                    message_lines.append(
                        f"- Certificates: {application.certificates_licenses}"
                    )
                if application.total_flight_hours:
                    message_lines.append(
                        f"- Flight Hours: {application.total_flight_hours}"
                    )

                message_lines.extend(
                    [
                        "",
                        "Soaring Experience:",
                        f"- Previous Soaring: {'Yes' if application.previous_soaring_experience else 'No'}",
                    ]
                )

                if application.soaring_hours:
                    message_lines.append(
                        f"- Soaring Hours: {application.soaring_hours}"
                    )
                if application.glider_ownership:
                    message_lines.append(
                        f"- Glider Ownership: {application.glider_ownership}"
                    )

                message_lines.extend(
                    [
                        "",
                        f"- Interested in Learning: {'Yes' if application.interested_in_learning_to_fly else 'No'}",
                        f"- How They Heard: {application.how_did_you_hear or 'Not specified'}",
                        "",
                        "Review and Action Required:",
                        "1. Review the complete application in the member management system",
                        "2. Contact the applicant to schedule any required interviews or visits",
                        "3. Approve, waitlist, or request additional information",
                        "",
                        "Management Links:",
                        f"- View Application: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/members/applications/{application.application_id}/",
                        f"- All Applications: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://localhost:8000'}/members/applications/",
                        "",
                        "This message was sent automatically by the club website membership system.",
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
                # Log the error but don't fail the application submission
                logger.error(
                    f"Failed to send membership application notification email: {e}"
                )

        # In-app notifications
        try:
            notification_message = (
                f"New membership application from {application.first_name} {application.last_name} "
                f"({application.email}) - ID: {application.application_id}"
            )

            try:
                notification_url = reverse(
                    "members:membership_application_detail",
                    args=[application.application_id],
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create membership application notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the application submission
        logger.error(f"Failed to notify member managers of membership application: {e}")
