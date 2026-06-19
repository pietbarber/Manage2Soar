from datetime import timedelta

from django.utils import timezone

from duty_roster.views_swap import send_periodic_open_swap_reminder_notifications
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Send periodic reminder emails for open duty swap requests"
    job_name = "remind_open_swap_requests"
    max_execution_time = timedelta(
        minutes=5
    )  # Matches K8s CronJob activeDeadlineSeconds=300

    def execute_job(self, *args, **options):
        dry_run = options.get("dry_run", False)
        today = timezone.now().date()

        summary = send_periodic_open_swap_reminder_notifications(
            today=today,
            dry_run=dry_run,
        )

        if summary["candidate_count"] == 0:
            self.log_info("No open swap requests matched reminder offsets today")
            return

        prefix = "[DRY RUN] " if dry_run else ""
        self.log_info(
            f"{prefix}Reminder candidates={summary['candidate_count']}, "
            f"requests_processed={summary['request_count']}, "
            f"emails_sent={summary['email_count']}, "
            f"skipped_no_recipients={summary['skipped_no_recipients']}"
        )
