"""
Signals for duty_roster app.

Handles notifications when:
- A student requests instruction (InstructionSlot created)
- An instructor accepts/rejects a request (instructor_response changes)
"""

import logging
import sys

from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse

from notifications.models import Notification
from siteconfig.models import SiteConfiguration
from utils.email import send_mail

logger = logging.getLogger(__name__)


def is_safe_to_run_signals():
    """
    Check if it's safe to run signal DB code.

    When running management commands that perform schema/data operations
    or test runs, we may want to avoid executing signal side-effects.
    """
    return apps.ready and not any(
        cmd in sys.argv
        for cmd in [
            "makemigrations",
            "migrate",
            "collectstatic",
            "loaddata",
        ]
    )


def _create_notification_if_not_exists(user, message, url=None):
    """
    Create a notification if one with the same message doesn't already exist.

    Simple message-based dedupe: if an undismissed notification exists with the
    same message, don't create another.
    """
    if Notification.objects.filter(
        user=user, dismissed=False, message=message
    ).exists():
        logger.debug(
            "Notification suppressed (duplicate) for user=%s", getattr(user, "pk", None)
        )
        return None
    return Notification.objects.create(user=user, message=message, url=url)


def _get_email_context(slot, config, site_url):
    """Build base context for email templates."""
    from instructors.models import StudentProgressSnapshot

    # Get student progress if available
    student_progress = None
    try:
        progress = StudentProgressSnapshot.objects.get(student=slot.student)
        # Create a simple dict that templates can access like an object
        student_progress = {
            "solo_progress": int((progress.solo_progress or 0) * 100),
            "checkride_progress": int((progress.checkride_progress or 0) * 100),
            "sessions": progress.sessions or 0,
        }
    except StudentProgressSnapshot.DoesNotExist:
        # Student has no progress snapshot yet - this is expected for new students
        pass

    # Get logo URL
    logo_url = None
    if config and config.club_logo:
        logo_url = config.club_logo.url
        if not logo_url.startswith(("http://", "https://")):
            logo_url = f"{site_url.rstrip('/')}{logo_url}"

    return {
        "student": slot.student,
        "instructor": slot.instructor or slot.assignment.instructor,
        "instruction_date": slot.assignment.date,
        "club_name": config.club_name if config else "Soaring Club",
        "club_logo_url": logo_url,
        "site_url": site_url,
        "student_progress": student_progress,
        "slot": slot,
    }


def _get_from_email(config):
    """Get the noreply@ from email address."""
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if "@" in default_from:
        domain = default_from.split("@")[-1]
        return f"noreply@{domain}"
    elif config and config.domain_name:
        return f"noreply@{config.domain_name}"
    else:
        return "noreply@manage2soar.com"


def send_student_signup_notification(slot):
    """
    Send email notification to instructor when a student signs up for instruction.

    Args:
        slot: InstructionSlot instance that was just created
    """
    from .models import InstructionSlot

    config = SiteConfiguration.objects.first()
    site_url = getattr(settings, "SITE_URL", "https://localhost:8000")

    # Determine which instructor(s) to notify
    # Primary instructor on the assignment, and surge instructor if present (and different)
    instructors_to_notify = []
    if slot.assignment.instructor:
        instructors_to_notify.append(slot.assignment.instructor)
    if (
        slot.assignment.surge_instructor
        and slot.assignment.surge_instructor != slot.assignment.instructor
    ):
        instructors_to_notify.append(slot.assignment.surge_instructor)

    if not instructors_to_notify:
        logger.warning(
            "No instructors assigned for date %s, cannot send notification",
            slot.assignment.date,
        )
        return

    context = _get_email_context(slot, config, site_url)
    context["review_url"] = f"{site_url}{reverse('duty_roster:instructor_requests')}"

    from_email = _get_from_email(config)

    for instructor in instructors_to_notify:
        if not instructor.email:
            logger.warning(
                "Instructor %s has no email, skipping notification",
                instructor.full_display_name,
            )
            continue

        context["instructor"] = instructor

        html_message = render_to_string(
            "instructors/emails/student_signup_notification.html", context
        )
        text_message = render_to_string(
            "instructors/emails/student_signup_notification.txt", context
        )

        subject = f"New instruction request from {slot.student.first_name} for {slot.assignment.date}"

        try:
            send_mail(
                subject=subject,
                message=text_message,
                from_email=from_email,
                recipient_list=[instructor.email],
                html_message=html_message,
            )
            logger.info(
                "Sent student signup notification to %s for student %s",
                instructor.email,
                slot.student.full_display_name,
            )
        except Exception as e:
            logger.exception(
                "Failed to send student signup notification to %s: %s",
                instructor.email,
                e,
            )

        # Also create in-system notification
        try:
            message = f"{slot.student.first_name} has requested instruction on {slot.assignment.date}."
            url = reverse("duty_roster:instructor_requests")
            _create_notification_if_not_exists(instructor, message, url=url)
        except Exception:
            logger.exception("Failed to create in-system notification for instructor")


