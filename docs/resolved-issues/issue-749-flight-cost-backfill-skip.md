# Issue #749: update_flight_costs Skipped Rental Backfill When Tow Actual Was Present

**Issue**: [#749](https://github.com/pietbarber/Manage2Soar/issues/749)  
**PR**: [#750](https://github.com/pietbarber/Manage2Soar/pull/750)  
**Resolved**: March 8, 2026

## Summary
Some finalized flights retained missing or zero rental actual values even though rental was computable. The backfill command (`update_flight_costs`) used a combined condition that required both tow and rental actual values to be missing/zero before updating either field.

This created a silent failure mode: flights with populated `tow_cost_actual` but missing `rental_cost_actual` were skipped.

## Root Cause
In `logsheet/management/commands/update_flight_costs.py`, the command previously used a single combined guard:

```python
if (tow_actual is None or tow_actual == 0) and (rental_actual is None or rental_actual == 0):
    flight.tow_cost_actual = flight.tow_cost or 0
    flight.rental_cost_actual = flight.rental_cost or 0
```

That logic is too strict. If either field was already populated, the command would not write the other field.

## Production Impact Observed
In tenant `tenant-ssc`:
- Logsheet `2095` (`2026-03-07`) had 6 finalized flights with `rental_cost_actual = NULL` while `tow_cost_actual` was non-zero.
- Rental values were computable and displayed correctly in model calculations, but the finalized actual field remained unset.

This presented in the UI as blank rental values for a subset of flights on the same day.

## Resolution
### Code change
Updated the command to backfill each field independently:

- Backfill `tow_cost_actual` when tow actual is missing/zero.
- Backfill `rental_cost_actual` when rental actual is missing/zero.

This preserves valid existing data while filling missing fields.

### Tests added
File: `logsheet/tests/test_update_flight_costs_command.py`

- `test_updates_rental_when_tow_actual_already_set`
- `test_after_filter_is_strictly_greater_than`
- `test_does_not_coerce_non_computable_costs_to_zero`
- `test_does_not_count_unchanged_zero_costs_as_updates`
- `test_skips_non_finalized_logsheets_when_backfilling`

These tests prevent regressions in both the field-level backfill behavior and date filter boundary behavior.

## Why This Fix Is Safe
- Existing non-zero actual values are not overwritten unless that specific field is missing/zero.
- The fix narrows behavior to backfill intent rather than recalculating all finalized costs.
- No schema changes or migrations are required.

## Prevention
1. Treat independent stored values as independent update targets.
2. Add regression tests whenever backfill commands combine multiple fields in one guard condition.
3. Prefer explicit booleans (`should_update_tow`, `should_update_rental`) over compound conditions for clarity.
4. For production remediations, use dry-run validation queries before applying updates.
5. Keep `*_actual` fields nullable to preserve unknown vs zero semantics:
   - `None` means unknown/not locked
   - Historically, some legacy rows use `0.00` as a placeholder for "missing"; `update_flight_costs` treats `*_cost_actual == 0` the same as `NULL` for backfill eligibility.

## Files Changed
- `logsheet/management/commands/update_flight_costs.py`
- `logsheet/tests/test_update_flight_costs_command.py`
- `docs/resolved-issues/issue-749-flight-cost-backfill-skip.md`
