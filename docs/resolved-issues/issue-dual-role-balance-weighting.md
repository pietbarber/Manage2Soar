# Dual-Role Balance Weighting (Duty Roster)

**Status**: Complete
**Date**: April 9, 2026
**App**: `duty_roster`
**Tenant Context**: `tenant-ssc`

## Problem Summary
A scheduling fairness concern was raised for members who can serve in both `instructor` and `towpilot` roles.

Observed pattern:
- Some dual-role members were repeatedly assigned to only one role over a generated range.
- Example allegation: members with 50/50 preference were effectively stuck in a single role.

This was difficult to validate operationally because there are relatively few real scheduling cycles and only a small number of dual-role members in this tenant.

## Root Cause
The OR-Tools objective already optimized for:
- role preference weighting,
- pairing affinity,
- staleness balancing,
- assignment concentration,
- weekend spacing.

However, there was no explicit per-member multi-role split term in the objective.

Result: even when a member had non-zero percentages in multiple roles (for example 50/50 or 25/75), the solver could still settle into one role if other objective terms and constraints made that locally attractive.

## Fix Implemented
A new soft objective component was added to the OR-Tools scheduler to penalize drift from each dual-role member's preferred split across the generated window.

### What changed
- Added `ROLE_SPLIT_BALANCE_WEIGHT` constant in `duty_roster/ortools_scheduler.py`.
- Added `_add_role_split_balance_soft_constraints()` and integrated it into objective building.
- For each member with at least two eligible roles in the model:
  - compute role assignment counts across the window,
  - compute deviation from percentage targets,
  - add absolute-deviation penalty terms to the objective.

### Preference handling behavior
- If all relevant role percentages are zero for a multi-role member, roles are treated as equally targeted.
- If only one role has a positive target, no split balancing is enforced (no split to balance).

## Validation
Targeted regression test added:
- `test_role_split_penalty_reduces_dual_role_drift`

What it verifies:
- With role-split weight disabled, baseline drift is measured.
- With role-split weight enabled, drift is reduced or at least not worsened.

## Notes and Limits
- This is a **soft** fairness objective, not a hard constraint.
- In tight staffing scenarios, hard coverage constraints still take priority over ideal split percentages.
- The fix improves balancing pressure while preserving model feasibility and operational coverage.

## Outcome
Dual-role assignment behavior now has explicit balancing pressure aligned with configured percentages, reducing the tendency for members to become stuck in only one of their qualified roles.
