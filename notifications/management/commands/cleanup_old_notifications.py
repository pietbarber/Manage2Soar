from datetime import timedelta

from django.utils.timezone import now

from notifications.models import Notification
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Purge notifications older than 60 days to prevent accumulation of stale notifications"
    job_name = "cleanup_old_notifications"
    # Allow time for large cleanup operations
    max_execution_time = timedelta(minutes=30)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--days",
            type=int,
            default=60,
            help="Number of days after which notifications are purged (default: 60)",
        )

    def execute_job(self, *args, **options):
        purge_days = options.get("days", 60)
        cutoff_date = now() - timedelta(days=purge_days)

        self.log_info(
            f"Looking for notifications older than {purge_days} days (before {cutoff_date.date()})"
        )

        # Find notifications older than the cutoff (both dismissed and undismissed)
        old_notifications = Notification.objects.filter(
            created_at__lt=cutoff_date
        ).select_related("user")

        if not old_notifications.exists():
            self.log_info("No old notifications found to purge")
            return 0

        notification_count = old_notifications.count()

        # Get stats for logging
        dismissed_count = old_notifications.filter(dismissed=True).count()
        undismissed_count = notification_count - dismissed_count

        self.log_info(
            f"Found {notification_count} old notification(s): "
            f"{dismissed_count} dismissed, {undismissed_count} undismissed"
        )

        if not options.get("dry_run"):
            # Perform the actual deletion
            deleted_count, _ = old_notifications.delete()

            self.log_success(
                f"Successfully purged {deleted_count} notification(s) older than {purge_days} days"
            )
        else:
            self.log_info(
                f"Would purge {notification_count} notification(s) older than {purge_days} days"
            )

        return notification_count
