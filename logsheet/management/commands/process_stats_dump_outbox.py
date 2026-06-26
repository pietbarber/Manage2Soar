from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from logsheet.models import StatsDumpOutbox
from logsheet.utils.stats_dump import process_stats_dump_outbox_job
from utils.management.commands.base_cronjob import BaseCronJobCommand

MAX_ATTEMPTS = 5  # Maximum retries before a job is permanently abandoned.


class Command(BaseCronJobCommand):
    help = "Process pending/failed stats dump export outbox jobs"
    job_name = "process_stats_dump_outbox"
    max_execution_time = timedelta(minutes=20)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Max outbox records to process per run (default: 20)",
        )

    def execute_job(self, *args, **options):
        limit = options.get("limit", 20)
        stale_cutoff = timezone.now() - self.max_execution_time

        recovered_count = (
            StatsDumpOutbox.objects.filter(
                status=StatsDumpOutbox.STATUS_PROCESSING,
            )
            .filter(Q(started_at__isnull=True) | Q(started_at__lt=stale_cutoff))
            .update(
                status=StatsDumpOutbox.STATUS_FAILED,
                last_error=(
                    "Marked failed for retry after stale processing timeout in "
                    "process_stats_dump_outbox."
                ),
                completed_at=timezone.now(),
            )
        )
        if recovered_count:
            self.log_info(
                f"Recovered {recovered_count} stale processing outbox job(s)."
            )

        outbox_ids = list(
            StatsDumpOutbox.objects.filter(
                status__in=[
                    StatsDumpOutbox.STATUS_PENDING,
                    StatsDumpOutbox.STATUS_FAILED,
                ],
                attempt_count__lt=MAX_ATTEMPTS,
            )
            .order_by("queued_at")
            .values_list("id", flat=True)[:limit]
        )

        if not outbox_ids:
            self.log_info("No pending stats dump outbox jobs.")
            return

        self.log_info(f"Processing {len(outbox_ids)} stats dump outbox job(s).")

        for outbox_id in outbox_ids:
            process_stats_dump_outbox_job(outbox_id)

        self.log_success("Finished processing stats dump outbox jobs.")
