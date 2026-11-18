# Roles and permissions overhaul TODO

This is the implementation worklist for making capability authorization the
default application authorization model. Checkboxes marked `~` are partially
implemented and still require review or endpoint coverage. A checked item is
not a deployment approval unless the release runbook says so.

## Policy decisions

- [ ] Approve the complete built-in role-to-capability mapping in
  `members/role_definitions.py`.
- [ ] Decide mappings for non-canonical roles (`stats_monger`, `duty_officer`,
  `Chief Flight Instructor`, and dynamic operational roles).
- [~] Keep qualification-derived access limited to explicitly opted-in,
  narrowly scoped `can_*` capabilities; approve the final action allowlist.
- [x] Reject kiosk access to membership-application management, including
  list/detail/waitlist POST requests.
- [ ] Decide whether preview audit events need database retention or are
  sufficient as structured application logs; document the retention period.
- [~] Keep role-preview GET requests read-only and deny unsafe preview methods
  outside DEBUG; verify this across all sensitive endpoints.
- [ ] Approve the global-capability versus contextual/ownership policy and
  document it as a required endpoint contract.

## Authorization migration

- [ ] Build a route-level inventory of remaining `is_staff`, role-boolean, and
  literal Group authorization checks.
- [ ] Classify each legacy check as authorization, eligibility, ownership,
  audience, presentation, or synchronization behavior.
- [ ] Migrate sensitive endpoints to explicit capabilities plus contextual
  predicates, preserving response shape and side-effect behavior.
- [ ] Replace literal Group-name authorization checks with stable role keys or
  capabilities.
- [ ] Document every intentional compatibility fallback with an owner and
  removal condition.
- [ ] Define enforcement or repair policy for direct `Member.groups` and
  through-table writes that bypass assignment provenance.

## Automated coverage

- [x] Test qualification expiry and revocation on an already-loaded user.
- [x] Test Django permission-cache behavior after direct and Group grant
  changes.
- [~] Add integration coverage for qualification expiry/revocation at endpoint
  level; ground-instruction GET coverage is now present, with other derived
  actions still outstanding.
- [ ] Exercise role preview across every sensitive GET, POST, HTMX, JSON, and
  admin endpoint.
- [ ] Test direct grants, custom Groups, conflicting role sources, and stale
  legacy flags during migration.
- [~] Assert denied requests have no mutation, email, audit, or queue side
  effects; revoked ground-instruction POST coverage is now present, with other
  sensitive endpoints still outstanding.
- [ ] Consolidate the focused authorization suite and run it consistently on
  PostgreSQL.

## Migration safety and operations

- [~] Verify forward-only, non-destructive behavior for existing migrations and
  reconciliation commands.
- [ ] Test idempotence, interruption, checkpoint resume, and partial failure
  recovery for every repair/reconciliation command.
- [ ] Define the restore-and-corrective-forward-migration procedure for partial
  permission migrations.
- [ ] Verify audit behavior for role deletes, Group cascades, permission
  changes, and role reconciliation.
- [ ] Run clean-install and in-place upgrade tests against disposable
  PostgreSQL databases.
- [ ] Compare sensitive-action results and mailing-list recipients against an
  authorized representative tenant snapshot.

## Documentation

- [ ] Publish the final capability matrix and endpoint policy matrix.
- [ ] Document administrator workflows for roles, capabilities, qualification
  bundles, and preview.
- [x] Document how to identify and repair unresolved legacy Group memberships.
- [x] Add troubleshooting for permission caches, sessions, and role preview.
- [ ] Record approved legacy compatibility exceptions and their sunset plan.

## Performance

- [ ] Profile repeated qualification permission queries and context processors.
- [ ] Profile role-preview permission loading and large member/Group pages.
- [ ] Add query-count coverage for representative authorization paths.
- [ ] Verify/add indexes for qualification expiry, role assignments, Group
  membership joins, and audit-event lookups.
- [ ] Record PostgreSQL query plans and results for a large member population.

## Completion gate

- [ ] No unreviewed application authorization depends on `is_staff`, raw role
  booleans, or literal Group names.
- [ ] Every sensitive endpoint has an approved allow/deny matrix.
- [ ] Compatibility paths are explicit, tested, and documented.
- [ ] Migration repair and rollback procedures have been exercised.
- [ ] Focused PostgreSQL tests, migration checks, and performance checks pass.
