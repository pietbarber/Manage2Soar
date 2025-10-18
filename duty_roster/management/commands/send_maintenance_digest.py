from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from logsheet.models import AircraftMeister, MaintenanceIssue


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

        lines = [f"🔧 Maintenance Summary for {today.strftime('%A, %B %d, %Y')}", ""]
        recipients = set()

        for issue in open_issues:
            aircraft = issue.glider or issue.towplane or "Unassigned"
            grounded_status = "GROUNDED" if issue.grounded else "Operational"
            lines.append(
                f"- {aircraft}: {issue.description} (Reported: "
                f"{issue.report_date.strftime('%Y-%m-%d')}) [{grounded_status}]"
            )

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

        lines.append("\nTotal Open Issues: " + str(open_issues.count()))
        lines.append(
            "\nMaintenance Dashboard: {}/maintenance/".format(settings.SITE_URL)
        )

        body = "\n".join(lines)

        if recipients:
            send_mail(
                subject=f"[Skyline Soaring] Maintenance Summary - {today.strftime('%B %d')}",
                message=body,
                from_email="noreply@default.manage2soar.com",
                recipient_list=list(recipients),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    (
                        "✅ Sent maintenance summary to: "
                        f"{', '.join(recipients)}"
                    )
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING("⚠️ No aircraft meisters with email found.")
            )
