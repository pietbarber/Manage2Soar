import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse

from notifications.models import Notification
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

from .models import Flight, MaintenanceIssue

logger = logging.getLogger(__name__)


def _create_notification_if_not_exists(user, message, url=None):
    """Create a Notification for user unless an undismissed identical message exists.

    This mirrors the message-based dedupe pattern used elsewhere in the project.
    """
    if user is None:
        return None
    try:
        existing = Notification.objects.filter(
            user=user, dismissed=False, message=message
        )
        if existing.exists():
            return None
        return Notification.objects.create(user=user, message=message, url=url)
    except Exception:
        logger.exception("_create_notification_if_not_exists: failed")
        return None


def _get_club_config():
    """Get SiteConfiguration for email context."""
    from siteconfig.models import SiteConfiguration

    return SiteConfiguration.objects.first()


def _send_maintenance_issue_email(issue, meisters):
    """Send email notification to meisters about a new maintenance issue.

    Issue #463: Send maintenance issue emails immediately when created,
    rather than waiting for logsheet finalization.
    """
    if not meisters:
        return

    config = _get_club_config()
    aircraft = issue.glider or issue.towplane
    aircraft_type = "Glider" if issue.glider else "Towplane"

    maintenance_url = build_absolute_url(reverse("logsheet:maintenance_issues"))

    context = {
        "aircraft": str(aircraft),
        "aircraft_type": aircraft_type,
        "description": issue.description,
        "grounded": issue.grounded,
        "reported_by": (
            issue.reported_by.full_display_name if issue.reported_by else "Unknown"
        ),
        "logsheet_date": (
            issue.logsheet.log_date.strftime("%B %d, %Y") if issue.logsheet else "N/A"
        ),
        "club_name": config.club_name if config else "Soaring Club",
        "club_logo_url": get_absolute_club_logo_url(config),
        "site_url": get_canonical_url(),
        "maintenance_url": maintenance_url,
    }

    # Render email templates
    html_message = render_to_string(
        "logsheet/emails/maintenance_issue_notification.html", context
    )
    text_message = render_to_string(
        "logsheet/emails/maintenance_issue_notification.txt", context
    )

    # Build recipient list
    recipient_emails = [
        meister.member.email
        for meister in meisters
        if meister.member and meister.member.email
    ]

    if not recipient_emails:
        logger.warning("No valid email addresses for meisters of aircraft %s", aircraft)
        return

    # Build subject line
    subject_prefix = "⚠️ GROUNDED: " if issue.grounded else "🔧 "
    club_name = config.club_name if config else "Club"
    subject = f"{subject_prefix}[{club_name}] Maintenance Issue - {aircraft}"

    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_emails,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(
            "Sent maintenance issue email for %s to %d meister(s)",
            aircraft,
            len(recipient_emails),
        )
    except Exception as e:
        logger.exception(
            "Failed to send maintenance issue email for %s: %s", aircraft, e
        )


@receiver(post_save, sender=MaintenanceIssue)
def notify_meisters_on_issue(sender, instance, created, **kwargs):
    """Notify assigned AircraftMeister members on creation and important updates.

    Issue #463: Send email immediately when a maintenance issue is created,
    rather than waiting for logsheet finalization. This ensures meisters are
    notified promptly about aircraft problems.
    """
    try:
        # On create: notify all meisters assigned to the affected aircraft
        # Issue #463: Send email IMMEDIATELY (don't wait for finalization)
        if created:
            if instance.glider:
                meisters = instance.glider.aircraftmeister_set.select_related(
                    "member"
                ).all()
            elif instance.towplane:
                meisters = instance.towplane.aircraftmeister_set.select_related(
                    "member"
                ).all()
            else:
                meisters = []

            if not meisters:
                return

            # Send email notification immediately (Issue #463)
            _send_maintenance_issue_email(instance, meisters)

            # Also create in-app notifications
            message = f"Maintenance issue reported for {instance.glider or instance.towplane}: {instance.description[:100]}"
            try:
                url = reverse("logsheet:maintenance_issues")
            except Exception:
                url = None

            for meister in meisters:
                _create_notification_if_not_exists(meister.member, message, url=url)
            return

        # On update: notify when issue is resolved (resolved field flips to True)
        # We capture previous resolved state in pre_save to detect transitions reliably.
        prev_resolved = getattr(instance, "_previous_resolved", False)
        if not prev_resolved and instance.resolved:
            # Issue was just resolved
            if instance.glider:
                meisters = instance.glider.aircraftmeister_set.select_related(
                    "member"
                ).all()
            elif instance.towplane:
                meisters = instance.towplane.aircraftmeister_set.select_related(
                    "member"
                ).all()
            else:
                meisters = []

            if not meisters:
                return

            resolver = (
                instance.resolved_by.full_display_name
                if instance.resolved_by
                else "someone"
            )
            message = f"Maintenance issue resolved for {instance.glider or instance.towplane} by {resolver}: {instance.description[:100]}"
            try:
                url = reverse("logsheet:maintenance_issues")
            except Exception:
                url = None

            for meister in meisters:
                _create_notification_if_not_exists(meister.member, message, url=url)
    except Exception:
        logger.exception("notify_meisters_on_issue: unexpected exception")
        return


