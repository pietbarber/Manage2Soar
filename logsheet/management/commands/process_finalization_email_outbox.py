from datetime import timedelta

from logsheet.models import FinalizationEmailOutbox
from logsheet.utils.finalization_email import _process_finalization_email_outbox_job
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Process pending/failed finalization summary email outbox jobs"
    job_name = "process_finalization_email_outbox"
    max_execution_time = timedelta(minutes=10)

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Max outbox records to process per run (default: 100)",
        )

    def execute_job(self, *args, **options):
        limit = options.get("limit", 100)

        outbox_ids = list(
            FinalizationEmailOutbox.objects.filter(
                status__in=[
                    FinalizationEmailOutbox.STATUS_PENDING,
                    FinalizationEmailOutbox.STATUS_FAILED,
                ]
            )
            .order_by("queued_at")
            .values_list("id", flat=True)[:limit]
        )

        if not outbox_ids:
            self.log_info("No pending finalization email outbox jobs.")
            return

        self.log_info(f"Processing {len(outbox_ids)} finalization email outbox job(s).")

        for outbox_id in outbox_ids:
            _process_finalization_email_outbox_job(outbox_id)

        self.log_success("Finished processing finalization email outbox jobs.")
