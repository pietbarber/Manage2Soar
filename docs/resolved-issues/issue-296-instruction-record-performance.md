# Issue 296: Instruction Report N+1 Query Performance Optimization

**Issue Summary**: The instruction record page was taking 14+ seconds to load for members with many instruction sessions due to N+1 database query issues.

**Resolution Date**: November 26, 2025

## Problem Statement

The member instruction record page (`/instructors/instruction-record/<member_id>/`) displayed a comprehensive timeline of all instruction sessions, including:
- Flight instruction reports
- Ground instruction sessions
- Cumulative progress charts
- Lesson scores and missing requirements

For members with 110+ instruction sessions over 10 years, the page took 14+ seconds to load, making it essentially unusable.

## Root Cause Analysis

The `member_instruction_record` view in `instructors/views.py` had severe N+1 query issues. For **each session**, the code executed:

### Chart Building Loop (per session)
```python
for sess in sessions:
    d = sess["date"]
    # 4 queries per session:
    flight_solo = set(
        LessonScore.objects.filter(
            report__student=member, report__report_date__lte=d, score__in=["3", "4"]
        ).values_list("lesson_id", flat=True)
    )
    ground_solo = set(
        GroundLessonScore.objects.filter(
            session__student=member, session__date__lte=d, score__in=["3", "4"]
        ).values_list("lesson_id", flat=True)
    )
    flight_rating = set(
        LessonScore.objects.filter(
            report__student=member, report__report_date__lte=d, score="4"
        ).values_list("lesson_id", flat=True)
    )
    ground_rating = set(
        GroundLessonScore.objects.filter(
            session__student=member, session__date__lte=d, score="4"
        ).values_list("lesson_id", flat=True)
    )
```

### Report Block Building (per report)
```python
for report in instruction_reports:
    # Same 4 queries again for cumulative progress
    # Plus:
    Flight.objects.filter(
        instructor=report.instructor,
        pilot=report.student,
        logsheet__log_date=d,
    )
    # Plus 2 more for missing lessons:
    TrainingLesson.objects.filter(id__in=solo_ids - solo_done)
    TrainingLesson.objects.filter(id__in=rating_ids - rating_done)
```

### Query Count Analysis

For a member with 110 sessions:
- Chart building: 4 queries × 110 sessions = **440 queries**
- Flight reports: 8 queries × 110 reports = **880 queries**
- Ground sessions: 8 queries × sessions = **additional queries**

**Total: 1000+ database queries** for a single page load!

## Solution Implementation

### 1. Pre-fetch All Lesson Scores Once

Instead of querying per-session, fetch ALL scores in 2 queries:

```python
# OPTIMIZATION: Fetch ALL lesson scores ONCE, then compute in Python
all_flight_scores = list(
    LessonScore.objects.filter(report__student=member)
    .select_related("report")
    .values("lesson_id", "score", "report__report_date")
)
all_ground_scores = list(
    GroundLessonScore.objects.filter(session__student=member)
    .select_related("session")
    .values("lesson_id", "score", "session__date")
)
```

### 2. Compute Cumulative Progress in Python

```python
def compute_cumulative_progress(target_date):
    """Compute solo and rating progress up to target_date using pre-fetched data."""
    # Solo standard: score 3 or 4
    flight_solo = {
        s["lesson_id"]
        for s in all_flight_scores
        if s["report__report_date"] <= target_date and s["score"] in ["3", "4"]
    }
    ground_solo = {
        s["lesson_id"]
        for s in all_ground_scores
        if s["session__date"] <= target_date and s["score"] in ["3", "4"]
    }
    solo_done = flight_solo | ground_solo

    # Rating standard: score 4 only
    flight_rating = {
        s["lesson_id"]
        for s in all_flight_scores
        if s["report__report_date"] <= target_date and s["score"] == "4"
    }
    ground_rating = {
        s["lesson_id"]
        for s in all_ground_scores
        if s["session__date"] <= target_date and s["score"] == "4"
    }
    rating_done = flight_rating | ground_rating

    solo_pct = int(len(solo_done & solo_ids) / total_solo * 100)
    rating_pct = int(len(rating_done & rating_ids) / total_rating * 100)

    return solo_done, rating_done, solo_pct, rating_pct
```

