# Logsheet 2097: Finances Duration Displayed None While Flights Had Times

**Issue**: Production incident on logsheet `2097` (tenant `tenant-ssc`)  
**PR**: [#779](https://github.com/pietbarber/Manage2Soar/pull/779)  
**Resolved**: March 14, 2026

## Summary
The finances page showed `None` for many flight durations even though the same flights showed valid durations on the main logsheet page.

## Root Cause
Two different duration sources were used by two pages:

- Logsheet manage page used `Flight.computed_duration` (fallback from launch/landing when `duration` is null).
- Finances page rendered raw `flight.duration` directly.

When stored `duration` was null, this produced a UI mismatch:

- Main logsheet page: valid duration visible.
- Finances page: `None` visible.

## Production Impact Observed
For logsheet `2097` (`2026-03-14`):

- 24 flights total
- 18 flights had `duration = NULL`
- Those same flights had valid `launch_time` and `landing_time`, so `computed_duration` was available

## Production Remediation Applied
Targeted backfill was run only for logsheet `2097`:

- For flights with `duration IS NULL` and both launch/landing present, set `duration = computed_duration`.
- Result: `remaining_null_duration = 0` on logsheet `2097`.

## Code Resolution
### Template fix
Updated `logsheet/templates/logsheet/manage_logsheet_finances.html` to use `computed_duration` fallback:

- Table duration cell now renders `flight.computed_duration|default:"—"`
- Split modal `data-duration` now uses the same fallback

This prevents `None` from appearing when stored duration is missing.

### Tests added
File: `logsheet/tests/test_finances_ui_and_split.py`

- Added regression test: `test_finances_uses_computed_duration_when_duration_is_null`
- Verifies finances view does not show `<td>None</td>` when stored duration is null but computed duration exists.

## Similarity to Issue #749
This incident is structurally similar to `issue-749-flight-cost-backfill-skip`:

- In both cases, a stored field was missing while a computable/fallback value existed.
- In both cases, one code path used the robust fallback but another path relied on raw stored data.
- Fix strategy in both cases: align code paths to independent/fallback-safe behavior and add regression coverage.

## Why This Fix Is Safe
- No schema changes.
- Backward-compatible template behavior (uses existing model property).
- Regression test protects against reintroducing raw-duration rendering in finances.
- Production data repair was scoped to one known-impacted logsheet.
