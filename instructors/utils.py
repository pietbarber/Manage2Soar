# instructors/utils.py

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Max, Q, Sum, Value
from django.db.models.fields import DurationField
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone

from logsheet.models import Flight
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

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

    # Prepare defaults template (used for missing keys - must be separate from totals)
    defaults: dict = {}
    for field in ("solo", "with", "given", "total"):
        defaults[f"{field}_count"] = 0
        defaults[f"{field}_time"] = timedelta(0)
        defaults[f"{field}_last"] = None

    # Prepare totals accumulator
    flights_summary: list[dict] = []
    totals: dict = {"n_number": "Totals"}
    totals.update(defaults.copy())

    for n in sorted(data):
        row = data[n]
        # Ensure missing keys get default values (use defaults, not totals!)
        for k, v in defaults.items():
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


def get_logbook_glider_time_summary(member):
    """Build an all-time, per-make/model glider time summary for logbook display."""

    def format_minutes(minutes):
        hours, mins = divmod(int(minutes), 60)
        return f"{hours}:{mins:02d}"

    rating_date = getattr(member, "private_glider_checkride_date", None)

    flights = Flight.objects.filter(
        (Q(pilot=member) | Q(instructor=member)),
        glider__isnull=False,
    ).select_related("glider", "logsheet")

    summary_by_glider = defaultdict(
        lambda: {
            "dual_received_m": 0,
            "solo_m": 0,
            "instruction_given_m": 0,
            "rated_dual_for_pic_m": 0,
            "total_m": 0,
        }
    )

    for flight in flights:
        flight_date = flight.logsheet.log_date if flight.logsheet else None
        duration_m = (
            int(flight.duration.total_seconds() // 60) if flight.duration else 0
        )

        make = (flight.glider.make or "").strip()
        model = (flight.glider.model or "").strip()
        make_model = " ".join(part for part in (make, model) if part).strip()
        if not make_model:
            make_model = flight.glider.n_number or "Unknown Glider"

        bucket = summary_by_glider[make_model]

        is_pilot = flight.pilot_id == member.id
        is_instructor = flight.instructor_id == member.id

        if is_pilot and flight.instructor_id:
            bucket["dual_received_m"] += duration_m
            if rating_date and flight_date and flight_date >= rating_date:
                bucket["rated_dual_for_pic_m"] += duration_m

        if (
            is_pilot
            and not flight.instructor_id
            and not flight.passenger_id
            and not flight.passenger_name
        ):
            bucket["solo_m"] += duration_m

        if is_instructor:
            bucket["instruction_given_m"] += duration_m

        if is_pilot or is_instructor:
            bucket["total_m"] += duration_m

    rows = []
    totals = {
        "make_model": "Totals",
        "dual_received_m": 0,
        "solo_m": 0,
        "instruction_given_m": 0,
        "pic_summary_m": 0,
        "total_m": 0,
    }

    for make_model in sorted(summary_by_glider):
        bucket = summary_by_glider[make_model]
        pic_summary_m = (
            bucket["solo_m"]
            + bucket["instruction_given_m"]
            + bucket["rated_dual_for_pic_m"]
        )

        row = {
            "make_model": make_model,
            "dual_received_m": bucket["dual_received_m"],
            "solo_m": bucket["solo_m"],
            "instruction_given_m": bucket["instruction_given_m"],
            "pic_summary_m": pic_summary_m,
            "total_m": bucket["total_m"],
            "dual_received": format_minutes(bucket["dual_received_m"]),
            "solo": format_minutes(bucket["solo_m"]),
            "instruction_given": format_minutes(bucket["instruction_given_m"]),
            "pic_summary": format_minutes(pic_summary_m),
            "total": format_minutes(bucket["total_m"]),
        }
        rows.append(row)

        totals["dual_received_m"] += row["dual_received_m"]
        totals["solo_m"] += row["solo_m"]
        totals["instruction_given_m"] += row["instruction_given_m"]
        totals["pic_summary_m"] += row["pic_summary_m"]
        totals["total_m"] += row["total_m"]

    if rows:
        totals.update(
            {
                "dual_received": format_minutes(totals["dual_received_m"]),
                "solo": format_minutes(totals["solo_m"]),
                "instruction_given": format_minutes(totals["instruction_given_m"]),
                "pic_summary": format_minutes(totals["pic_summary_m"]),
                "total": format_minutes(totals["total_m"]),
            }
        )
        rows.append(totals)

    return rows


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

    # Build URLs using canonical URL helpers
    site_url = get_canonical_url()
    logbook_url = build_absolute_url(
        f"/instructors/instruction-record/{report.student.id}/"
    )

    # Get club logo URL if available (uses helper for proper absolute URL)
    club_logo_url = get_absolute_club_logo_url(config)

    # Get lesson scores for this report
    lesson_scores = report.lesson_scores.select_related("lesson").order_by(
        "lesson__sort_key"
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
    # Use the mailing list alias (e.g., instructors@skylinesoaring.org) instead of
    # expanding to individual subscriber emails. This allows the mail server to handle
    # the distribution and ensures the alias appears in the CC field.
    cc_emails = []
    try:
        # Try to get from settings first, otherwise construct from domain
        instructors_list = getattr(settings, "INSTRUCTORS_MAILING_LIST", "")
        if instructors_list and "@" in instructors_list:
            cc_emails = [instructors_list]
        elif config and config.domain_name:
            cc_emails = [f"instructors@{config.domain_name}"]
        else:
            # Fallback to default (shouldn't happen in production)
            cc_emails = [f"instructors@{domain_name}"]
    except Exception as e:
        logger.warning(f"Could not construct instructors mailing list address: {e!s}")

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
        cc_info = f" (CC: {', '.join(cc_emails)})" if cc_emails else ""
        logger.info(f"Sent instruction report email to {report.student.email}{cc_info}")
        return 1
    except Exception as e:
        logger.exception(f"Failed to send instruction report email: {e!s}")
        return 0