@receiver(pre_save, sender=MaintenanceIssue)
def capture_previous_maintenance_state(sender, instance, **kwargs):
    try:
        if instance.pk:
            prev = sender.objects.filter(pk=instance.pk).first()
            instance._previous_resolved = getattr(prev, "resolved", False)
        else:
            instance._previous_resolved = False
    except Exception:
        instance._previous_resolved = False


# Capture previous status before save so post_save can detect transitions
@receiver(pre_save, sender=Flight)
def capture_previous_flight_status(sender, instance, **kwargs):
    try:
        if instance.pk:
            prev = sender.objects.filter(pk=instance.pk).first()
            instance._previous_status = getattr(prev, "status", None)
        else:
            instance._previous_status = None
    except Exception:
        # Don't let diagnostics break saving
        instance._previous_status = None


# Notify instructors when a flight with a pilot and instructor is created
@receiver(post_save, sender=Flight)
def notify_instructor_on_flight_created(sender, instance, created, **kwargs):
    # Use module-level logger (defined at top of this module)

    # Only proceed when a new flight is created OR when an existing flight
    # transitions from not-landed to landed (i.e., landing_time added).
    if not created:
        prev_status = getattr(instance, "_previous_status", None)
        curr_status = getattr(instance, "status", None)
        # If it didn't transition to landed, skip
        if not (prev_status != "landed" and curr_status == "landed"):
            logger.debug(
                "notify_instructor_on_flight_created: skipped because not created and not transitioned to landed (prev=%s curr=%s pk=%s)",
                prev_status,
                curr_status,
                getattr(instance, "pk", None),
            )
            return
    # Ensure both pilot and instructor are set and are different
    if not instance.pilot or not instance.instructor:
        logger.debug(
            "notify_instructor_on_flight_created: skipped because missing pilot/instructor (pilot=%s instructor=%s)",
            getattr(instance, "pilot", None),
            getattr(instance, "instructor", None),
        )
        return
    # Avoid notifying if pilot and instructor are the same person
    if instance.pilot == instance.instructor:
        logger.debug(
            "notify_instructor_on_flight_created: skipped because pilot == instructor (member=%s)",
            instance.pilot,
        )
        return

    # Only notify for completed flights. Use the model's `status` property so we
    # capture the same logic as the rest of the codebase (e.g. admin/imports).
    if getattr(instance, "status", None) != "landed":
        logger.debug(
            "notify_instructor_on_flight_created: skipped because status != 'landed' (status=%s, pk=%s)",
            getattr(instance, "status", None),
            getattr(instance, "pk", None),
        )
        return

    # Build a notification message and dedupe by instructor + log_date
    try:
        log_date = getattr(instance.logsheet, "log_date", None)
        date_str = log_date.isoformat() if log_date else "recent date"
        notif_msg = f"You have an instruction flight to complete a report for {instance.pilot.full_display_name} on {date_str}."
        recipient = instance.instructor

        # Dedupe: only create one notification per instructor per exact log_date
        if log_date:
            # Dedupe by checking for an existing notification that includes the exact date
            date_str = log_date.isoformat()
            existing = Notification.objects.filter(
                user=recipient,
                dismissed=False,
                message__contains=date_str,
            )
            if existing.exists():
                return

        # Point the notification to the instructors dashboard where pending reports are listed
        try:
            from django.urls import reverse

            notif_url = reverse("instructors:instructors-dashboard")
        except Exception:
            notif_url = None

        notif = Notification.objects.create(
            user=recipient, message=notif_msg, url=notif_url
        )
        logger.info(
            "notify_instructor_on_flight_created: created notification id=%s for user=%s flight=%s",
            notif.pk,
            recipient.pk if recipient else None,
            getattr(instance, "pk", None),
        )
    except Exception:
        # Don't raise in signals
        logger.exception("notify_instructor_on_flight_created: unexpected exception")
        return
