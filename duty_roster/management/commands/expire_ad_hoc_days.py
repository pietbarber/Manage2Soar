from datetime import timedelta

from django.template.loader import render_to_string

from duty_roster.models import DutyAssignment
from duty_roster.utils.email import get_email_config, get_mailing_list
from siteconfig.timezone_utils import get_club_now
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Cancel unconfirmed ad-hoc ops days at the club-local 11 PM deadline"
    job_name = "expire_ad_hoc_days"
    max_execution_time = timedelta(
        minutes=5
    )  # Matches K8s CronJob activeDeadlineSeconds=300

    def execute_job(self, *args, **options):
        # The CronJob runs every 15 minutes because the club timezone is
        # configurable, including fractional-hour offsets. Only the first
        # local quarter-hour of 23:00 is the night-before deadline; using a
        # fixed UTC run would be too early for UTC/east-of-UTC clubs or too
        # late for west-of-UTC clubs.
        club_now = get_club_now()
        if club_now.hour != 23 or club_now.minute >= 15:
            self.log_info(
                f"No expiration required at {club_now:%H:%M} club-local time; "
                "deadline is 23:00"
            )
            return

        # At the local 23:00 deadline, the ops day is tomorrow.
        tomorrow = club_now.date() + timedelta(days=1)

        assignments = DutyAssignment.objects.filter(
            is_scheduled=False, is_confirmed=False, date=tomorrow
        )

        if not assignments.exists():
            self.log_info("No unconfirmed ad-hoc ops days found for tomorrow")
            return

        cancelled_count = 0

        # Get configuration using helper functions
        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "MEMBERS_MAILING_LIST", "members", email_config["config"]
        )

        for assignment in assignments:
            ops_date = assignment.date.strftime("%A, %B %d, %Y")

            if options.get("dry_run"):
                self.log_info(
                    f"[DRY RUN] Would cancel unconfirmed ad-hoc ops day for {assignment.date} "
                    "(club-local 23:00 night-before deadline)"
                )
                cancelled_count += 1
            else:
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
                    f"Cancelled unconfirmed ad-hoc ops day for {assignment.date} "
                    "(club-local 23:00 night-before deadline passed)"
                )
                cancelled_count += 1

        if options.get("dry_run"):
            if cancelled_count > 0:
                self.log_info(
                    f"[DRY RUN] Would cancel {cancelled_count} unconfirmed ad-hoc ops day(s)"
                )
            else:
                self.log_info("[DRY RUN] No ad-hoc ops days would require cancellation")
        elif cancelled_count > 0:
            self.log_success(
                f"Cancelled {cancelled_count} unconfirmed ad-hoc ops day(s)"
            )
        else:
            self.log_info("No ad-hoc ops days required cancellation")
