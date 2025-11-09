import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import NoReverseMatch, reverse

from members.models import Member

try:
    from notifications.models import Notification
except ImportError:
    # Notifications app may be optional in some deployments
    Notification = None

from .models import Question

logger = logging.getLogger(__name__)


def _create_notification_if_not_exists(user, message, url=None, dedup_key=None):
    """Create notification if similar one doesn't already exist (dedupe)."""
    if Notification is None:
        return None

    # Improved dedupe logic: use a unique key per question update to prevent
    # spam while allowing legitimate subsequent notifications
    if dedup_key:
        # Check if we already have an undismissed notification for this user
        # about this specific question update (using dedup_key)
        existing = Notification.objects.filter(
            user=user, dismissed=False, message__contains=dedup_key
        ).exists()
        if existing:
            logger.debug(
                "Notification suppressed (duplicate) for user=%s, dedup_key=%s",
                getattr(user, "pk", None),
                dedup_key,
            )
            return None

    return Notification.objects.create(user=user, message=message, url=url)


@receiver(post_save, sender=Question)
def notify_instructors_on_question_update(sender, instance, created, **kwargs):
    """
    Notify all instructors when a question in the test bank is updated.

    This implements issue #212 - when test content is updated, all instructors
    should be notified so they're aware of changes to the test bank.
    """
    try:
        if Notification is None:
            logger.debug(
                "Notification system not available, skipping question update notification"
            )
            return

        # Only notify on updates, not creation (to avoid spam when importing questions)
        if created:
            logger.debug("Question %s created, skipping notification", instance.qnum)
            return

        # Get all active instructors
        instructors = Member.objects.filter(instructor=True, is_active=True)

        logger.debug(
            "Found %d active instructors: %s",
            instructors.count(),
            [i.username for i in instructors],
        )

        if not instructors.exists():
            logger.debug(
                "No active instructors found, skipping question update notification"
            )
            return

        # Create the notification message
        updater_name = "Unknown"
        if instance.updated_by:
            updater_name = instance.updated_by.full_display_name

        category_name = (
            instance.category.description if instance.category else "Unknown Category"
        )

        # Create a unique deduplication key based on question, updater, and rough timestamp
        from django.utils import timezone

        update_time = timezone.now()
        timestamp = update_time.strftime("%Y-%m-%d %H:%M:%S")

        # Use update time to create a unique key for deduplication
        # This allows multiple legitimate updates while preventing immediate duplicates
        dedup_key = (
            f"Q{instance.qnum}_{updater_name}_{update_time.strftime('%Y%m%d_%H%M%S')}"
        )

        message = (
            f"Knowledge test question updated: Q{instance.qnum} ({category_name}) "
            f"has been modified by {updater_name} at {timestamp}. Review the updated test bank content. "
            f"[{dedup_key}]"
        )

        # Try to create a URL to the admin page for the question
        url = None
        try:
            url = reverse("admin:knowledgetest_question_change", args=[instance.qnum])
        except NoReverseMatch:
            logger.debug("Could not create admin URL for question %s", instance.qnum)
            url = None

        # Notify all instructors
        notifications_created = 0
        for instructor in instructors:
            notification = _create_notification_if_not_exists(
                instructor, message, url, dedup_key
            )
            if notification:
                notifications_created += 1

        logger.info(
            "Question %s updated - notified %d instructors",
            instance.qnum,
            notifications_created,
        )

    except Exception as e:
        logger.exception("Failed to notify instructors about question update: %s", e)
        # Don't re-raise from signal handlers to avoid breaking the main save operation
        return
