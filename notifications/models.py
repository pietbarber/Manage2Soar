from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# Member-facing display window (Issue #1168): notifications older than this
# rolling interval are hidden from member-facing displays (page-top block and
# the notifications page). This is a *display* policy, not a retention policy:
# records are not deleted here and remain in the database until the separate
# ``cleanup_old_notifications`` command purges them.
DISPLAY_WINDOW_DAYS = 30


class NotificationQuerySet(models.QuerySet):
    def for_display(self, user):
        """Return the notifications visible to ``user`` in member-facing displays.

        A rolling ``DISPLAY_WINDOW_DAYS`` window applied in the database query:
        undismissed notifications with ``created_at`` at or after
        ``timezone.now() - timedelta(days=DISPLAY_WINDOW_DAYS)``, newest first.
        A notification exactly at the cutoff is eligible; older ones are
        excluded. Viewing never deletes or mutates the underlying records.
        """
        cutoff = timezone.now() - timedelta(days=DISPLAY_WINDOW_DAYS)
        return self.filter(
            user=user,
            dismissed=False,
            created_at__gte=cutoff,
        ).order_by("-created_at")


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.TextField()
    url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)
    contact_submission = models.ForeignKey(
        "cms.VisitorContact",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.user}: {self.message[:50]}"
