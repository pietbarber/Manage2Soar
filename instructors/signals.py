import logging
import sys

from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import NoReverseMatch, reverse

from members.models import MemberBadge
from notifications.models import Notification

from .models import GroundInstruction, InstructionReport, MemberQualification
from .utils import update_student_progress_snapshot

logger = logging.getLogger(__name__)


def _create_notification_if_not_exists(user, message, url=None):
    # Simple message-based dedupe: if an undismissed notification exists with the
    # same message, don't create another. Messages include actor/instructor and date
    # so multiple instructors on the same day create separate messages.
    if Notification.objects.filter(
        user=user, dismissed=False, message=message
    ).exists():
        logger.debug(
            "Notification suppressed (duplicate) for user=%s", getattr(user, "pk", None)
        )
        return None
    return Notification.objects.create(user=user, message=message, url=url)


@receiver(post_save, sender=InstructionReport)
def notify_student_on_instruction_report(sender, instance, created, **kwargs):
    try:
        student = instance.student
        instructor = instance.instructor
        date_str = instance.report_date.isoformat()
        message = f"{instructor.full_display_name} has added or updated the instruction record for {date_str}."
        # Build a link to the member's instruction-record page and anchor to
        # the recorded date (so the member sees the record inside the normal
        # page with site chrome/CSS/JS). Example:
        # /instructors/instruction-record/<member_id>/#flight-2025-10-11
        url = None
        try:
            date_str = instance.report_date.isoformat()
        except Exception:
            date_str = None

        try:
            base = (
                reverse("instructors:member_instruction_record", args=[student.pk])
                if student
                else None
            )
            if base and date_str:
                url = f"{base}#flight-{date_str}"
            else:
                url = base
        except NoReverseMatch:
            try:
                url = (
                    reverse("members:member_view", args=[student.pk])
                    if student
                    else None
                )
            except NoReverseMatch:
                url = None
        _create_notification_if_not_exists(student, message, url=url)
    except Exception:
        logger.exception("notify_student_on_instruction_report failed")
        # Don't re-raise from signal handlers; swallowing prevents breaking
        # the main save operation (tests and production rely on this pattern).
        return


@receiver(post_save, sender=GroundInstruction)
def notify_student_on_ground_instruction(sender, instance, created, **kwargs):
    try:
        student = instance.student
        instructor = instance.instructor
        date_str = instance.date.isoformat()
        message = f"A ground instruction session with {instructor.full_display_name} on {date_str} was recorded."
        # Link to the member's instruction-record page and anchor to the ground
        # instruction date so the student sees it in the full page (not modal).
        url = None
        try:
            base = (
                reverse("instructors:member_instruction_record", args=[student.pk])
                if student
                else None
            )
            if base:
                url = f"{base}#ground-{date_str}"
            else:
                url = None
        except NoReverseMatch:
            try:
                url = (
                    reverse("members:member_view", args=[student.pk])
                    if student
                    else None
                )
            except NoReverseMatch:
                url = None
        _create_notification_if_not_exists(student, message, url=url)
    except Exception:
        logger.exception("notify_student_on_ground_instruction failed")
        # Avoid re-raising inside signal handlers
        return


@receiver(post_save, sender=MemberQualification)
def notify_member_on_qualification(sender, instance, created, **kwargs):
    try:
        member = instance.member
        instr = instance.instructor
        date_str = (
            instance.date_awarded.isoformat() if instance.date_awarded else "recently"
        )
        # qualification may be created with a qualification_id that doesn't
        # correspond to an existing ClubQualificationType in tests; guard access
        try:
            qual_name = instance.qualification.name
        except Exception:
            qual_name = (
                f"qualification #{getattr(instance, 'qualification_id', 'unknown')}"
            )

        message = f"You've been awarded the qualification {qual_name} by {instr.full_display_name if instr else 'the club'} on {date_str}."
        try:
            url = (
                reverse("members:member_profile", args=[member.pk]) if member else None
            )
        except NoReverseMatch:
            url = None
        _create_notification_if_not_exists(member, message, url=url)
    except Exception:
        logger.exception("notify_member_on_qualification failed")
        # Avoid re-raising inside signal handlers
        return


@receiver(post_save, sender=MemberBadge)
def notify_member_on_badge(sender, instance, created, **kwargs):
    try:
        member = instance.member
        badge = instance.badge
        date_str = (
            instance.date_awarded.isoformat()
            if getattr(instance, "date_awarded", None)
            else "recently"
        )
        message = f"You've received a new badge: {badge.name} on {date_str}."
        try:
            url = reverse("members:badge_board")
        except NoReverseMatch:
            url = None
        _create_notification_if_not_exists(member, message, url=url)
    except Exception:
        logger.exception("notify_member_on_badge failed")
        # Avoid re-raising inside signal handlers
        return


# instructors/signals.py


# Utility to check if it's safe to run signal DB code


def is_safe_to_run_signals():
    # When running management commands that perform schema/data operations
    # or test runs, we may want to avoid executing signal side-effects.
    # Note: many developers run tests with pytest (argv contains 'pytest'),
    # while Django's test runner uses 'test' in sys.argv. Check for both.
    return apps.ready and not any(
        cmd in sys.argv
        for cmd in [
            "makemigrations",
            "migrate",
            "collectstatic",
            "loaddata",
            "test",
            "pytest",
        ]
    )


####################################################
# Signal handlers for updating StudentProgressSnapshot
#
# These receivers listen for post-save events on InstructionReport
# and GroundInstruction models, and trigger a refresh of the
# StudentProgressSnapshot for the affected student.
####################################################


@receiver(post_save, sender=InstructionReport)
def instruction_report_saved(sender, instance, **kwargs):
    """
    Handler for InstructionReport saves.

    Whenever an InstructionReport is created or updated, this
    signal fires and calls update_student_progress_snapshot()
    for the report's student to keep the snapshot in sync.
    """
    if not is_safe_to_run_signals():
        return
    update_student_progress_snapshot(instance.student)


@receiver(post_save, sender=GroundInstruction)
def ground_instruction_saved(sender, instance, **kwargs):
    """
    Handler for GroundInstruction saves.

    Whenever a GroundInstruction session is created or updated,
    this signal fires and calls update_student_progress_snapshot()
    for the session's student to update the snapshot accordingly.
    """
    if not is_safe_to_run_signals():
        return
    update_student_progress_snapshot(instance.student)
