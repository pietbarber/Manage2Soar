"""
Send pre-operation duty email with HTML formatting.

This management command sends a nicely formatted HTML email to the duty crew
with information about:
- Assigned crew members
- Students requesting instruction
- Members planning to fly (ops intent)
- Grounded aircraft
- Upcoming maintenance deadlines

Students requesting instruction and members with ops intent are automatically
CC'd on the email to keep them informed.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils.timezone import now

from duty_roster.models import DutyAssignment, InstructionSlot, OpsIntent
from logsheet.models import MaintenanceDeadline, MaintenanceIssue
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import send_mail


class Command(BaseCommand):
    help = "Send pre-op duty email showing grounded aircraft, students, and upcoming maintenance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=str, help="Target date for pre-op report (YYYY-MM-DD)"
        )

    def handle(self, *args, **options):
        # Show dev mode status
        if settings.EMAIL_DEV_MODE:
            redirect_to = settings.EMAIL_DEV_MODE_REDIRECT_TO
            if redirect_to:
                self.stdout.write(
                    self.style.WARNING(
                        f"EMAIL DEV MODE ENABLED - All emails will be redirected to: {redirect_to}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "EMAIL DEV MODE ENABLED but EMAIL_DEV_MODE_REDIRECT_TO is not set! "
                        "Emails will fail to send."
                    )
                )

        # Determine target date
        if options["date"]:
            try:
                target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("Invalid date format. Use YYYY-MM-DD.")
                )
                return
        else:
            target_date = now().date() + timedelta(days=1)

        self.stdout.write(
            self.style.NOTICE(f"Generating pre-op report for {target_date}")
        )

        # Get the duty assignment
        try:
            assignment = DutyAssignment.objects.get(date=target_date, is_scheduled=True)
        except DutyAssignment.DoesNotExist:
            self.stdout.write("No scheduled ops for this date.")
            return

        # Collect duty crew emails
        crew_fields = [
            assignment.instructor,
            assignment.surge_instructor,
            assignment.tow_pilot,
            assignment.surge_tow_pilot,
            assignment.duty_officer,
            assignment.assistant_duty_officer,
        ]
        to_emails = [m.email for m in crew_fields if m and m.email]

        if not to_emails:
            self.stdout.write(
                self.style.WARNING(
                    "No valid email addresses for duty crew. Email not sent."
                )
            )
            return

        # Get site configuration
        config = SiteConfiguration.objects.first()
        site_url = getattr(settings, "SITE_URL", "https://localhost:8000")

        # Build context for templates
        context = self._build_context(assignment, target_date, config, site_url)

        # Collect CC emails from students and ops intent members
        cc_emails = []
        for slot in context.get("instruction_requests", []):
            if slot.student and slot.student.email:
                cc_emails.append(slot.student.email)
        for intent in context.get("ops_intents", []):
            if intent.member and intent.member.email:
                cc_emails.append(intent.member.email)
        # Remove duplicates and any emails already in to_emails
        cc_emails = list(set(cc_emails) - set(to_emails))

        # Render templates
        html_message = render_to_string("duty_roster/emails/preop_email.html", context)
        text_message = render_to_string("duty_roster/emails/preop_email.txt", context)

        # Send email - use noreply@ with domain extracted from DEFAULT_FROM_EMAIL
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
        if "@" in default_from:
            # Extract domain from email like "members@skylinesoaring.org"
            domain = default_from.split("@")[-1]
            from_email = f"noreply@{domain}"
        elif config and config.domain_name:
            from_email = f"noreply@{config.domain_name}"
        else:
            from_email = "noreply@manage2soar.com"

        try:
            send_mail(
                subject=f"Pre-Ops Report for {target_date}",
                message=text_message,
                from_email=from_email,
                recipient_list=to_emails,
                cc=cc_emails if cc_emails else None,
                html_message=html_message,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Email sent to: {', '.join(to_emails)}")
            )
            if cc_emails:
                self.stdout.write(self.style.SUCCESS(f"CC'd: {', '.join(cc_emails)}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send email: {e}"))
            raise

    def _build_context(self, assignment, target_date, config, site_url):
        """Build the template context with all required data."""

        # Get grounded aircraft
        grounded_gliders = MaintenanceIssue.objects.filter(
            glider__isnull=False, grounded=True, resolved=False
        ).select_related("glider")

        grounded_towplanes = MaintenanceIssue.objects.filter(
            towplane__isnull=False, grounded=True, resolved=False
        ).select_related("towplane")

        # Get upcoming maintenance deadlines (next 30 days from target date)
        upcoming_deadlines = (
            MaintenanceDeadline.objects.filter(
                due_date__gte=target_date,
                due_date__lte=target_date + timedelta(days=30),
            )
            .select_related("glider", "towplane")
            .order_by("due_date")
        )

        # Get students requesting instruction for this day
        instruction_requests = InstructionSlot.objects.filter(
            assignment=assignment,
            status__in=["pending", "confirmed", "waitlist"],
        ).select_related("student")

        # Get members who indicated they want to fly (ops intent)
        ops_intents = OpsIntent.objects.filter(date=target_date).select_related(
            "member", "glider"
        )

        # Calculate days until target date for dynamic wording
        today = now().date()
        days_until = (target_date - today).days

        # Get role titles from site config
        context = {
            # Date and site info
            "target_date": target_date,
            "days_until": days_until,
            "club_name": config.club_name if config else "Soaring Club",
            "club_nickname": config.club_nickname if config else "",
            "club_logo_url": self._get_logo_url(config, site_url),
            "site_url": site_url,
            "duty_roster_url": f"{site_url}/duty_roster/calendar/",
            # Duty crew
            "instructor": assignment.instructor,
            "surge_instructor": assignment.surge_instructor,
            "tow_pilot": assignment.tow_pilot,
            "surge_tow_pilot": assignment.surge_tow_pilot,
            "duty_officer": assignment.duty_officer,
            "assistant_duty_officer": assignment.assistant_duty_officer,
            # Role titles
            "instructor_title": get_role_title("instructor"),
            "surge_instructor_title": get_role_title("surge_instructor"),
            "towpilot_title": get_role_title("towpilot"),
            "surge_towpilot_title": get_role_title("surge_towpilot"),
            "duty_officer_title": get_role_title("duty_officer"),
            "assistant_duty_officer_title": get_role_title("assistant_duty_officer"),
            # Students and members
            "instruction_requests": instruction_requests,
            "ops_intents": ops_intents,
            # Maintenance
            "grounded_gliders": grounded_gliders,
            "grounded_towplanes": grounded_towplanes,
            "upcoming_deadlines": upcoming_deadlines,
        }

        return context

    def _get_logo_url(self, config, site_url):
        """Get the club logo URL, or None if not configured."""
        if config and config.club_logo:
            logo_url = config.club_logo.url
            # If it's already an absolute URL (e.g., from cloud storage), use as-is
            if logo_url.startswith(("http://", "https://")):
                return logo_url
            # Otherwise, prepend site_url for relative paths
            return f"{site_url.rstrip('/')}{logo_url}"
        return None
