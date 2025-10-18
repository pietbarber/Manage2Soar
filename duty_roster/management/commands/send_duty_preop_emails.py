from datetime import datetime, timedelta

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from duty_roster.models import DutyAssignment
from logsheet.models import MaintenanceDeadline, MaintenanceIssue


class Command(BaseCommand):
    help = "Send pre-op duty email showing grounded aircraft and upcoming maintenance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date", type=str, help="Target date for pre-op report (YYYY-MM-DD)"
        )

    def handle(self, *args, **options):
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

        notice_msg = f"Generating pre-op report for {target_date}"
        self.stdout.write(self.style.NOTICE(notice_msg))

        try:
            assignment = DutyAssignment.objects.get(date=target_date, is_scheduled=True)
        except DutyAssignment.DoesNotExist:
            self.stdout.write("❌ No scheduled ops for this date.")
            return

        # Resolve crew display names into short variables to keep source lines
        # under the length limit while preserving exact text.
        instr_name = (
            assignment.instructor.full_display_name if assignment.instructor else "—"
        )
        surge_instr_name = (
            assignment.surge_instructor.full_display_name
            if assignment.surge_instructor
            else "—"
        )
        tow_pilot_name = (
            assignment.tow_pilot.full_display_name if assignment.tow_pilot else "—"
        )
        surge_tow_name = (
            assignment.surge_tow_pilot.full_display_name
            if assignment.surge_tow_pilot
            else "—"
        )
        duty_officer_name = (
            assignment.duty_officer.full_display_name if assignment.duty_officer else "—"
        )
        assistant_do_name = (
            assignment.assistant_duty_officer.full_display_name
            if assignment.assistant_duty_officer
            else "—"
        )

        crew_fields = [
            assignment.instructor,
            assignment.surge_instructor,
            assignment.tow_pilot,
            assignment.surge_tow_pilot,
            assignment.duty_officer,
            assignment.assistant_duty_officer,
        ]
        to_emails = []
        for m in crew_fields:
            if m and m.email:
                to_emails.append(m.email)

        grounded_gliders = MaintenanceIssue.objects.filter(
            glider__isnull=False, grounded=True, resolved=False
        )
        grounded_towplanes = MaintenanceIssue.objects.filter(
            towplane__isnull=False, grounded=True, resolved=False
        )
        upcoming_deadlines = MaintenanceDeadline.objects.filter(
            due_date__lte=target_date + timedelta(days=30)
        )

        lines = [f"🚨 Pre-Operations Summary for {target_date}", ""]

        lines.append("👥 Assigned Duty Crew:")
        lines.append("🎓 Instructor: %s" % instr_name)
        lines.append("🎓 Surge Instructor: %s" % surge_instr_name)
        lines.append("🛩️ Tow Pilot: %s" % tow_pilot_name)
        lines.append("🛩️ Surge Tow Pilot: %s" % surge_tow_name)
        lines.append("📋 Duty Officer: %s" % duty_officer_name)
        lines.append("💪 Assistant DO: %s" % assistant_do_name)
        lines.append("")

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
                aircraft = d.glider or d.towplane or "Unknown Aircraft"
                lines.append(f"- {aircraft} :: {d.description} due {d.due_date}")
        else:
            lines.append("- None")

        body = "\n".join(lines)

        if to_emails:
            subject = f"Pre-Ops Report for {assignment.date}"
            send_mail(
                subject=subject,
                message=body,
                from_email="noreply@default.manage2soar.com",
                recipient_list=to_emails,
            )
            sent_msg = f"\u2705 Email sent to: {', '.join(to_emails)}"
            self.stdout.write(self.style.SUCCESS(sent_msg))
        else:
            self.stdout.write(
                self.style.WARNING(
                    (
                        "⚠️ No valid email addresses for duty crew. "
                        "Email not sent."
                    )
                )
            )
