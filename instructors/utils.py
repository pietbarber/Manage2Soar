# instructors/utils.py
# instructors/utils.py

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Sum, Max, F, Value
from django.db.models.functions import Coalesce
from django.db.models.fields import DurationField
from logsheet.models import Flight
from .models import StudentProgressSnapshot, GroundInstruction, GroundLessonScore, TrainingLesson

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
    #  - sessions: count of both Flight.instructor sessions AND GroundInstruction sessions
    #  - solo_progress: fraction of solo-required lessons scored ≥3
    #  - checkride_progress: fraction of checkride-required lessons scored ==4

def update_student_progress_snapshot(student):
    snapshot, _ = StudentProgressSnapshot.objects.get_or_create(student=student)

    # 1. Count sessions
    flight_sessions = Flight.objects.filter(instructor=student).count()
    ground_sessions = GroundInstruction.objects.filter(student=student).count()
    snapshot.sessions = flight_sessions + ground_sessions

    # 2. Build lesson ID sets in Python
    lessons       = TrainingLesson.objects.all()
    solo_ids      = [l.id for l in lessons if l.far_requirement]
    rating_ids    = [l.id for l in lessons if l.is_required_for_private()]

    solo_total    = len(solo_ids)
    rating_total  = len(rating_ids)

    # 3. Count completed scores using those ID lists
    solo_completed = GroundLessonScore.objects.filter(
        session__student=student,
        lesson_id__in=solo_ids,
        score__gte=3
    ).count()

    rating_completed = GroundLessonScore.objects.filter(
        session__student=student,
        lesson_id__in=rating_ids,
        score=4
    ).count()

    # 4. Compute ratios (guard divide-by-zero)
    snapshot.solo_progress      = (solo_completed  / solo_total)   if solo_total   else 0.0
    snapshot.checkride_progress = (rating_completed / rating_total) if rating_total else 0.0

    # 5. Timestamp & save
    snapshot.last_updated = timezone.now()
    snapshot.save()

    return snapshot
