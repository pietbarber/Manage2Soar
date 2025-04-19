from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django.core.mail import send_mail
from logsheet.models import Logsheet, MaintenanceIssue, MaintenanceDeadline, AircraftMeister
from datetime import timedelta
from members.models import Member
from django.conf import settings

class Command(BaseCommand):
    help = "Send pre-op duty email showing grounded aircraft and upcoming maintenance"

    def handle(self, *args, **options):
        tomorrow = now().date() + timedelta(days=1)

        self.stdout.write(self.style.NOTICE(f"Generating pre-op report for {tomorrow}"))

        logsheets = Logsheet.objects.filter(log_date=tomorrow)
        if not logsheets.exists():
            self.stdout.write("❌ No operations scheduled for tomorrow.")
            return

        grounded_gliders = MaintenanceIssue.objects.filter(glider__isnull=False, grounded=True, resolved=False)
        grounded_towplanes = MaintenanceIssue.objects.filter(towplane__isnull=False, grounded=True, resolved=False)

        upcoming_deadlines = MaintenanceDeadline.objects.filter(due_date__lte=tomorrow + timedelta(days=30))

        lines = [f"🚨 Pre-Operations Summary for {tomorrow}", ""]

        lines.append("🛑 Grounded Gliders:")
        if grounded_gliders:
            for issue in grounded_gliders:
                lines.append(f"- {issue.glider} :: {issue.description}")
        else:
            lines.append("- None")

        lines.append("\n🛑 Grounded Towplanes:")
        if grounded_towplanes:
            for issue in grounded_towplanes:
                lines.append(f"- {issue.towplane} :: {issue.description}")
        else:
            lines.append("- None")

        lines.append("\n🗓️ Maintenance Deadlines in Next 30 Days:")
        if upcoming_deadlines:
            for d in upcoming_deadlines:
                aircraft = d.glider or d.towplane
                lines.append(f"- {aircraft} :: {d.item} due {d.due_date}")
        else:
            lines.append("- None")

        body = "\n".join(lines)

        self.stdout.write("\n=================== EMAIL ===================")
        self.stdout.write(body)
        self.stdout.write("============================================\n")

        # Optional: send as real email if desired later
        # send_mail("Skyline Pre-Op Report", body, settings.DEFAULT_FROM_EMAIL, ["someone@example.com"])

        self.stdout.write(self.style.SUCCESS("Pre-op report generated and sent to console."))