def send_request_response_email(slot):
    """
    Send email notification to student when instructor accepts/rejects their request.

    Args:
        slot: InstructionSlot instance with updated instructor_response
    """
    if not slot.student or not slot.student.email:
        logger.warning(
            "Student %s has no email, skipping response notification",
            getattr(slot.student, "full_display_name", "unknown"),
        )
        return

    config = SiteConfiguration.objects.first()
    site_url = getattr(settings, "SITE_URL", "https://localhost:8000")

    context = _get_email_context(slot, config, site_url)
    context["is_accepted"] = slot.instructor_response == "accepted"
    context["response_status"] = (
        "Accepted" if slot.instructor_response == "accepted" else "Update"
    )
    context["instructor_note"] = slot.instructor_note or ""
    context["my_requests_url"] = (
        f"{site_url}{reverse('duty_roster:my_instruction_requests')}"
    )
    context["calendar_url"] = f"{site_url}{reverse('duty_roster:duty_calendar')}"

    from_email = _get_from_email(config)

    html_message = render_to_string("instructors/emails/request_response.html", context)
    text_message = render_to_string("instructors/emails/request_response.txt", context)

    if slot.instructor_response == "accepted":
        subject = (
            f"Your instruction request for {slot.assignment.date} has been confirmed!"
        )
    else:
        subject = f"Update on your instruction request for {slot.assignment.date}"

    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[slot.student.email],
            html_message=html_message,
        )
        logger.info(
            "Sent request response email to %s (response=%s)",
            slot.student.email,
            slot.instructor_response,
        )
    except Exception as e:
        logger.exception(
            "Failed to send request response email to %s: %s",
            slot.student.email,
            e,
        )

    # Also create in-system notification
    try:
        instructor = slot.instructor or slot.assignment.instructor
        instructor_name = instructor.first_name if instructor else "An instructor"
        if slot.instructor_response == "accepted":
            message = f"{instructor_name} has confirmed your instruction for {slot.assignment.date}!"
        else:
            message = f"{instructor_name} was unable to confirm your instruction request for {slot.assignment.date}."

        url = reverse("duty_roster:my_instruction_requests")
        _create_notification_if_not_exists(slot.student, message, url=url)
    except Exception:
        # Log the error but don't break the notification flow
        logger.exception("Failed to create in-system notification for student")


@receiver(pre_save, sender="duty_roster.InstructionSlot")
def store_original_instructor_response(sender, instance, **kwargs):
    """
    Store the original instructor_response before save so we can detect changes.

    Uses instance attribute instead of module-level dict to avoid concurrency
    issues and potential memory leaks with long-running processes.
    """
    if not is_safe_to_run_signals():
        return

    if instance.pk:
        try:
            from .models import InstructionSlot

            original = InstructionSlot.objects.get(pk=instance.pk)
            # Store on instance to avoid module-level state
            instance._original_instructor_response = original.instructor_response
        except sender.DoesNotExist:
            # Instance doesn't exist yet - this can happen during migrations
            pass


def _invalidate_instructor_cache_for_slot(instance):
    """
    Invalidate the instructor pending count cache for a slot's instructors.

    Args:
        instance: InstructionSlot instance
    """
    try:
        from duty_roster.context_processors import invalidate_instructor_pending_cache

        if instance.assignment.instructor:
            invalidate_instructor_pending_cache(instance.assignment.instructor.id)
        if instance.assignment.surge_instructor:
            invalidate_instructor_pending_cache(instance.assignment.surge_instructor.id)
    except (AttributeError, ImportError) as e:
        logger.exception("Failed to invalidate instructor pending cache: %s", e)


@receiver(post_save, sender="duty_roster.InstructionSlot")
def handle_instruction_slot_save(sender, instance, created, **kwargs):
    """
    Handle InstructionSlot saves:
    - If created with status=pending, notify instructor(s)
    - If instructor_response changed to accepted/rejected, notify student
    - Invalidate instructor pending count cache
    """
    if not is_safe_to_run_signals():
        return

    # Invalidate cache for affected instructors
    _invalidate_instructor_cache_for_slot(instance)

    try:
        if created and instance.status == "pending":
            # New request - notify instructor(s)
            send_student_signup_notification(instance)
        elif not created:
            # Check if instructor_response changed (stored in pre_save)
            original_response = getattr(instance, "_original_instructor_response", None)
            if (
                original_response
                and original_response != instance.instructor_response
                and instance.instructor_response in ("accepted", "rejected")
            ):
                # Response changed - notify student
                send_request_response_email(instance)
    except Exception:
        # Log error but don't re-raise to avoid breaking the save operation
        logger.exception("handle_instruction_slot_save failed")


@receiver(post_delete, sender="duty_roster.InstructionSlot")
def handle_instruction_slot_delete(sender, instance, **kwargs):
    """
    Handle InstructionSlot deletes:
    - Invalidate instructor pending count cache
    """
    if not is_safe_to_run_signals():
        return

    # Invalidate cache for affected instructors
    _invalidate_instructor_cache_for_slot(instance)
