from datetime import timedelta

from django.template.loader import render_to_string

from duty_roster.models import DutyAssignment
from duty_roster.utils.email import get_email_config, get_mailing_list
from siteconfig.timezone_utils import get_club_today
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Cancel unconfirmed ad-hoc ops days whose deadline has passed (runs at 3 AM UTC = 10 PM EST / 11 PM EDT)"
    job_name = "expire_ad_hoc_days"
    max_execution_time = timedelta(
        minutes=5
    )  # Matches K8s CronJob activeDeadlineSeconds=300

    def execute_job(self, *args, **options):
        # Run at 3 AM UTC (10 PM EST / 11 PM EDT), which is the "night before"
        # the upcoming ops day in club-local time.  At that moment
        # get_club_today() is the CURRENT local evening and the ops day is the
        # NEXT local day (TOMORROW), so we expire ad-hoc days scheduled for
        # tomorrow — the night-before deadline has passed and there is no
        # longer time to assemble minimum crew before flying begins in the
        # morning (issue #1056).
        #
        # Historically this ran at 6 PM UTC (1-2 PM EST) and checked
        # `tomorrow`, cancelling days mid-afternoon before members could
        # respond (issue #654).  Moving the schedule to 3 AM UTC made
        # "today" the night-before date, which shifted the cancellation to
        # the evening AFTER the ops day flew instead of the evening before —
        # an off-by-one regression introduced when club-local timezone
        # support was added (issue #1056).
        tomorrow = get_club_today() + timedelta(days=1)

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
                    "(night-before deadline, 03:00 UTC)"
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
                    "(night-before deadline passed, 03:00 UTC)"
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
