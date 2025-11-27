# Issue #298: Towplane Logbook Page Performance Optimization

## Problem
The towplane logbook page (`/logsheet/towplane/<id>/logbook/`) was extremely slow for towplanes with long operational histories. Load times exceeded **10,000 milliseconds** for towplanes in service for 10+ years.

## Root Cause: N+1 Query Problems

The original `towplane_logbook` view had severe N+1 query issues:

### Problem 1: Per-Day Flight Queries
```python
# BEFORE: For each closeout (each day), run a separate query
for c in closeouts:
    day = c.logsheet.log_date
    # This query runs for EVERY day
    flights = Flight.objects.filter(
        towplane=towplane, logsheet__log_date=day
    ).values("tow_pilot", "guest_towpilot_name", "legacy_towpilot_name")
```

For a towplane with 1,000 days of operations, this resulted in **1,000 queries** just to get flight counts.

### Problem 2: Per-Day Maintenance Issue Queries
```python
# BEFORE: For each day in the final loop, re-query ALL issues
for day in days_sorted:
    row = daily_data[day]
    # This runs the ENTIRE issues query for EVERY day
    row["issues"] = _issues_by_day_for_towplane(towplane).get(day, [])
```

The `_issues_by_day_for_towplane()` function was called inside the loop, executing the same query N times.

## Solution: Batch Queries

### Fix 1: Pre-fetch ALL Flights in One Query
```python
# AFTER: Single query for all flights
all_flights = Flight.objects.filter(towplane=towplane).values(
    "logsheet__log_date", "tow_pilot", "guest_towpilot_name", "legacy_towpilot_name"
)

# Build per-day data in Python (fast)
flights_by_day = {}
for f in all_flights:
    day = f["logsheet__log_date"]
    if day not in flights_by_day:
        flights_by_day[day] = {"count": 0, "towpilots": set()}
    flights_by_day[day]["count"] += 1
    # ... collect tow pilot info
```

### Fix 2: Pre-fetch ALL Member Names in One Query
```python
# AFTER: Single query for all tow pilot names
id_to_name = {}
if all_towpilot_ids:
    for m in Member.objects.filter(id__in=all_towpilot_ids).only(
        "id", "first_name", "last_name", "username"
    ):
        id_to_name[m.id] = m.get_full_name() or m.username
```

### Fix 3: Pre-fetch Issues Once
```python
# AFTER: Call once BEFORE the loop
issues_by_day = _issues_by_day_for_towplane(towplane)

# Inside loop, just lookup from dict
daily_data[day] = {
    ...
    "issues": issues_by_day.get(day, []),
}
```

## Performance Results

| Metric | Before | After |
|--------|--------|-------|
| Queries (100 days) | 200+ | ~10 |
| Queries (1000 days) | 2000+ | ~10 |
| Load time (10+ years) | >10 seconds | <1 second |
| Query complexity | O(days) | O(1) |

## Key Files Modified
- `logsheet/views.py`: Rewrote `towplane_logbook()` view with batch queries

## Testing
- All 152 existing logsheet tests pass
- Added new performance tests in `test_towplane_logbook_performance.py`:
  - `test_towplane_logbook_query_count`: Verifies query count stays under threshold
  - `test_towplane_logbook_data_integrity`: Verifies data correctness with batch loading
  - `test_query_analysis`: Validates specific query patterns
  - `test_empty_logbook`: Edge case with no data
  - `test_single_day_logbook`: Edge case with minimal data

## Pattern Applied
This optimization uses the same pattern as Issue #296 (instruction record performance):

1. **Identify the loop** - Find code that runs queries inside loops
2. **Batch the query** - Move query outside loop, fetch ALL data at once
3. **Index in Python** - Build lookup dictionaries from batch results
4. **Lookup in loop** - Use O(1) dict lookups instead of O(n) queries

## Date
July 2025
