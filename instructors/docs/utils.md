## See Also
- [README (App Overview)](README.md)
- [Management Commands](management.md)
- [Models](models.md)
- [Signals](signals.md)
- [Views](views.md)
- [Decorators](decorators.md)
# Utilities Reference

This document outlines the primary utility functions defined in **instructors/utils.py**, detailing their purpose, parameters, return values, and side effects.

---

## `get_flight_summary_for_member(member)`

Aggregates flight activity for a given `Member`, summarizing per-glider counts, durations, and most recent dates for different flight categories.

**Parameters**

* `member` (`Member`): The user for whom to generate the flight summary. May act as pilot or instructor.

**Functionality**

1. Filters `Flight` records where `pilot=member` and `glider` is not null.
2. Defines an inner helper `summarize(qs, prefix, extra_filter=None)` to annotate:

   * `<prefix>_count`: Number of flights.
   * `<prefix>_time`: Sum of `duration` (zero fallback).
   * `<prefix>_last`: Latest `logsheet.log_date`.
3. Computes four categories of flights:

   * **solo** (no instructor)
   * **with** (with instructor)
   * **given** (where `member` is instructor)
   * **total** (all pilot flights)
4. Merges annotations by glider `n_number` into a combined dictionary.
5. Builds a sorted list of per-glider rows plus a "Totals" row, each containing fields:

   ```yaml
   n_number: str               # Glider ID or 'Totals'
   solo_count: int
   solo_time: 'H:MM'
   solo_last: date
   with_count: int
   with_time: 'H:MM'
   with_last: date
   given_count: int
   given_time: 'H:MM'
   given_last: date
   total_count: int
   total_time: 'H:MM'
   total_last: date
   ```

**Return**

* `List[Dict]`: Each dict corresponds to one glider summary, with the final entry labeled `n_number='Totals'`.

**Usage Example**

```python
summary = get_flight_summary_for_member(request.user)
for row in summary:
    print(row['n_number'], row['total_count'], row['total_time'])
```

---

## `update_student_progress_snapshot(student)`

Recomputes or creates a `StudentProgressSnapshot` for a given `Member`, storing precomputed progress metrics for dashboard performance.

**Parameters**

* `student` (`Member`): The student whose snapshot to rebuild.

**Functionality**

1. Retrieves or creates a `StudentProgressSnapshot` instance.
2. **Session counting**:

   * Counts `InstructionReport` entries where `report.student=student`.
   * Counts `GroundInstruction` entries where `session.student=student`.
   * Sets `snapshot.sessions = report_count + ground_count`.
3. **Lesson ID extraction**:

   * Gathers all `TrainingLesson` objects.
   * `solo_ids = [l.id for l in lessons if l.far_requirement]`.
   * `rating_ids = [l.id for l in lessons if l.is_required_for_private()]`.
4. **Score aggregation**:

   * Fetches distinct lesson IDs from both `LessonScore` and `GroundLessonScore` tables where scores meet thresholds:

     * Solo: `score >= '3'` on `solo_ids`.
     * Rating: `score == '4'` on `rating_ids`.
   * Combines sets: `solo_done = ls_solo ∪ gs_solo`; `rating_done = ls_rating ∪ gs_rating`.
5. **Progress computation**:

   * `snapshot.solo_progress = len(solo_done) / len(solo_ids)` (guard against zero).
   * `snapshot.checkride_progress = len(rating_done) / len(rating_ids)`.
6. Updates `snapshot.last_updated = timezone.now()` and saves.

**Returns**

* `StudentProgressSnapshot`: The updated snapshot instance.

**Side Effects**

* Writes to the database, updating or inserting a row in `StudentProgressSnapshot`.
* Typically triggered by signal handlers on save of instructional models.

**Usage Example**

```python
from instructors.utils import update_student_progress_snapshot
update_student_progress_snapshot(some_student)
```
