from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.timezone import now

from duty_roster.models import DutyAssignment
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
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

        # Get configuration using helper functions
        from duty_roster.utils.email import get_email_config, get_mailing_list

        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "MEMBERS_MAILING_LIST", "members", email_config["config"]
        )

        for assignment in assignments:
            ops_date = assignment.date.strftime("%A, %B %d, %Y")

            if not options.get("dry_run"):
                # Prepare template context
                context = {
                    "ops_date": ops_date,
                    "club_name": email_config["club_name"],
                    "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
                    "roster_url": email_config["roster_url"],
                }

                # Render email templates
                html_message = render_to_string(
                    "duty_roster/emails/ad_hoc_expiration.html", context
                )
                text_message = render_to_string(
                    "duty_roster/emails/ad_hoc_expiration.txt", context
                )

                send_mail(
                    subject=f"[{email_config['club_name']}] Ad-Hoc Ops Expired - {ops_date}",
                    message=text_message,
                    from_email=email_config["from_email"],
                    recipient_list=recipient_list,
                    html_message=html_message,
                )
                assignment.delete()

            self.log_warning(
                f"Cancelled unconfirmed ad-hoc ops day for {assignment.date}"
            )
            cancelled_count += 1

        if cancelled_count > 0:
            self.log_success(
                f"Cancelled {cancelled_count} unconfirmed ad-hoc ops day(s)"
            )
        else:
            self.log_info("No ad-hoc ops days required cancellation")
