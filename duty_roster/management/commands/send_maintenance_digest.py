from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils.timezone import now

from duty_roster.utils.email import get_email_config
from logsheet.models import AircraftMeister, MaintenanceIssue
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url


class Command(BaseCommand):
    help = "Send weekly maintenance summary to aircraft meisters"

    def handle(self, *args, **options):
        today = now().date()
        open_issues = MaintenanceIssue.objects.filter(resolved=False).order_by(
            "report_date"
        )

        if not open_issues.exists():
            self.stdout.write("✅ No unresolved maintenance issues. Skipping email.")
            return

        recipients = set()

        # Collect recipients and prepare issues data for templates
        grounded_issues = []
        operational_issues = []

        for issue in open_issues:
            aircraft = issue.glider or issue.towplane or "Unassigned"

            issue_data = {
                "aircraft": str(aircraft),
                "description": issue.description,
                "report_date": issue.report_date,
                "grounded": issue.grounded,
            }

            if issue.grounded:
                grounded_issues.append(issue_data)
            else:
                operational_issues.append(issue_data)

            # Get assigned meisters
            if issue.glider:
                meisters = AircraftMeister.objects.filter(glider=issue.glider)
            elif issue.towplane:
                meisters = AircraftMeister.objects.filter(towplane=issue.towplane)
            else:
                meisters = []

            for meister in meisters:
                if meister.member and meister.member.email:
                    recipients.add(meister.member.email)

        if not recipients:
            self.stdout.write(
                self.style.WARNING("⚠️ No aircraft meisters with email found.")
            )
            return

        # Prepare template context using helper function
        email_config = get_email_config()
        site_url = email_config["site_url"]
        maintenance_url = f"{site_url}/maintenance/" if site_url else "/maintenance/"

        context = {
            "report_date": today.strftime("%A, %B %d, %Y"),
            "issues": grounded_issues + operational_issues,
            "issue_count": open_issues.count(),
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
            "maintenance_dashboard_url": maintenance_url,
        }

        # Render email templates
        html_message = render_to_string(
            "duty_roster/emails/maintenance_digest.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/maintenance_digest.txt", context
        )

        subject = f"[{email_config['club_name']}] Maintenance Summary - {today.strftime('%B %d')}"

        send_mail(
            subject=subject,
            message=text_message,
            from_email=email_config["from_email"],
            recipient_list=list(recipients),
            html_message=html_message,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Sent maintenance summary to: {', '.join(recipients)}"
            )
        )
