from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.timezone import now

from instructors.utils import get_overdue_sprs, get_spr_escalation_level
from notifications.models import Notification
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand
from utils.url_helpers import build_absolute_url, get_canonical_url


class Command(BaseCronJobCommand):
    help = "Notify instructors about overdue SPRs (Student Progress Reports) at 7/14/21/25/30 day intervals"
    job_name = "notify_late_sprs"
    max_execution_time = timedelta(minutes=20)  # May need to process many flights

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--max-days",
            type=int,
            default=30,
            help="Maximum days to look back for flights needing SPRs (default: 30)",
        )

    def execute_job(self, *args, **options):
        max_days = options.get("max_days", 30)
        as_of_date = now().date()
        cutoff_date = as_of_date - timedelta(days=max_days)

        self.log_info(f"Checking for overdue SPRs from flights since {cutoff_date}")
        overdue_sprs = get_overdue_sprs(max_days=max_days, as_of_date=as_of_date)

        if not overdue_sprs:
            self.log_info("No overdue SPRs found")
            return

        # Send notifications
        total_instructors = len(overdue_sprs)
        total_overdue_sprs = sum(len(sprs) for sprs in overdue_sprs.values())

        self.log_info(
            f"Found {total_overdue_sprs} overdue SPRs for {total_instructors} instructor(s)"
        )

        notifications_sent = 0
        for instructor, spr_data in overdue_sprs.items():
            if not options.get("dry_run"):
                self._send_notification(instructor, spr_data)
                notifications_sent += 1
            else:
                escalation_counts = {}
                for spr in spr_data:
                    level = spr["escalation_level"]
                    escalation_counts[level] = escalation_counts.get(level, 0) + 1

                escalation_summary = ", ".join(
                    [f"{count} {level}" for level, count in escalation_counts.items()]
                )
                self.log_info(
                    f"Would notify {instructor.full_display_name} about {len(spr_data)} overdue SPRs ({escalation_summary})"
                )

        if notifications_sent > 0:
            self.log_success(
                f"Sent overdue SPR notifications to {notifications_sent} instructor(s)"
            )
        else:
            self.log_info("No notifications sent (dry run mode)")

    def _get_escalation_level(self, days_overdue):
        """Determine escalation level based on days overdue"""
        return get_spr_escalation_level(days_overdue)

    def _send_notification(self, instructor, spr_data):
        """Send email and in-app notification to instructor about overdue SPRs"""

        # Group SPRs by escalation level for better presentation
        escalation_groups = {}
        for spr in spr_data:
            level = spr["escalation_level"]
            if level not in escalation_groups:
                escalation_groups[level] = []
            escalation_groups[level].append(spr)

        # Determine overall urgency for subject line
        escalation_order = ["FINAL", "URGENT", "WARNING", "REMINDER", "NOTICE"]
        highest_urgency = "NOTICE"  # Default
        for level in escalation_order:
            if level in escalation_groups:
                highest_urgency = level
                break

        # Build subject with urgency prefix
        subject = (
            f"Student Progress Report Reminder - {len(spr_data)} Overdue Report(s)"
        )

        if highest_urgency == "FINAL":
            subject = f"FINAL NOTICE: {subject}"
        elif highest_urgency == "URGENT":
            subject = f"URGENT: {subject}"

        # Prepare template context
        config = SiteConfiguration.objects.first()
        canonical_base = get_canonical_url()
        instruction_reports_url = build_absolute_url(
            "/instructors/", canonical=canonical_base
        )

        # Format SPR data for templates
        formatted_escalation_groups = {}
        for level, sprs in escalation_groups.items():
            formatted_escalation_groups[level] = [
                {
                    "student_name": spr["student"].full_display_name,
                    "flight_date": spr["flight_date"].strftime("%A, %B %d, %Y"),
                    "days_overdue": spr["days_overdue"],
                }
                for spr in sprs
            ]

        context = {
            "instructor_name": instructor.full_display_name,
            "escalation_groups": formatted_escalation_groups,
            "highest_urgency": highest_urgency,
            "club_name": config.club_name if config else "Soaring Club",
            "club_logo_url": get_absolute_club_logo_url(config),
            "instruction_reports_url": instruction_reports_url,
        }

        # Render email templates
        html_message = render_to_string(
            "instructors/emails/late_sprs_notification.html", context
        )
        text_message = render_to_string(
            "instructors/emails/late_sprs_notification.txt", context
        )

        # Build from email
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
        if "@" in default_from:
            domain = default_from.split("@")[-1]
            from_email = f"noreply@{domain}"
        elif config and config.domain_name:
            from_email = f"noreply@{config.domain_name}"
        else:
            from_email = "noreply@manage2soar.com"

        try:
            # Send email notification
            send_mail(
                subject=subject,
                message=text_message,
                from_email=from_email,
                recipient_list=[instructor.email] if instructor.email else [],
                html_message=html_message,
                fail_silently=False,
            )

            # Create in-app notification with appropriate urgency
            urgency_emoji = {
                "FINAL": "🚨",
                "URGENT": "⚠️",
                "WARNING": "⚠️",
                "REMINDER": "📝",
                "NOTICE": "📌",
            }

            emoji = urgency_emoji.get(highest_urgency, "📝")

            Notification.objects.create(
                user=instructor,
                message=f"{emoji} You have {len(spr_data)} overdue Student Progress Report(s)",
                url="/instructors/",
            )

            self.log_success(
                f"Notified {instructor.full_display_name} about {len(spr_data)} overdue SPR(s)"
            )

        except Exception as e:
            self.log_error(f"Failed to notify {instructor.full_display_name}: {str(e)}")
