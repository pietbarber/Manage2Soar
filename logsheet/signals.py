from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import send_mail
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import MaintenanceIssue
from .models import Flight
from django.db.models.signals import post_save
from django.dispatch import receiver
from notifications.models import Notification
from django.utils import timezone
from datetime import timedelta


@receiver(post_save, sender=MaintenanceIssue)
def notify_meisters_on_issue(sender, instance, created, **kwargs):
    if not created or instance.resolved:
        return
    # Only notify for oil/100hr/annual issues (simple keyword match)
    keywords = ["oil change", "100-hour", "annual"]
    if not any(k in (instance.description or "").lower() for k in keywords):
        return
    # Get all users in the "Meisters" group
    try:
        group = Group.objects.get(name="Meisters")
        recipients = list(group.user_set.values_list("email", flat=True))
    except Group.DoesNotExist:
        recipients = []
    recipients = [e for e in recipients if e]
    if not recipients:
        return
    subject = f"Maintenance Alert: {instance}"
    body = f"A maintenance issue has been created for {instance.glider or instance.towplane}:\n\n{instance.description}\n\nGrounded: {'Yes' if instance.grounded else 'No'}\nLogsheet: {instance.logsheet}\n"
    send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True
    )


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
    import logging

    logger = logging.getLogger(__name__)

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
        notif_msg = (
            f"You have an instruction flight to complete a report for {instance.pilot.full_display_name} on {date_str}."
        )
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
            user=recipient, message=notif_msg, url=notif_url)
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
