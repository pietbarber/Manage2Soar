from datetime import timedelta, date
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils.timezone import now

from instructors.models import InstructionReport
from logsheet.models import Flight
from members.models import Member
from notifications.models import Notification
from utils.management.commands.base_cronjob import BaseCronJobCommand


class Command(BaseCronJobCommand):
    help = "Notify instructors about overdue SPRs (Student Progress Reports) at 7/14/21/25/30 day intervals"
    job_name = "notify_late_sprs"
    max_execution_time = timedelta(minutes=20)  # May need to process many flights

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--max-days',
            type=int,
            default=30,
            help='Maximum days to look back for flights needing SPRs (default: 30)'
        )

    def execute_job(self, *args, **options):
        max_days = options.get('max_days', 30)
        cutoff_date = now().date() - timedelta(days=max_days)

        self.log_info(f"Checking for overdue SPRs from flights since {cutoff_date}")

        # Find instructional flights that might need SPRs
        instructional_flights = Flight.objects.filter(
            instructor__isnull=False,  # Has an instructor
            logsheet__finalized=True,  # From finalized logsheets only
            logsheet__log_date__gte=cutoff_date,  # Within our time window
            logsheet__log_date__lt=now().date(),  # Not today's flights
        ).select_related(
            'instructor',
            'pilot',
            'logsheet'
        ).order_by('logsheet__log_date', 'instructor')

        if not instructional_flights.exists():
            self.log_info("No instructional flights found requiring SPR check")
            return

        self.log_info(
            f"Checking {instructional_flights.count()} instructional flights for missing SPRs")

        # Group flights by instructor and student combination
        instructor_student_flights = {}

        for flight in instructional_flights:
            if not flight.instructor or not flight.pilot:
                continue

            key = (flight.instructor, flight.pilot)
            if key not in instructor_student_flights:
                instructor_student_flights[key] = []

            instructor_student_flights[key].append(flight)

        # Check each instructor-student combination for missing SPRs
        overdue_sprs = {}

        for (instructor, student), flights in instructor_student_flights.items():
            # Sort flights by date to process chronologically
            flights.sort(key=lambda f: f.logsheet.log_date)

            for flight in flights:
                flight_date = flight.logsheet.log_date
                days_since_flight = (now().date() - flight_date).days

                # Check if there's an SPR for this flight
                spr_exists = InstructionReport.objects.filter(
                    instructor=instructor,
                    student=student,
                    report_date=flight_date
                ).exists()

                if not spr_exists and days_since_flight >= 7:  # Overdue threshold
                    # Determine escalation level
                    escalation_level = self._get_escalation_level(days_since_flight)

                    if instructor not in overdue_sprs:
                        overdue_sprs[instructor] = []

                    overdue_sprs[instructor].append({
                        'flight': flight,
                        'student': student,
                        'days_overdue': days_since_flight,
                        'escalation_level': escalation_level,
                        'flight_date': flight_date
                    })

        if not overdue_sprs:
            self.log_info("No overdue SPRs found")
            return

        # Send notifications
        total_instructors = len(overdue_sprs)
        total_overdue_sprs = sum(len(sprs) for sprs in overdue_sprs.values())

        self.log_info(
            f"Found {total_overdue_sprs} overdue SPRs for {total_instructors} instructor(s)")

        notifications_sent = 0
        for instructor, spr_data in overdue_sprs.items():
            if not options.get('dry_run'):
                self._send_notification(instructor, spr_data)
                notifications_sent += 1
            else:
                escalation_counts = {}
                for spr in spr_data:
                    level = spr['escalation_level']
                    escalation_counts[level] = escalation_counts.get(level, 0) + 1

                escalation_summary = ", ".join(
                    [f"{count} {level}" for level, count in escalation_counts.items()])
                self.log_info(
                    f"Would notify {instructor.full_display_name} about {len(spr_data)} overdue SPRs ({escalation_summary})")

        if notifications_sent > 0:
            self.log_success(
                f"Sent overdue SPR notifications to {notifications_sent} instructor(s)")
        else:
            self.log_info("No notifications sent (dry run mode)")

    def _get_escalation_level(self, days_overdue):
        """Determine escalation level based on days overdue"""
        if days_overdue >= 30:
            return "FINAL"  # 30+ days: Final notice
        elif days_overdue >= 25:
            return "URGENT"  # 25+ days: Urgent
        elif days_overdue >= 21:
            return "WARNING"  # 21+ days: Strong warning
        elif days_overdue >= 14:
            return "REMINDER"  # 14+ days: Escalated reminder
        else:  # 7+ days
            return "NOTICE"  # 7+ days: Initial notice

    def _send_notification(self, instructor, spr_data):
        """Send email and in-app notification to instructor about overdue SPRs"""

        # Group SPRs by escalation level for better presentation
        escalation_groups = {}
        for spr in spr_data:
            level = spr['escalation_level']
            if level not in escalation_groups:
                escalation_groups[level] = []
            escalation_groups[level].append(spr)

        # Build email content
        subject = f"Student Progress Report Reminder - {len(spr_data)} Overdue Report(s)"

        # Determine overall urgency for subject line
        if any(spr['escalation_level'] == 'FINAL' for spr in spr_data):
            subject = f"FINAL NOTICE: {subject}"
        elif any(spr['escalation_level'] == 'URGENT' for spr in spr_data):
            subject = f"URGENT: {subject}"

        message_lines = [f"Hello {instructor.full_display_name},",
                         "",
                         "The following Student Progress Reports (SPRs) are overdue:"]

        # Process each escalation level in order of severity
        escalation_order = ['FINAL', 'URGENT', 'WARNING', 'REMINDER', 'NOTICE']

        for level in escalation_order:
            if level not in escalation_groups:
                continue

            sprs = escalation_groups[level]

            # Add level-specific messaging
            level_messages = {
                'FINAL': "🚨 FINAL NOTICE (30+ days overdue) - No SPRs will be allowed after deadline:",
                'URGENT': "⚠️ URGENT (25+ days overdue):",
                'WARNING': "⚠️ WARNING (21+ days overdue):",
                'REMINDER': "📝 REMINDER (14+ days overdue):",
                'NOTICE': "📌 NOTICE (7+ days overdue):"
            }

            message_lines.append("")
            message_lines.append(level_messages[level])

            for spr in sprs:
                flight_date_str = spr['flight_date'].strftime("%A, %B %d, %Y")
                message_lines.append(
                    f"- {spr['student'].full_display_name} on {flight_date_str} ({spr['days_overdue']} days ago)"
                )

        message_lines.extend([
            "",
            "Please log into Manage2Soar to file these Student Progress Reports as soon as possible.",
            "SPRs are essential for tracking student progress and maintaining training records.",
            "",
            f"Instruction Reports: {settings.SITE_URL}/instructors/",
            "",
            "Thank you for your prompt attention to this matter.",
            "",
            "- Manage2Soar Automated Notifications"
        ])

        message = "\n".join(message_lines)

        try:
            # Send email notification
            send_mail(
                subject=subject,
                message=message,
                from_email="noreply@default.manage2soar.com",
                recipient_list=[instructor.email] if instructor.email else [],
                fail_silently=False,
            )

            # Create in-app notification with appropriate urgency
            urgency_emoji = {
                'FINAL': '🚨',
                'URGENT': '⚠️',
                'WARNING': '⚠️',
                'REMINDER': '📝',
                'NOTICE': '📌'
            }

            # Get the highest urgency level
            highest_urgency = 'NOTICE'  # Default
            for level in escalation_order:
                if level in escalation_groups:
                    highest_urgency = level
                    break

            emoji = urgency_emoji.get(highest_urgency, '📝')

            Notification.objects.create(
                user=instructor,
                message=f"{emoji} You have {len(spr_data)} overdue Student Progress Report(s)",
                url="/instructors/"
            )

            self.log_success(
                f"Notified {instructor.full_display_name} about {len(spr_data)} overdue SPR(s)")

        except Exception as e:
            self.log_error(f"Failed to notify {instructor.full_display_name}: {str(e)}")
