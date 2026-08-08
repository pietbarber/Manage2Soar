"""Management command to notify duty officers about aging (unfinalized) logsheets."""

from datetime import timedelta

from django.template.loader import render_to_string
from django.utils.timezone import now

from duty_roster.utils.email import get_email_config
from logsheet.models import Logsheet
from notifications.models import Notification
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand
from utils.url_helpers import build_absolute_url

# Canonical fragment used to identify aging-logsheet notifications for deduplication
_AGING_MSG_FRAGMENT = "aging logsheet"


class Command(BaseCronJobCommand):
    """Notify duty officers about logsheets that are 7+ days old and not finalized."""

    help = "Notify duty officers about logsheets that are 7+ days old and not finalized"
    job_name = "notify_aging_logsheets"
    max_execution_time = timedelta(minutes=15)  # Should be quick operation

    def add_arguments(self, parser):
        """Add command-line arguments to the argument parser."""
        super().add_arguments(parser)
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days after which logsheets are considered aging (default: 7)",
        )

    def execute_job(self, *args, **options):
        """Execute the aging logsheet notification command."""
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

    def _upsert_aging_notification(self, member, count):
        """Maintain exactly one undismissed aging-logsheet notification per member.

        If no such notification exists, creates one.  If one or more exist,
        keeps only the latest (by ``created_at``), updates its message with the
        current count, and deletes any extras.

        Args:
            member: The Member instance to notify.
            count: Number of aging logsheets to display in the message.

        Returns:
            The canonical (kept or created) Notification instance.
        """
        candidates = Notification.objects.filter(
            user=member,
            dismissed=False,
            message__icontains=_AGING_MSG_FRAGMENT,
            url="/logsheet/",
        ).order_by("-created_at")

        if not candidates.exists():
            return Notification.objects.create(
                user=member,
                message=f"You have {count} aging logsheet(s) that need finalization",
                url="/logsheet/",
            )

        canonical = candidates.first()
        if canonical is None:
            return Notification.objects.create(
                user=member,
                message=f"You have {count} aging logsheet(s) that need finalization",
                url="/logsheet/",
            )
        extras_to_remove = candidates.exclude(pk=canonical.pk)
        if extras_to_remove.exists():
            extras_to_remove.delete()

        new_message = f"You have {count} aging logsheet(s) that need finalization"
        if canonical.message != new_message:
            canonical.message = new_message
            canonical.save(update_fields=["message"])
        return canonical

    def _send_notification(self, member, logsheet_data):
        """Send email and in-app notification to a duty officer about aging logsheets."""

        # Build email content
        logsheet_list = []
        for logsheet, days_old in logsheet_data:
            date_str = logsheet.log_date.strftime("%A, %B %d, %Y")
            logsheet_list.append(
                f"- {date_str} at {logsheet.airfield} ({days_old} days old)"
            )

        subject = (
            f"Aging Logsheet Reminder - {len(logsheet_data)} Unfinalized Logsheet(s)"
        )

        # Prepare context for email templates
        email_config = get_email_config()
        config = email_config["config"]

        context = {
            "member": member,
            "logsheet_list": logsheet_list,
            "logsheet_url": build_absolute_url("/logsheet/"),
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "site_url": email_config["site_url"],
        }

        # Render HTML and plain text templates
        html_message = render_to_string(
            "duty_roster/emails/aging_logsheets.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/aging_logsheets.txt", context
        )

        email_sent = False
        in_app_sent = False

        try:
            # Send email notification
            send_mail(
                subject=subject,
                message=text_message,
                from_email=email_config["from_email"],
                recipient_list=[member.email],
                html_message=html_message,
                fail_silently=False,
            )
            email_sent = True
        except Exception as e:
            self.log_error(
                f"Failed to send aging logsheet email to {member.full_display_name}: {str(e)}"
            )

        try:
            # Upsert a single canonical in-app notification per user.
            # Each cron run maintains exactly one undismissed aging-logsheet
            # notification per member, updating the count instead of stacking.
            self._upsert_aging_notification(member, len(logsheet_data))
            in_app_sent = True
        except Exception as e:
            self.log_error(
                f"Failed to create aging logsheet in-app notification for {member.full_display_name}: {str(e)}"
            )

        if email_sent or in_app_sent:
            self.log_success(
                f"Notified {member.full_display_name} about {len(logsheet_data)} aging logsheet(s)"
            )