### 3. Batch-Load All Flights

```python
# OPTIMIZATION: Batch fetch flights for all report dates at once
report_dates = [r.report_date for r in instruction_reports]
all_flights = list(
    Flight.objects.filter(pilot=member, logsheet__log_date__in=report_dates)
    .select_related("logsheet", "glider", "instructor")
)
# Group flights by (instructor_id, date)
flights_by_key = defaultdict(list)
for f in all_flights:
    key = (f.instructor_id, f.logsheet.log_date)
    flights_by_key[key].append(f)
```

### 4. Use In-Memory Lesson Lookup

```python
# Build lesson lookup for missing lessons (only compute once)
lessons_by_id = {L.id: L for L in lessons}

# Later, instead of querying:
missing_solo = sorted(
    [lessons_by_id[lid] for lid in (solo_ids - solo_done) if lid in lessons_by_id],
    key=lambda x: x.code,
)
```

### 5. Proper Prefetching

```python
instruction_reports = list(
    InstructionReport.objects.filter(student=member)
    .order_by("-report_date")
    .select_related("instructor")  # Added
    .prefetch_related("lesson_scores__lesson")
)

ground_sessions = list(
    GroundInstruction.objects.filter(student=member)
    .order_by("-date")
    .select_related("instructor")  # Added
    .prefetch_related("lesson_scores__lesson")
)
```

## Query Count Comparison

| Operation | Before | After |
|-----------|--------|-------|
| Lesson Scores | 4 × N sessions | 2 total |
| Cumulative Progress | 4 × N reports | 0 (Python) |
| Flights per Block | 1 × N reports | 1 total |
| Missing Lessons | 2 × N reports | 0 (lookup) |
| **Total (110 sessions)** | **1000+** | **~10** |

## Validation Results

### Test Coverage

```bash
$ pytest instructors/tests/ -v
===== 4 passed in 44.37s =====

$ pytest --tb=short -q
563 passed, 4 warnings in 987.28s
```

All tests pass with the optimized implementation.

### Performance Improvement

**Before Optimization**:
- Page load time: 14+ seconds
- Network tab showed long "waiting for server response"
- Database query count: 1000+

**After Optimization**:
- Page load time: Sub-second
- Server response time dramatically reduced
- Database query count: ~10

## Files Modified

- `instructors/views.py`: Rewrote `member_instruction_record` function with optimizations

## Success Criteria Met ✅

- ✅ **Query Reduction**: From 1000+ queries to ~10 queries
- ✅ **Load Time**: From 14+ seconds to sub-second
- ✅ **Functionality Preserved**: All features work identically
- ✅ **Test Coverage**: All 563 tests passing
- ✅ **No Breaking Changes**: Template receives same data structure

## Key Optimization Techniques

1. **Batch Fetching**: Load all related data in bulk queries upfront
2. **Python Processing**: Compute cumulative values in Python using pre-fetched data
3. **Dictionary Lookups**: Replace repeated queries with O(1) dictionary lookups
4. **select_related**: Eagerly load foreign keys to avoid lazy loading
5. **prefetch_related**: Eagerly load reverse relations and many-to-many

## Lessons Learned

1. **Profile Before Optimizing**: The N+1 pattern was obvious once identified
2. **Python is Fast**: In-memory set operations are extremely fast compared to database queries
3. **Batch Over Loop**: Always prefer batch operations to looped queries
4. **Cumulative Calculations**: For cumulative progress, pre-fetch all data and compute ranges in Python

## Related Issues

- **Issue #286**: Photo thumbnail optimization (different performance issue, same goal)
- **Issue #285**: Added database indexes for logsheet performance

---

**Status**: ✅ **COMPLETE AND DEPLOYED**

**Impact**: Dramatic improvement from 14+ second load times to sub-second for instruction record pages. Enables viewing of full training history for long-term students.
