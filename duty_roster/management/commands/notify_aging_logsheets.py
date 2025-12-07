from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.timezone import now

from logsheet.models import Logsheet
from notifications.models import Notification
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Notify duty officers about logsheets that are 7+ days old and not finalized"
    job_name = "notify_aging_logsheets"
    max_execution_time = timedelta(minutes=15)  # Should be quick operation

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days after which logsheets are considered aging (default: 7)",
        )

    def execute_job(self, *args, **options):
        aging_days = options.get("days", 7)
        cutoff_date = now() - timedelta(days=aging_days)

        self.log_info(
            f"Checking for logsheets older than {aging_days} days (before {cutoff_date.date()})"
        )

        # Find unfinalized logsheets older than the cutoff
        aging_logsheets = (
            Logsheet.objects.filter(finalized=False, log_date__lt=cutoff_date.date())
            .select_related(
                "duty_officer", "assistant_duty_officer", "created_by", "airfield"
            )
            .order_by("created_at")
        )

        if not aging_logsheets.exists():
            self.log_info("No aging logsheets found")
            return

        self.log_info(f"Found {aging_logsheets.count()} aging logsheet(s)")

        # Group logsheets by duty officer for efficient notification
        duty_officer_logsheets = {}

        for logsheet in aging_logsheets:
            days_old = (now() - logsheet.created_at).days

            # Determine who to notify (duty officer first, then assistant, then creator)
            notify_members = []
            if logsheet.duty_officer:
                notify_members.append(logsheet.duty_officer)
            if logsheet.assistant_duty_officer:
                notify_members.append(logsheet.assistant_duty_officer)
            if not notify_members and logsheet.created_by:
                notify_members.append(logsheet.created_by)

            # Group by notifiable members
            for member in notify_members:
                if member.email:  # Only notify members with email addresses
                    if member not in duty_officer_logsheets:
                        duty_officer_logsheets[member] = []
                    duty_officer_logsheets[member].append((logsheet, days_old))

        if not duty_officer_logsheets:
            self.log_warning(
                "No duty officers with email addresses found for aging logsheets"
            )
            return

        # Send notifications to each duty officer
        notifications_sent = 0
        for member, logsheet_data in duty_officer_logsheets.items():
            if not options.get("dry_run"):
                self._send_notification(member, logsheet_data)
                notifications_sent += 1
            else:
                self.log_info(
                    f"Would notify {member.full_display_name} about {len(logsheet_data)} aging logsheet(s)"
                )

        if notifications_sent > 0:
            self.log_success(
                f"Sent aging logsheet notifications to {notifications_sent} duty officer(s)"
            )
        else:
            self.log_info("No notifications sent (dry run mode)")

    def _send_notification(self, member, logsheet_data):
        """Send email and in-app notification to a duty officer about aging logsheets"""

        # Build email content
        logsheet_list = []
        for logsheet, days_old in logsheet_data:
            date_str = logsheet.created_at.strftime("%A, %B %d, %Y")
            logsheet_list.append(
                f"- {date_str} at {logsheet.airfield} ({days_old} days old)"
            )

        subject = (
            f"Aging Logsheet Reminder - {len(logsheet_data)} Unfinalized Logsheet(s)"
        )

        message = f"""Hello {member.full_display_name},

The following logsheet(s) are overdue for finalization:

{chr(10).join(logsheet_list)}

Please log into Manage2Soar to finalize these logsheets as soon as possible. Unfinalized logsheets prevent accurate reporting and billing.

Logsheet Management: {settings.SITE_URL}/logsheet/

Thank you for your attention to this matter.

- Manage2Soar Automated Notifications"""

        # Prepare context for email templates
        config = SiteConfiguration.objects.first()

        context = {
            "member": member,
            "logsheet_list": logsheet_list,
            "logsheet_url": f"{getattr(settings, 'SITE_URL', 'https://localhost:8000')}/logsheet/",
            "club_name": config.club_name if config else "Club",
            "club_logo_url": get_absolute_club_logo_url(config),
            "site_url": getattr(settings, "SITE_URL", None),
        }

        # Render HTML and plain text templates
        html_message = render_to_string(
            "duty_roster/emails/aging_logsheets.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/aging_logsheets.txt", context
        )

        try:
            # Send email notification
            send_mail(
                subject=subject,
                message=text_message,
                from_email="noreply@default.manage2soar.com",
                recipient_list=[member.email],
                html_message=html_message,
                fail_silently=False,
            )

            # Create in-app notification
            Notification.objects.create(
                user=member,
                message=f"You have {len(logsheet_data)} aging logsheet(s) that need finalization",
                url="/logsheet/",
            )

            self.log_success(
                f"Notified {member.full_display_name} about {len(logsheet_data)} aging logsheet(s)"
            )

        except Exception as e:
            self.log_error(f"Failed to notify {member.full_display_name}: {str(e)}")
