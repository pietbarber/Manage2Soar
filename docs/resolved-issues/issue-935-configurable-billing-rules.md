# Issue #935: Configurable Billing Rules for Membership-Based Tow Discounts and Optional Instructor-Time Charges

**Resolution Date**: May 29, 2026  
**Branch**: feature/issue-936-configurable-billing-rules  
**Status**: Phases 1-2 Complete ✅ (Foundation + Matrix Rental Enhancements)

## Problem Set (Anonymized)

A multi-tenant billing gap was identified across two different tenant policy models:

1. **Tenant A policy need**
- Tow billing needed to vary by membership category.
- Existing architecture calculates tow cost by towplane charge scheme and altitude tiers.
- Attempting to represent membership policy by duplicating towplane schemes would create combinatorial complexity and high maintenance risk.

2. **Tenant B policy need**
- Billing for instructor time is required as a normal operational workflow.
- Existing platform already supports generic member charges, but lacked an integrated, policy-driven instructor-time billing path.

3. **Platform constraint**
- Billing behavior must be configurable per deployment and not hardcoded to any tenant identity.
- New/legacy clubs must retain current behavior unless explicitly opting in.

## Root Cause Analysis

The historical pricing model focused on aircraft/equipment dimensions, not member-category dimensions:

- Tow pricing was designed as base operational pricing (towplane + altitude tiers).
- No centralized, validated policy layer existed for per-membership pricing modifiers.
- Instructor-time billing existed as a potential generic charge, but not as a cohesive configured workflow.

## Approach and Design Decisions

### 1. Keep the proven base-rate engine
Towplane charge schemes remain the authoritative base tow calculator. This avoids destabilizing a mature pricing path.

### 2. Add a policy modifier layer
Introduce membership-status billing rules as an optional modifier after base cost calculation. This keeps the model composable:

- Base tow cost = operational truth
- Membership modifier = policy overlay

### 3. Use configuration, not tenant-name branches
Policy is enabled and tuned through site configuration and admin-managed rule data. No tenant-name checks are required.

### 4. Build phased delivery
- Phase 1 ships schema, admin controls, and tow-discount integration behind feature toggles.
- Phase 2 extends matrix behavior to support per-glider status exceptions and a configurable minimum billable rental duration.

## What Was Implemented (Phase 1)

### Configuration controls
Added new `SiteConfiguration` fields to support safe defaults and feature gating:

- `billing_rules_enabled`
- `instructor_time_charges_enabled`
- `default_tow_discount_percent`
- `default_instructor_rate_multiplier`

### Structured rule model
Added `MembershipBillingRule` keyed to configured membership statuses:

- One rule per membership status
- `tow_discount_percent`
- `instructor_rate_multiplier`
- `is_active`
- helper lookup/application methods

### Admin UX
Added admin interfaces so webmasters can manage policy without code changes:

- New Billing Rules section in Site Configuration
- New Membership Billing Rule admin table/editor

### Tow cost integration
Integrated optional tow discount application into flight tow calculation path:

- Base tow remains towplane-scheme-driven
- Modifier applies only when `billing_rules_enabled = true`
- Rule resolution path:
  1. status-specific active rule (if present)
  2. otherwise `default_tow_discount_percent`
  3. otherwise neutral default behavior

### Database migration
Added migration:

- `siteconfig/migrations/0044_siteconfiguration_billing_rules_enabled_and_more.py`

## What Was Implemented (Phase 2)

### Matrix mode rental and instruction extensions
Expanded matrix-mode pricing to support real-world club policy edge cases:

- Added matrix-mode absolute component fields to `MembershipBillingRule` for:
  - `tow_hookup_fee_override`
  - `tow_rate_per_1000ft_override`
  - `glider_rental_rate_per_hour_override`
  - `instruction_flat_fee_per_flight`
  - `charge_instruction_per_instructed_flight`
- Added `billing_pricing_mode` in `SiteConfiguration` to separate discount mode from matrix mode behavior.
- Added `instruction_fee_actual` snapshot on `Flight` and integrated instruction fee into flight/member totals and finance finalization lock-in.

### Per-glider junior exception support
Implemented status + glider override rules for rental pricing:

- Added `MembershipGliderRentalRule` for explicit status+glider hourly rental overrides.
- Added precedence order in matrix mode:
  1. status+glider override
  2. status-wide rental override
  3. base glider rental rate

This enables policies such as “junior members pay $0.00/hr on selected gliders” while preserving paid rates on other gliders.

### Minimum billable rental floor
Implemented configurable minimum billable rental duration:

- Added `minimum_billable_rental_minutes` to `SiteConfiguration`.
- Rental computation now bills by `max(actual_duration, minimum_floor)`.
- Example supported: 10-minute flight billed as 20 minutes when floor is set to 20.

### Admin UX enhancements
Updated admin help text to include concrete configuration examples so webmasters can configure matrix mode correctly on first setup:

- Matrix mode + 20-minute floor guidance
- status+glider $0.00/hr junior exception guidance

### Database migrations
Added migrations:

- `siteconfig/migrations/0045_membershipbillingrule_charge_instruction_per_instructed_flight_and_more.py`
- `logsheet/migrations/0022_flight_instruction_fee_actual.py`
- `siteconfig/migrations/0046_siteconfiguration_minimum_billable_rental_minutes_and_more.py`

## Files Changed

