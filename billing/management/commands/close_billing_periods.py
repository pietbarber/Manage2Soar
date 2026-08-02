from datetime import timedelta

from billing.periods import close_due_periods
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Close due billing periods under the configured automatic policy."
    job_name = "close_billing_periods"
    max_execution_time = timedelta(minutes=5)

    def execute_job(self, *args, **options):
        periods = close_due_periods(dry_run=options.get("dry_run", False))
        if options.get("dry_run"):
            self.log_info(f"Would close {len(periods)} billing period(s)")
            return
        self.log_success(f"Closed {len(periods)} billing period(s)")
