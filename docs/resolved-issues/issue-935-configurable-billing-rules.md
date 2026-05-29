# Issue #935: Configurable Billing Rules for Membership-Based Tow Discounts and Optional Instructor-Time Charges

**Resolution Date**: May 29, 2026  
**Branch**: feature/issue-936-configurable-billing-rules  
**Status**: Phase 1 Complete ✅ (Foundation Delivered)

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
Phase 1 ships schema, admin controls, and tow-discount integration behind feature toggles. Instructor workflow integration is reserved for next phase.

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

## Files Changed in Phase 1

- `siteconfig/models.py`
- `siteconfig/admin.py`
- `siteconfig/tests/test_siteconfig.py`
- `logsheet/models.py`
- `logsheet/tests/test_towplane_charging.py`
- `siteconfig/migrations/0044_siteconfiguration_billing_rules_enabled_and_more.py`

## Validation and Test Coverage

Focused validation suite executed:

- `pytest siteconfig/tests/test_siteconfig.py logsheet/tests/test_towplane_charging.py -q`

Result:

- **52 passed**, 0 failed

Coverage added/updated includes:

- default configuration behavior for new flags/fields
- rule lookup behavior
- inactive rule exclusion
- tow-discount application with rules enabled
- fallback to default discount when no status-specific rule exists

## Safety and Backward Compatibility

- Behavior remains unchanged when new feature flags are disabled.
- Existing clubs are not forced into tenant-specific policy assumptions.
- Existing towplane charge schemes continue to work as before.
- Pricing modifiers are explicit and auditable via admin-configured rules.

## Operational Notes

- Policy changes are configuration-driven through Site Configuration and Membership Billing Rule admin.
- This keeps onboarding and policy evolution self-service for future clubs.
- No tenant-name code branching is needed to support different billing policies.

## Remaining Work (Next Phase)

1. Integrate instructor-time charge workflow from instruction flows using existing charge models.
2. Apply instructor multipliers when instructor-time billing is enabled.
3. Improve treasurer-facing exports/views so adjusted-charge provenance is explicit.
4. Expand integration tests across the full billing lifecycle and reporting surfaces.

## Lessons Learned

- Multi-tenant billing variability is best handled as a composable policy layer, not as duplicated base-rate schemes.
- Feature flags + neutral defaults are critical to safe rollout in established tenant environments.
- Reusing existing charge infrastructure minimizes risk and accelerates phased delivery.

## References

- Tracking issue: https://github.com/pietbarber/Manage2Soar/issues/935
- Club identities intentionally redacted in this document.
