# instructors/utils.py

import logging
from datetime import timedelta

from django.db.models import Count, F, Max, Sum, Value
from django.db.models.fields import DurationField
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone

from logsheet.models import Flight
from siteconfig.models import MailingList, SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url

from .models import (
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    StudentProgressSnapshot,
    TrainingLesson,
)

logger = logging.getLogger(__name__)


####################################################
# get_flight_summary_for_member
#
# Generates a per-glider summary of flight activity for the given member,
# aggregating counts, total durations, and most recent dates for solo,
# dual (with instructor), given (instructor) and total flights.
#
# Parameters:
# - member: Member instance acting as either pilot or instructor.
#
# Returns:
# - List of dicts, one per glider (identified by n_number), plus a 'Totals' row:
#     {
#       'n_number': str,
#       'solo_count': int,
#       'solo_time': str ("H:MM"),
#       'solo_last': date,
#       'with_count': int,
#       'with_time': str,
#       'with_last': date,
#       'given_count': int,
#       'given_time': str,
#       'given_last': date,
#       'total_count': int,
#       'total_time': str,
#       'total_last': date,
#     }
####################################################
def get_flight_summary_for_member(member):
    pilot_qs = Flight.objects.filter(pilot=member, glider__isnull=False)

    def summarize(qs, prefix, extra_filter=None):
        """
        Helper to aggregate a queryset of Flight objects:
        - Count of flights (prefix_count)
        - Sum of durations with zero fallback (prefix_time)
        - Maximum log_date (prefix_last)
        """
        if extra_filter:
            qs = qs.filter(**extra_filter)
        return qs.values(n_number=F("glider__n_number")).annotate(
            **{
                f"{prefix}_count": Count("id"),
                f"{prefix}_time": Coalesce(
                    Sum("duration"),
                    Value(timedelta(0), output_field=DurationField()),
                    output_field=DurationField(),
                ),
                f"{prefix}_last": Max("logsheet__log_date"),
            }
        )

    solo = summarize(pilot_qs, "solo", {"instructor__isnull": True})
    with_i = summarize(pilot_qs, "with", {"instructor__isnull": False})
    given = summarize(
        Flight.objects.filter(instructor=member, glider__isnull=False), "given"
    )
    total = summarize(pilot_qs, "total")

    # Merge all prefixes into a dict keyed by n_number
    data = {}
    for qs in (solo, with_i, given, total):
        for row in qs:
            data.setdefault(row["n_number"], {}).update(row)

    # Prepare totals accumulator
    flights_summary: list[dict] = []
    totals: dict = {"n_number": "Totals"}
    for field in ("solo", "with", "given", "total"):
        totals[f"{field}_count"] = 0
        totals[f"{field}_time"] = timedelta(0)
        totals[f"{field}_last"] = None

    for n in sorted(data):
        row = data[n]
        # Ensure missing keys get default values
        for k, v in totals.items():
            row.setdefault(k, v)
        flights_summary.append(row)
        # Accumulate into totals
        for field in ("solo", "with", "given", "total"):
            totals[f"{field}_count"] += row[f"{field}_count"]
            totals[f"{field}_time"] += row[f"{field}_time"]
            last = row[f"{field}_last"]
            if last and (
                totals[f"{field}_last"] is None or last > totals[f"{field}_last"]
            ):
                totals[f"{field}_last"] = last

    flights_summary.append(totals)

    # Format durations as "H:MM"
    for row in flights_summary:
        for prefix in ("solo", "with", "given", "total"):
            dur = row.get(f"{prefix}_time")
            if isinstance(dur, timedelta):
                total_minutes = int(dur.total_seconds() // 60)
                h, m = divmod(total_minutes, 60)
                row[f"{prefix}_time"] = f"{h}:{m:02d}"
            else:
                row[f"{prefix}_time"] = ""

    return flights_summary


####################################################
# update_student_progress_snapshot
#
# Recomputes (or creates) a StudentProgressSnapshot for the given student.
# - sessions: total number of InstructionReport + GroundInstruction entries
# - solo_progress: fraction of solo-required lessons with score ≥3
# - checkride_progress: fraction of rating-required lessons with score ==4
#
# Automatically updates last_updated timestamp.
####################################################
def update_student_progress_snapshot(student):
    snapshot, _ = StudentProgressSnapshot.objects.get_or_create(student=student)

    # 1. Session counting
    report_sessions = InstructionReport.objects.filter(student=student).count()
    ground_sessions = GroundInstruction.objects.filter(student=student).count()
    snapshot.sessions = report_sessions + ground_sessions

    # 2. Identify required lesson IDs
    lessons = list(TrainingLesson.objects.all())
    solo_ids = [l.id for l in lessons if l.far_requirement]
    rating_ids = [l.id for l in lessons if l.is_required_for_private()]

    solo_total = len(solo_ids)
    rating_total = len(rating_ids)

    # 3. Collect completed lesson IDs from both scoring tables
    ls_solo = set(
        LessonScore.objects.filter(
            report__student=student, lesson_id__in=solo_ids, score__gte="3"
        ).values_list("lesson_id", flat=True)
    )
    gs_solo = set(
        GroundLessonScore.objects.filter(
            session__student=student, lesson_id__in=solo_ids, score__gte="3"
        ).values_list("lesson_id", flat=True)
    )

    ls_rating = set(
        LessonScore.objects.filter(
            report__student=student, lesson_id__in=rating_ids, score="4"
        ).values_list("lesson_id", flat=True)
    )
    gs_rating = set(
        GroundLessonScore.objects.filter(
            session__student=student, lesson_id__in=rating_ids, score="4"
        ).values_list("lesson_id", flat=True)
    )

    # 4. Compute progress ratios
    solo_done = ls_solo.union(gs_solo)
    rating_done = ls_rating.union(gs_rating)

    snapshot.solo_progress = (len(solo_done) / solo_total) if solo_total else 0.0
    snapshot.checkride_progress = (
        (len(rating_done) / rating_total) if rating_total else 0.0
    )

    # 5. Save and timestamp
    snapshot.last_updated = timezone.now()
    snapshot.save()
    return snapshot


####################################################
# send_instruction_report_email
#
# Sends an email to the student with their instruction report.
# Optionally CCs the instructors mailing list if configured.
#
# Parameters:
# - report: InstructionReport instance
# - is_update: Boolean indicating if this is an update to an existing report
# - new_qualifications: Optional list of MemberQualification instances
#   that were awarded during this instruction session
#
# Returns:
# - int: Number of emails sent (0 or 1)
####################################################
def send_instruction_report_email(report, is_update=False, new_qualifications=None):
    """Send instruction report email to student and optionally CC instructors."""
    if not report.student.email:
        logger.warning(
            f"Cannot send instruction report email: student {report.student!s} has no email"
        )
        return 0

    # Get site configuration
    config = SiteConfiguration.objects.first()
    club_name = config.club_name if config else "Manage2Soar"
    domain_name = config.domain_name if config else "manage2soar.com"

    # Build URLs
    site_url = f"https://{domain_name}"
    logbook_url = f"{site_url}/instructors/instruction-record/{report.student.id}/"

    # Get club logo URL if available (uses helper for proper absolute URL)
    club_logo_url = get_absolute_club_logo_url(config)

    # Get lesson scores for this report
    lesson_scores = report.lesson_scores.select_related("lesson").order_by(
        "lesson__code"
    )

    # Build email context
    context = {
        "student": report.student,
        "instructor": report.instructor,
        "report_date": report.report_date,
        "report_text": report.report_text,
        "is_simulator": report.simulator,
        "is_update": is_update,
        "lesson_scores": lesson_scores,
        "new_qualifications": new_qualifications or [],
        "club_name": club_name,
        "club_logo_url": club_logo_url,
        "site_url": site_url,
        "logbook_url": logbook_url,
    }

    # Render email templates
    html_message = render_to_string(
        "instructors/emails/instruction_report.html", context
    )
    text_message = render_to_string(
        "instructors/emails/instruction_report.txt", context
    )

    # Build subject line
    subject_prefix = "Updated: " if is_update else ""
    subject = (
        f"{subject_prefix}Instruction Report - "
        f"{report.student.first_name} {report.student.last_name} - "
        f"{report.report_date.strftime('%B %d, %Y')}"
    )

    # Get from email
    from_email = f"noreply@{domain_name}"

    # Check for instructors mailing list to CC
    cc_emails = []
    try:
        instructors_list = MailingList.objects.filter(
            name__iexact="instructors", is_active=True
        ).first()
        if instructors_list:
            cc_emails = instructors_list.get_subscriber_emails()
            # Remove the student from CC if they happen to be on the list
            if report.student.email in cc_emails:
                cc_emails.remove(report.student.email)
    except Exception as e:
        logger.warning(f"Could not get instructors mailing list: {e!s}")

    # Send the email
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=[report.student.email],
            html_message=html_message,
            cc=cc_emails if cc_emails else None,
        )
        logger.info(
            f"Sent instruction report email to {report.student.email}"
            f"{' (CC: instructors)' if cc_emails else ''}"
        )
        return 1
    except Exception as e:
        logger.exception(f"Failed to send instruction report email: {e!s}")
        return 0
