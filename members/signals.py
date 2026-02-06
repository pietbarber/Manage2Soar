"""
Signals for member-related notifications.
Notifies membership managers about important member events.
"""

import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

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

                # Prepare context for email templates
                context = {
                    "member": member,
                    "auto_approved": auto_approved,
                    "status_text": status_text,
                    "glider_rating": member.get_glider_rating_display()
                    or "Not specified",
                    "registration_time": member.date_joined.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "manage_member_url": build_absolute_url(
                        f"/admin/members/member/{member.pk}/change/"
                    ),
                    "all_visiting_pilots_url": build_absolute_url(
                        f"/admin/members/member/?membership_status__exact={config.visiting_pilot_status}"
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": get_canonical_url(),
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/visiting_pilot_notification.html", context
                )
                text_message = render_to_string(
                    "members/emails/visiting_pilot_notification.txt", context
                )

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        html_message=html_message,
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

                # Prepare context for email templates
                context = {
                    "application": application,
                    "submitted_at": application.submitted_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "review_application_url": build_absolute_url(
                        f"/members/applications/{application.application_id}/"
                    ),
                    "all_applications_url": build_absolute_url(
                        "/members/applications/"
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": get_canonical_url(),
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/application_submitted.html", context
                )
                text_message = render_to_string(
                    "members/emails/application_submitted.txt", context
                )

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        html_message=html_message,
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


def notify_membership_managers_of_withdrawal(application):
    """
    Send notifications to membership managers when an applicant withdraws their application.

    Args:
        application (MembershipApplication): The application that was withdrawn
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error(
                "SiteConfiguration not found - cannot send withdrawal notifications"
            )
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for application withdrawal notification"
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

                subject = f"Membership Application Withdrawn: {safe_name[:50]}"

                # Prepare context for email templates
                context = {
                    "application": application,
                    "submitted_at": application.submitted_at.strftime(
                        "%B %d, %Y at %I:%M %p"
                    ),
                    "view_application_url": build_absolute_url(
                        f"/members/applications/{application.application_id}/"
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": get_canonical_url(),
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/application_withdrawn.html", context
                )
                text_message = render_to_string(
                    "members/emails/application_withdrawn.txt", context
                )

                # Send email to all member managers
                for manager in member_managers:
                    if manager.email:
                        try:
                            send_mail(
                                subject=subject,
                                message=text_message,
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                recipient_list=[manager.email],
                                html_message=html_message,
                                fail_silently=False,
                            )
                            logger.info(
                                f"Sent withdrawal notification to {manager.email} for application {application.application_id}"
                            )
                        except Exception as email_error:
                            logger.error(
                                f"Failed to send withdrawal notification email to {manager.email}: {email_error}"
                            )

                logger.info(
                    f"Processed withdrawal notifications for application {application.application_id}"
                )

            except Exception as e:
                logger.error(f"Failed to send withdrawal notification emails: {e}")

        # In-app notification
        try:
            from notifications.models import Notification

            notification_message = (
                f"Membership application withdrawn: {safe_name} ({safe_email})"
            )

            for manager in member_managers:
                Notification.objects.create(
                    recipient=manager,
                    notification_type="membership_application_withdrawn",
                    title="Membership Application Withdrawn",
                    message=notification_message,
                    related_object_type="membership_application",
                    related_object_id=str(application.application_id),
                    priority="medium",
                )

            logger.info(
                f"Created in-app withdrawal notifications for application {application.application_id}"
            )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create withdrawal notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the withdrawal process
        logger.error(f"Failed to notify member managers of application withdrawal: {e}")