- `siteconfig/models.py`
- `siteconfig/admin.py`
- `siteconfig/tests/test_siteconfig.py`
- `logsheet/models.py`
- `logsheet/views.py`
- `logsheet/utils/flight_charges.py`
- `logsheet/templates/logsheet/manage_logsheet_finances.html`
- `logsheet/tests/test_towplane_charging.py`
- `logsheet/tests/test_member_charge_views.py`
- `siteconfig/migrations/0044_siteconfiguration_billing_rules_enabled_and_more.py`
- `siteconfig/migrations/0045_membershipbillingrule_charge_instruction_per_instructed_flight_and_more.py`
- `logsheet/migrations/0022_flight_instruction_fee_actual.py`
- `siteconfig/migrations/0046_siteconfiguration_minimum_billable_rental_minutes_and_more.py`

## Validation and Test Coverage

Focused validation suite executed:

- `pytest siteconfig/tests/test_siteconfig.py logsheet/tests/test_towplane_charging.py -q`

Result:

- **59 passed**, 0 failed

Coverage added/updated includes:

- default configuration behavior for new flags/fields
- rule lookup behavior
- inactive rule exclusion
- tow-discount application with rules enabled
- fallback to default discount when no status-specific rule exists
- matrix-mode tow component override behavior
- matrix-mode flat per-flight instruction fee behavior
- 20-minute minimum billable rental floor behavior
- status+glider rental override precedence behavior

## Safety and Backward Compatibility

- Behavior remains unchanged when new feature flags are disabled.
- Existing clubs are not forced into tenant-specific policy assumptions.
- Existing towplane charge schemes continue to work as before.
- Pricing modifiers are explicit and auditable via admin-configured rules.

## Operational Notes

- Policy changes are configuration-driven through Site Configuration and Membership Billing Rule admin.
- This keeps onboarding and policy evolution self-service for future clubs.
- No tenant-name code branching is needed to support different billing policies.

### HH-Style Configuration Recipe (Anonymized Runbook)

Use this when a club wants:

- matrix-mode billing (absolute component rates)
- junior members free rental on exactly two selected gliders
- a 20-minute minimum billable rental duration

1. Enable billing policy mode in Site Configuration
- Go to Admin -> Site Configuration.
- Set `billing_rules_enabled = true`.
- Set `billing_pricing_mode = matrix`.
- Set `minimum_billable_rental_minutes = 20`.
- Save.

2. Create or confirm membership status records
- Ensure statuses (for example: Junior, Full Member, Introductory) already exist in the site configuration membership-status list.
- Confirm status names match exactly what billing rules will reference.

3. Add membership billing rules (status-wide defaults)
- Go to Admin -> Membership Billing Rules.
- Create one active rule per status that needs custom pricing.
- Example starter matrix for Junior:
  - `tow_hookup_fee_override = 15.00`
  - `tow_rate_per_1000ft_override = 8.00`
  - `glider_rental_rate_per_hour_override = 20.00` (status-wide baseline)
  - `charge_instruction_per_instructed_flight = true`
  - `instruction_flat_fee_per_flight = 10.00`
  - `is_active = true`

4. Add two glider-specific free-rental exceptions for Junior
- Go to Admin -> Membership Glider Rental Rules.
- Create two active rows for membership status `Junior` with rental rate `0.00` for the two selected gliders.
- Example:
  - Junior + Glider SGS 1-34 A -> `hourly_rate_override = 0.00`, `is_active = true`
  - Junior + Glider SGS 1-26 B -> `hourly_rate_override = 0.00`, `is_active = true`

5. Verify rule precedence behavior
- Expected precedence in matrix mode:
  1. status+glider override (most specific)
  2. status-wide rental override
  3. base glider rental rate
- Practical check:
  - A Junior flight in one of the two free gliders should bill rental at 0.00/hr.
  - A Junior flight in any other glider should use the Junior status-wide rental hourly rate.

6. Validate 20-minute minimum billing floor
- Enter a short rental flight (for example 10 minutes) and verify billing uses 20 minutes for rental cost.
- Enter a 35-minute rental flight and verify billing uses actual duration (35 minutes).

7. Finalization and audit check
- Open finance management views and confirm instruction fee and rental totals appear as expected.
- Finalize the logsheet and verify `*_actual` snapshots capture final computed values.

## Remaining Work (Next Phase)

1. Add optional UI/report labels showing exact matrix rule provenance per line item (status rule vs status+glider rule).
2. Evaluate whether clubs need full per-status tow tier tables (beyond per-status hookup + per-1000ft rate).
3. Add optional glider-class grouping overrides if a club policy depends on glider category rather than specific glider records.
4. Expand integration tests across the full billing lifecycle and export reconciliation scenarios.

## Lessons Learned

- Multi-tenant billing variability is best handled as a composable policy layer, not as duplicated base-rate schemes.
- Feature flags + neutral defaults are critical to safe rollout in established tenant environments.
- Reusing existing charge infrastructure minimizes risk and accelerates phased delivery.
- Per-glider exception tables are an effective way to support stubborn real-world policy outliers without polluting core rate definitions.
- A minimum billable duration floor closes a common accounting gap and should be explicit configuration, not implicit business logic.

## References

- Tracking issue: https://github.com/pietbarber/Manage2Soar/issues/935
- Club identities intentionally redacted in this document.
