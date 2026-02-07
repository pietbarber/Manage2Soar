"""
Send 48-hour advance summary emails to instructors.

This management command sends a nicely formatted HTML email to instructors
scheduled for duty 48 hours from now, summarizing:
- Students who have requested instruction
- Student progress information (solo/checkride percentages, session counts)
- Links to review and respond to requests

This runs as a CronJob with distributed locking to prevent duplicate sends
across multiple Kubernetes pods.
"""

from datetime import timedelta

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import now

from duty_roster.models import DutyAssignment, InstructionSlot
from instructors.models import StudentProgressSnapshot
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.management.commands.base_cronjob import BaseCronJobCommand
from utils.url_helpers import build_absolute_url, get_canonical_url


class Command(BaseCronJobCommand):
    job_name = "send_instructor_summary_emails"
    max_execution_time = timedelta(minutes=15)

    help = "Send 48-hour advance summary email to scheduled instructors"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--date",
            type=str,
            help="Target date for instruction (YYYY-MM-DD). Default is 2 days from now.",
        )
        parser.add_argument(
            "--hours-ahead",
            type=int,
            default=48,
            help="Hours ahead to look for scheduled instructors (default: 48)",
        )

    def execute_job(self, *args, **options):
        """Execute the summary email job."""
        from datetime import datetime

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
        if options.get("date"):
            try:
                target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("Invalid date format. Use YYYY-MM-DD.")
                )
                return
        else:
            hours_ahead = options.get("hours_ahead", 48)
            target_date = (now() + timedelta(hours=hours_ahead)).date()

        self.stdout.write(
            self.style.NOTICE(f"Generating instructor summary emails for {target_date}")
        )

        # Get assignments scheduled for target date
        try:
            assignments = DutyAssignment.objects.filter(
                date=target_date, is_scheduled=True
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error querying assignments: {e}"))
            return

        if not assignments.exists():
            self.stdout.write("No scheduled ops for this date.")
            return

        # Get site configuration
        config = SiteConfiguration.objects.first()
        site_url = get_canonical_url()

        emails_sent = 0
        errors = 0

        for assignment in assignments:
            # Collect instructors for this assignment
            # Avoid adding surge_instructor if same as primary instructor
            instructors = []
            if assignment.instructor:
                instructors.append(assignment.instructor)
            if (
                assignment.surge_instructor
                and assignment.surge_instructor != assignment.instructor
            ):
                instructors.append(assignment.surge_instructor)

            if not instructors:
                self.stdout.write(
                    self.style.WARNING(f"No instructors assigned for {target_date}")
                )
                continue

            # Get instruction slots for this assignment
            slots = InstructionSlot.objects.filter(
                assignment=assignment,
                status__in=["pending", "confirmed", "waitlist"],
            ).select_related("student")

            if not slots.exists():
                self.stdout.write(
                    f"No students requesting instruction for {target_date}"
                )
                # Still send summary even with no students so instructor knows
                # they don't have anyone scheduled

            # Build student info with progress data
            students_data = self._build_students_data(slots)

            # Calculate days until
            today = now().date()
            days_until = (target_date - today).days

            # Send to each instructor
            for instructor in instructors:
                if not instructor.email:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Instructor {instructor.full_display_name} has no email"
                        )
                    )
                    continue

                if self.dry_run:
                    self.stdout.write(
                        f"Would send summary to {instructor.email} for {target_date}"
                    )
                    continue

                try:
                    self._send_summary_email(
                        instructor=instructor,
                        target_date=target_date,
                        days_until=days_until,
                        students_data=students_data,
                        config=config,
                        site_url=site_url,
                    )
                    emails_sent += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Failed to send to {instructor.email}: {e}")
                    )
                    errors += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sent {emails_sent} summary emails ({errors} errors)")
        )

    def _build_students_data(self, slots):
        """Build list of student data with progress info."""
        from django.db.models import Count

        from logsheet.models import Flight

        students_data = []

        # Get all student IDs for bulk query
        student_ids = [slot.student_id for slot in slots]

        # Bulk query for flight counts to avoid N+1
        # Students appear as 'pilot' in Flight records
        flight_counts = {}
        if student_ids:
            counts = (
                Flight.objects.filter(pilot_id__in=student_ids)
                .values("pilot_id")
                .annotate(count=Count("id"))
            )
            flight_counts = {item["pilot_id"]: item["count"] for item in counts}

        for slot in slots:
            student = slot.student

            # Get progress snapshot if available
            progress_data = None
            try:
                progress = StudentProgressSnapshot.objects.get(student=student)
                progress_data = {
                    "solo_progress": int((progress.solo_progress or 0) * 100),
                    "checkride_progress": int((progress.checkride_progress or 0) * 100),
                    "sessions": progress.sessions or 0,
                }
            except StudentProgressSnapshot.DoesNotExist:
                # Student has no progress snapshot yet - expected for new students
                pass

            students_data.append(
                {
                    "student": student,
                    "slot": slot,
                    "status": slot.status,  # Raw value for template comparison
                    "progress": progress_data,
                    "total_flights": flight_counts.get(student.pk, 0),
                }
            )

        return students_data

    def _send_summary_email(
        self, instructor, target_date, days_until, students_data, config, site_url
    ):
        """Send summary email to a single instructor."""
        # Get logo URL
        logo_url = None
        if config and config.club_logo:
            logo_url = config.club_logo.url
            if not logo_url.startswith(("http://", "https://")):
                logo_url = f"{site_url.rstrip('/')}{logo_url}"

        # Count pending requests for action reminder
        pending_count = sum(1 for s in students_data if s.get("status") == "pending")

        context = {
            "instructor": instructor,
            "instruction_date": target_date,
            "days_until": days_until,
            "students": students_data,
            "pending_count": pending_count,
            "club_name": config.club_name if config else "Soaring Club",
            "club_logo_url": logo_url,
            "site_url": site_url,
            "review_url": build_absolute_url(
                reverse("duty_roster:instructor_requests"), canonical=site_url
            ),
            "calendar_url": build_absolute_url(
                reverse("duty_roster:duty_calendar"), canonical=site_url
            ),
        }

        html_message = render_to_string(
            "instructors/emails/instructor_summary.html", context
        )
        text_message = render_to_string(
            "instructors/emails/instructor_summary.txt", context
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

        # Build subject line
        student_count = len(students_data)
        if days_until == 1:
            when = "Tomorrow"
        elif days_until == 2:
            when = "In 2 days"
        else:
            when = f"On {target_date.strftime('%A, %B %d')}"

        if student_count == 0:
            subject = f"{when}: No students scheduled for instruction"
        elif student_count == 1:
            subject = f"{when}: 1 student requesting instruction"
        else:
            subject = f"{when}: {student_count} students requesting instruction"

        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[instructor.email],
            html_message=html_message,
        )

        self.stdout.write(self.style.SUCCESS(f"  Sent summary to {instructor.email}"))
