# instructors/utils.py
# instructors/utils.py

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Max, F, Value
from django.db.models.functions import Coalesce
from django.db.models.fields import DurationField
from logsheet.models import Flight
from .models import StudentProgressSnapshot, GroundInstruction, GroundLessonScore, TrainingLesson, InstructionReport, LessonScore

def get_flight_summary_for_member(member):
    pilot_qs = Flight.objects.filter(pilot=member, glider__isnull=False)

    def summarize(qs, prefix, extra_filter=None):
        if extra_filter:
            qs = qs.filter(**extra_filter)
        return (
            qs
            .values(n_number=F('glider__n_number'))
            .annotate(
                **{
                    # restore the flight count
                    f"{prefix}_count": Count('id'),
                    # sum durations with zero‐timedelta fallback
                    f"{prefix}_time": Coalesce(
                        Sum('duration'),
                        Value(timedelta(0), output_field=DurationField()),
                        output_field=DurationField()
                    ),
                    # most recent date
                    f"{prefix}_last": Max('logsheet__log_date'),
                }
            )
        )

    solo   = summarize(pilot_qs, 'solo', {'instructor__isnull': True})
    with_i = summarize(pilot_qs, 'with', {'instructor__isnull': False})
    given  = summarize(
        Flight.objects.filter(
            instructor=member,
            glider__isnull=False   # skip null‐glider flights here too
        ),
        'given'
    )

    total  = summarize(pilot_qs, 'total')

    # merge into per-glider dicts
    data = {}
    for qs in (solo, with_i, given, total):
        for row in qs:
            data.setdefault(row['n_number'], {}).update(row)

    # build sorted list + totals
    flights_summary = []
    totals = {'n_number':'Totals'}
    for field in ('solo','with','given','total'):
        totals[f'{field}_count'] = 0
        totals[f'{field}_time']  = timedelta(0)
        totals[f'{field}_last']  = None

    for n in sorted(data):
        row = data[n]
        # default missing keys
        for k, v in totals.items():
            if k not in row:
                row[k] = v
        flights_summary.append(row)
        # accumulate
        for field in ('solo','with','given','total'):
            totals[f'{field}_count'] += row[f'{field}_count']
            totals[f'{field}_time']  += row[f'{field}_time']
            last = row[f'{field}_last']
            if last and (totals[f'{field}_last'] is None or last > totals[f'{field}_last']):
                totals[f'{field}_last'] = last

    flights_summary.append(totals)

    # ── Format all duration fields as H:MM strings ──
    for row in flights_summary:
        for prefix in ('solo', 'with', 'given', 'total'):
            dur = row.get(f'{prefix}_time')
            if isinstance(dur, timedelta):
                total_minutes = int(dur.total_seconds() // 60)
                h, m = divmod(total_minutes, 60)
                row[f'{prefix}_time'] = f"{h}:{m:02d}"
            else:
                # no duration: show empty
                row[f'{prefix}_time'] = ""

    return flights_summary

    ##################################
    # Rebuild the progress snapshot for a given student:
    #  - sessions: count of both InstructionReport sessions AND GroundInstruction sessions
    #  - solo_progress: fraction of solo-required lessons scored ≥3
    #  - checkride_progress: fraction of checkride-required lessons scored ==4

def update_student_progress_snapshot(student):
    snapshot, _ = StudentProgressSnapshot.objects.get_or_create(student=student)

    # 1. Count sessions
    # ✅ Count flight-based reports instead of Flight objects
    report_sessions = InstructionReport.objects.filter(student=student).count()
    # ✅ Count ground sessions
    ground_sessions = GroundInstruction.objects.filter(student=student).count()
    # ✅ Sum them both
    snapshot.sessions = report_sessions + ground_sessions

    print(f"DEBUG {student}: reports={report_sessions}, ground={ground_sessions}")

    # 2) figure out which lessons count
    lessons     = list(TrainingLesson.objects.all())
    solo_ids    = [l.id for l in lessons if l.far_requirement]
    rating_ids  = [l.id for l in lessons if l.is_required_for_private()]

    solo_total   = len(solo_ids)
    rating_total = len(rating_ids)

    # 3) fetch distinct lesson IDs from both score tables
    ls_solo = set(
        LessonScore.objects
        .filter(report__student=student,
                lesson_id__in=solo_ids,
                score__gte=3)
        .values_list('lesson_id', flat=True)
    )
    gs_solo = set(
        GroundLessonScore.objects
        .filter(session__student=student,
                lesson_id__in=solo_ids,
                score__gte=3)
        .values_list('lesson_id', flat=True)
    )

    ls_rating = set(
        LessonScore.objects
        .filter(report__student=student,
                lesson_id__in=rating_ids,
                score=4)
        .values_list('lesson_id', flat=True)
    )
    gs_rating = set(
        GroundLessonScore.objects
        .filter(session__student=student,
                lesson_id__in=rating_ids,
                score=4)
        .values_list('lesson_id', flat=True)
    )

    # 4) combine and compute ratios
    solo_done    = ls_solo.union(gs_solo)
    rating_done  = ls_rating.union(gs_rating)

    snapshot.solo_progress      = (len(solo_done)   / solo_total)   if solo_total   else 0.0
    snapshot.checkride_progress = (len(rating_done) / rating_total) if rating_total else 0.0

    # 5) timestamp & save
    snapshot.last_updated = timezone.now()
    snapshot.save()
    return snapshot
