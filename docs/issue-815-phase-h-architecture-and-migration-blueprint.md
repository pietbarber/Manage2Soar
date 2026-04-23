# Issue #815 Phase H: Architecture Deliverables and Migration Blueprint

## Scope

Phase H is documentation-only for this cycle. It captures:

1. Architecture design for dynamic duty roles and compatibility invariants.
2. Migration blueprint and data mapping specification.
3. Prototype proof notes showing dual-read behavior via `RoleResolutionService`.

This phase does not include a full production migration or complete UI replacement.

## Compatibility Invariants

These are non-negotiable guardrails for rollout safety:

1. Legacy clubs (no dynamic feature flag enabled) must keep current behavior.
2. Existing role title terminology from site configuration remains authoritative for legacy-mapped roles.
3. Existing fixed-role flows (calendar, swap, volunteer, scheduler defaults) continue to function when dynamic roles are disabled.
4. Dynamic-role changes are feature-flag controlled and reversible.
5. Backfill and synchronization logic remains idempotent.

## Delivered Architecture (A-G Context)

The following architecture pieces are already implemented in this branch:

1. Dynamic role registry models:
- `DutyRoleDefinition`
- `DutyQualificationRequirement`
- `MemberDutyQualification`

2. Compatibility and resolution service:
- `RoleResolutionService` provides:
  - enabled role discovery
  - label resolution with legacy terminology precedence
  - eligibility checks with dynamic requirement support
  - legacy fallback behavior

3. Assignment storage foundation:
- `DutyAssignmentRole` normalized role rows
- dual-read behavior from normalized rows and legacy assignment fields
- backfill command support for normalized rows

4. Feature-flagged behavior:
- site configuration flag `enable_dynamic_duty_roles`
- legacy behavior remains default when flag is off

## Migration Blueprint

## Stage 0: Pre-Migration Safety

1. Confirm backups and rollback procedure.
2. Confirm feature flags default to legacy-safe mode.
3. Confirm migration scripts and commands are idempotent in staging.

## Stage 1: Schema Introduction

1. Add dynamic role/qualification registry tables.
2. Add normalized assignment role table.
3. Add swap-request dynamic metadata fields and consistency constraints.
4. Keep all existing legacy columns in place.

## Stage 2: Dual-Write / Dual-Read Stabilization

1. Continue writing legacy assignment columns for legacy-mapped roles.
2. Maintain normalized rows for legacy and dynamic keys.
3. Read paths use compatibility-first resolution (`RoleResolutionService`).

## Stage 3: Backfill and Validation

1. Run normalized-row backfill command for historical assignments.
2. Validate parity against legacy views and swap behavior.
3. Verify idempotence by repeating backfill in staging.

## Stage 4: Feature-Gated Expansion

1. Enable dynamic registry read-only for selected club configuration.
2. Enable dynamic eligibility checks.
3. Enable dynamic assignment writing flows.
4. Maintain rollback path by disabling flags.

## Stage 5: Optional Future Cleanup (Out of This Cycle)

1. Evaluate deprecation strategy for legacy member role booleans.
2. Evaluate deprecation strategy for fixed-role-only assumptions in older views/forms.
3. Remove/retain legacy columns only after prolonged parity evidence.

## Data Mapping Specification

| Legacy Concept | New/Normalized Target | Mapping Rule |
| --- | --- | --- |
| Fixed role keys (`instructor`, `towpilot`, `duty_officer`, `assistant_duty_officer`, etc.) | `DutyRoleDefinition.key` and `DutyAssignmentRole.role_key` | Preserve legacy-compatible keys for mapped roles; allow non-legacy dynamic keys for new roles |
| Legacy role title terminology | `RoleResolutionService.get_role_label()` | If dynamic role maps to legacy key, site terminology takes precedence |
| Member boolean role flags | `DutyQualificationRequirement` (legacy flag type) and/or fallback checks | Use dynamic requirements when configured; fallback to legacy booleans when no dynamic config |
| Duty assignment fixed columns | `DutyAssignmentRole` rows | Keep fixed columns for compatibility and sync normalized rows in parallel |
| Swap role code (`DO`, `ADO`, `INSTRUCTOR`, `TOW`) | Dynamic swap metadata (`dynamic_role_key`, `dynamic_role_label`) | Use static code for legacy paths; use dynamic metadata for non-legacy dynamic roles |
| Historical assignment records | Backfilled `DutyAssignmentRole` rows | Backfill from legacy assignment fields with idempotent command |

## Prototype Proof: Dual-Read Behavior

The prototype objective for Phase H is already met by the existing service + storage pattern:

1. Role enablement resolves dynamically when configured, otherwise from legacy schedule flags.
2. Role labels resolve through site terminology for legacy-mapped keys.
3. Eligibility resolves from dynamic requirements when enabled, with legacy fallback.
4. Assignment retrieval supports normalized rows while retaining legacy field compatibility.

Representative verification targets:

1. `duty_roster/tests/test_role_resolution_service.py`
2. `duty_roster/tests/test_propose_roster_dynamic_roles.py`
3. `duty_roster/tests/test_assignment_role_sync.py`
4. `duty_roster/tests/test_duty_swap.py`

## Validation Checklist for This Documentation Phase

1. Architecture invariants documented and explicit.
2. Migration stages documented with rollback awareness.
3. Data mapping documented from legacy to normalized/dynamic structures.
4. Prototype proof documented with concrete test references.

## Out-of-Scope for Phase H

1. Full deprecation/removal of legacy schema fields.
2. Full UI redesign for dynamic-role management across all admin/member surfaces.
3. Full production migration cutover plan execution.
