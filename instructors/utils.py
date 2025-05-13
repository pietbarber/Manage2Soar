# instructors/utils.py

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Max, F, Value
from django.db.models.functions import Coalesce
from django.db.models.fields import DurationField
from logsheet.models import Flight
from .models import (
    StudentProgressSnapshot,
    GroundInstruction,
    GroundLessonScore,
    TrainingLesson,
    InstructionReport,
    LessonScore,
)

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
        return (
            qs
            .values(n_number=F('glider__n_number'))
            .annotate(
                **{
                    f"{prefix}_count": Count('id'),
                    f"{prefix}_time": Coalesce(
                        Sum('duration'),
                        Value(timedelta(0), output_field=DurationField()),
                        output_field=DurationField()
                    ),
                    f"{prefix}_last": Max('logsheet__log_date'),
                }
            )
        )

    solo   = summarize(pilot_qs, 'solo', {'instructor__isnull': True})
    with_i = summarize(pilot_qs, 'with', {'instructor__isnull': False})
    given  = summarize(
        Flight.objects.filter(instructor=member, glider__isnull=False),
        'given'
    )
    total  = summarize(pilot_qs, 'total')

    # Merge all prefixes into a dict keyed by n_number
    data = {}
    for qs in (solo, with_i, given, total):
        for row in qs:
            data.setdefault(row['n_number'], {}).update(row)

    # Prepare totals accumulator
    flights_summary = []
    totals = {'n_number': 'Totals'}
    for field in ('solo', 'with', 'given', 'total'):
        totals[f'{field}_count'] = 0
        totals[f'{field}_time']  = timedelta(0)
        totals[f'{field}_last']  = None

    for n in sorted(data):
        row = data[n]
        # Ensure missing keys get default values
        for k, v in totals.items():
            row.setdefault(k, v)
        flights_summary.append(row)
        # Accumulate into totals
        for field in ('solo', 'with', 'given', 'total'):
            totals[f'{field}_count'] += row[f'{field}_count']
            totals[f'{field}_time']  += row[f'{field}_time']
            last = row[f'{field}_last']
            if last and (totals[f'{field}_last'] is None or last > totals[f'{field}_last']):
                totals[f'{field}_last'] = last

    flights_summary.append(totals)

    # Format durations as "H:MM"
    for row in flights_summary:
        for prefix in ('solo', 'with', 'given', 'total'):
            dur = row.get(f'{prefix}_time')
            if isinstance(dur, timedelta):
                total_minutes = int(dur.total_seconds() // 60)
                h, m = divmod(total_minutes, 60)
                row[f'{prefix}_time'] = f"{h}:{m:02d}"
            else:
                row[f'{prefix}_time'] = ""

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
    lessons    = list(TrainingLesson.objects.all())
    solo_ids   = [l.id for l in lessons if l.far_requirement]
    rating_ids = [l.id for l in lessons if l.is_required_for_private()]

    solo_total   = len(solo_ids)
    rating_total = len(rating_ids)

    # 3. Collect completed lesson IDs from both scoring tables
    ls_solo = set(
        LessonScore.objects
        .filter(report__student=student, lesson_id__in=solo_ids, score__gte='3')
        .values_list('lesson_id', flat=True)
    )
    gs_solo = set(
        GroundLessonScore.objects
        .filter(session__student=student, lesson_id__in=solo_ids, score__gte='3')
        .values_list('lesson_id', flat=True)
    )

    ls_rating = set(
        LessonScore.objects
        .filter(report__student=student, lesson_id__in=rating_ids, score='4')
        .values_list('lesson_id', flat=True)
    )
    gs_rating = set(
        GroundLessonScore.objects
        .filter(session__student=student, lesson_id__in=rating_ids, score='4')
        .values_list('lesson_id', flat=True)
    )

    # 4. Compute progress ratios
    solo_done   = ls_solo.union(gs_solo)
    rating_done = ls_rating.union(gs_rating)

    snapshot.solo_progress      = (len(solo_done) / solo_total) if solo_total else 0.0
    snapshot.checkride_progress = (len(rating_done) / rating_total) if rating_total else 0.0

    # 5. Save and timestamp
    snapshot.last_updated = timezone.now()
    snapshot.save()
    return snapshot
