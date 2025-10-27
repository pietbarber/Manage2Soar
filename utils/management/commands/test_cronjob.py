from datetime import timedelta
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Test command to verify CronJob framework functionality"
    job_name = "test_cronjob"
    max_execution_time = timedelta(minutes=5)

    def execute_job(self, *args, **options):
        self.log_info("CronJob framework test starting...")

        # Test basic functionality
        self.log_success("Framework is working correctly!")
        self.log_warning("This is a warning message")
        self.log_info("Test completed successfully")

        return "Test completed"
