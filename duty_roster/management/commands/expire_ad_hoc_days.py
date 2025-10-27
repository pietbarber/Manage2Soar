from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils.timezone import now

from duty_roster.models import DutyAssignment
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Cancel unconfirmed ad-hoc ops days that are scheduled for tomorrow"
    job_name = "expire_ad_hoc_days"
    max_execution_time = timedelta(minutes=10)  # This is a quick operation

    def execute_job(self, *args, **options):
        tomorrow = now().date() + timedelta(days=1)

        assignments = DutyAssignment.objects.filter(
            is_scheduled=False, is_confirmed=False, date=tomorrow
        )

        if not assignments.exists():
            self.log_info("No unconfirmed ad-hoc ops days found for tomorrow")
            return

        cancelled_count = 0

        for assignment in assignments:
            ops_date = assignment.date.strftime("%A, %B %d, %Y")

            if not options.get('dry_run'):
                send_mail(
                    subject=f"Ad-Hoc Ops Cancelled - {ops_date}",
                    message=f"""Ad-hoc ops on {ops_date} could not get sufficient interest to meet the minimum 
duty crew of tow pilot and duty officer. The deadline has passed and the ops 
have been cancelled for tomorrow.\n\nCalendar: {settings.SITE_URL}/duty_roster/calendar/""",
                    from_email="noreply@default.manage2soar.com",
                    recipient_list=["members@default.manage2soar.com"],
                )
                assignment.delete()

            self.log_warning(
                f"Cancelled unconfirmed ad-hoc ops day for {assignment.date}")
            cancelled_count += 1

        if cancelled_count > 0:
            self.log_success(
                f"Cancelled {cancelled_count} unconfirmed ad-hoc ops day(s)")
        else:
            self.log_info("No ad-hoc ops days required cancellation")
