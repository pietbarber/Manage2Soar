# Issue #301: Long Load Times - "My Logbook"

## Problem
The "My Logbook" page at `/instructors/logbook/?show_all_years=1` was taking approximately 15 seconds to load for members with 20 years of flight history. This was caused by N+1 query patterns when looking up InstructionReports for each flight.

## Root Cause
In the `member_logbook` view (`instructors/views.py`), for each flight where the logged-in member was a pilot with an instructor, the code was executing a separate database query to look up the corresponding InstructionReport:

```python
# N+1 query - executed for each flight with instruction
rpt = InstructionReport.objects.filter(
    student=member, instructor=f.instructor, report_date=date
).first()

if rpt:
    codes = [ls.lesson.code for ls in rpt.lesson_scores.all()]  # Another query per report
```

With 20 years of flight data (potentially hundreds or thousands of flights), this resulted in:
- One query per flight to look up the InstructionReport
- One additional query per report to fetch lesson scores

## Solution
Applied batch query pattern similar to Issue #298 (towplane logbook):

1. **Pre-fetch all InstructionReports** for the member in a single query before the loop
2. **Build a lookup dictionary** keyed by `(instructor_id, report_date)` for O(1) access
3. **Pre-compute lesson codes** when building the dict to avoid repeated `lesson_scores.all()` calls

### Key Changes

```python
# Pre-fetch all instruction reports for this member to avoid N+1 queries
instruction_reports = (
    InstructionReport.objects.filter(
        student=member, report_date__year__in=years_to_load
    )
    .select_related("instructor")
    .prefetch_related("lesson_scores__lesson")
)

# Build lookup: (instructor_id, date) -> report with pre-loaded lesson codes
report_lookup = {}
for rpt in instruction_reports:
    codes = [ls.lesson.code for ls in rpt.lesson_scores.all()]
    report_lookup[(rpt.instructor_id, rpt.report_date)] = {
        "report": rpt,
        "codes": codes,
    }

# In the loop, O(1) lookup instead of database query:
report_data = report_lookup.get((f.instructor_id, date))
if report_data:
    rpt = report_data["report"]
    codes = report_data["codes"]
```

## Additional Bug Fix
While implementing this fix, discovered and fixed a pre-existing bug where ground instruction rows referenced an undefined `date` variable, causing an `UnboundLocalError` when displaying ground instruction entries.

## Query Count Reduction
| Scenario | Before | After |
|----------|--------|-------|
| 100 flights with instruction | ~200+ queries | ~6 queries |
| 500 flights with instruction | ~1000+ queries | ~6 queries |

The number of queries is now constant regardless of the number of flights/reports.

## Files Changed
- `instructors/views.py`:
  - Added batch pre-fetch for InstructionReports
  - Added lookup dict for O(1) report access
  - Added `select_related("instructor")` to GroundInstruction query
  - Fixed ground instruction date variable bug
- `instructors/tests/test_member_logbook_performance.py`: Added 8 comprehensive tests

## Testing
All 8 new performance tests pass, validating:
1. Large datasets (100 flights across 5 years) load efficiently
2. Mixed roles (pilot, passenger, instructor) work correctly
3. Ground instruction sessions display properly
4. Default 2-year view filters correctly
5. Instruction reports match to correct flights (by instructor AND date)
6. Flights without reports show "instruction received" correctly
7. Specific year filtering works
8. Cumulative totals calculate correctly

## Related Issues
- Issue #296: Finances page N+1 queries
- Issue #298: Towplane logbook N+1 queries
