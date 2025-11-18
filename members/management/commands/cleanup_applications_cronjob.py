"""
CronJob command to automatically clean up old approved membership applications.

This command runs annually on New Year's Eve via the distributed CronJob system
and removes approved membership applications that are older than 365 days (1 year).

Provides annual housekeeping while maintaining full year audit trail.
Part of the membership application lifecycle management.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from members.models_applications import MembershipApplication
from utils.management.commands.base_cronjob import BaseCronJobCommand

logger = logging.getLogger(__name__)


class Command(BaseCronJobCommand):
    help = "CronJob: Clean up membership applications approved more than 365 days ago"
    job_name = "cleanup_approved_applications"

    # Run annually on New Year's Eve (December 31st) at 11:30 PM
    cron_expression = "30 23 31 12 *"

    def execute_job(self, *args, **options):
        """Clean up approved applications older than 365 days (1 year)."""
        days_to_keep = 365
        cutoff_date = timezone.now() - timedelta(days=days_to_keep)

        # Find old approved applications
        old_applications = MembershipApplication.objects.filter(
            status="approved", reviewed_at__lt=cutoff_date
        ).select_related("member_account")

        count = old_applications.count()

        if count == 0:
            logger.info(
                f"Annual cleanup: No approved applications older than {days_to_keep} days found"
            )
            return

        logger.info(
            f"Annual cleanup: Found {count} approved applications to clean up (older than {days_to_keep} days)"
        )

        # Delete old applications
        deleted_count = 0
        for app in old_applications:
            try:
                app_info = f"{app.full_name} (ID: {app.application_id})"
                days_old = (
                    (timezone.now() - app.reviewed_at).days
                    if app.reviewed_at
                    else "unknown"
                )

                app.delete()
                deleted_count += 1
                logger.info(
                    f"Annual cleanup: Deleted approved application: {app_info} ({days_old} days old)"
                )

            except Exception as e:
                logger.error(f"Failed to delete application {app.application_id}: {e}")

        logger.info(
            f"Annual cleanup: Successfully cleaned up {deleted_count} out of {count} approved applications"
        )
