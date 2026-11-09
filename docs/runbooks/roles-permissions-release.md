# Roles and Permissions Release Runbook

Use this runbook for the authorization migration release. It intentionally
covers backend behavior and migration safety; new role-management UX is a
separate workstream.

## Pre-release checks

Run from the application checkout with the deployment environment loaded:

```bash
./.venv/bin/python manage.py check --settings=manage2soar.settings
./.venv/bin/python manage.py check --settings=manage2soar.settings_single_host
./.venv/bin/python manage.py makemigrations --check --dry-run \
  --settings=manage2soar.settings
./.venv/bin/python manage.py makemigrations --check --dry-run \
  --settings=manage2soar.settings_single_host
npm ci --no-audit --no-fund
npm run vendor
```

Run the focused authorization suites and record the results:

```bash
./.venv/bin/pytest -q members/tests/test_authorization.py
./.venv/bin/pytest -q members/tests/test_role_definitions.py
./.venv/bin/pytest -q members/tests/test_role_preview.py
./.venv/bin/pytest -q cms/tests/test_editing_permissions.py
./.venv/bin/pytest -q logsheet/tests/test_permissions.py
./.venv/bin/pytest -q members/tests/test_membership_application_access_matrix.py
./.venv/bin/pytest -q members/tests/test_capability_registry_migration.py
./.venv/bin/pytest -q members/tests/test_role_assignments.py
./.venv/bin/pytest -q members/tests/test_role_assignment_service.py
./.venv/bin/pytest -q members/tests/test_role_assignment_audit.py
./.venv/bin/pytest -q members/tests/test_group_permissions_migration.py
./.venv/bin/pytest -q siteconfig/tests/test_mailing_list.py
./.venv/bin/pytest -q members/tests/test_stats_monger_permissions.py
./.venv/bin/pytest -q members/tests/test_admin_password_change_permissions.py
./.venv/bin/pytest -q knowledgetest/tests/test_written_test_capability_migration.py
./.venv/bin/pytest -q knowledgetest/tests/test_written_test_permissions.py
./.venv/bin/pytest -q duty_roster/tests/test_permissions.py duty_roster/tests/test_duty_swap.py
./.venv/bin/pytest -q members/tests/test_admin_member_import_permissions.py
./.venv/bin/pytest -q members/tests/test_context_processors.py
```

These tests create and migrate **disposable test databases**; never run the
in-place test against a live tenant database. A clean pytest database exercises
the complete migration graph; the migration tests additionally exercise
forward upgrades with existing Groups, permissions, and memberships. Record the
PostgreSQL version and the test results in the PR. A local `makemigrations
--check` may report "No changes detected" even if it could not connect to
PostgreSQL to verify migration history; report that warning rather than
claiming database validation succeeded.

For the PR review, identify the access changes in
[`docs/roles-and-permissions-authorization-inventory.md`](../roles-and-permissions-authorization-inventory.md#review-scope-for-this-branch),
especially the intentional kiosk restriction on application-management routes.
Clean-install tests do **not** establish existing-tenant recipient parity: use
an authorized copy of representative tenant data for that comparison before
deployment. Do not copy or migrate a live database as a substitute for a backup.

## Read-only parity snapshots

Use an authorized, disposable copy of representative tenant data. Capture the
baseline with the pre-branch revision (or a checkout containing the parity
tool and pre-branch models) so it can read the old schema; use the
`--legacy-compatible` projection. After applying the branch migrations, use a
full capture. The legacy projection compares stable member, Group/permission,
and recipient state while the full capture reports new role metadata and
assignment state separately.

```bash
./.venv/bin/python manage.py capture_authorization_parity \
  /tmp/roles-before.json --legacy-compatible \
  --settings=manage2soar.settings
# Apply the backup and migration steps below to the disposable copy.
./.venv/bin/python manage.py capture_authorization_parity \
  /tmp/roles-after.json \
  --settings=manage2soar.settings
./.venv/bin/python manage.py compare_authorization_parity \
  /tmp/roles-before.json /tmp/roles-after.json \
  --settings=manage2soar.settings
```

The snapshot includes role metadata and capabilities, member role flags and
effective permissions, assignment provenance, and mailing-list criteria and
recipient fingerprints. It performs no database writes. Recipient emails are
hashed by default; use `--include-emails` only when the output is being handled
as confidential data. A nonzero comparison means stable legacy state differs;
review each difference rather than assuming it is a regression. Branch-only
role and assignment additions are intentionally not treated as legacy parity
failures.

## Database rollout

1. Take a PostgreSQL backup and record its restore location.
2. Run migrations during the maintenance window:

   ```bash
   ./manage.py migrate --settings=manage2soar.settings
   ```

3. Confirm `members.0052_sync_registered_role_capabilities`,
   `members.0053_source_aware_stats_monger_grants`,
   `members.0054_reconcile_stats_monger_direct_grants`, and
   `members.0055_alter_member_options`, `members.0056_member_manager_import_permission`,
   `knowledgetest.0008_create_and_grant_written_test_capabilities`, and
   `instructors.0008_groundinstruction_manage_permission` completed.
4. Run the role registry parity test against the migrated database.
5. Compare role permissions and sensitive-action allow/deny results with the
   pre-release baseline before enabling traffic.

The registry migration only adds missing capability grants; it does not revoke
stale Group permissions removed from a later runtime registry. Migration `0053`
adds a source-aware stats-monger role assignment and `0054` is non-destructive:
both preserve unprovenanced direct export grants, including possible legacy
access. On an authorized tenant copy, run
`manage.py report_stats_export_direct_grants` (add `--include-member-ids` only
for confidential, tenant-specific review). Obtain an approved allowlist and
backup before any explicit later cleanup; the flag alone proves no ownership.
If a tenant already ran the earlier destructive `0053`/`0054` code, this
revision cannot reconstruct removed direct grants; review a pre-migration
backup and plan a tenant-approved corrective grant rather than assuming a
rerun or migration rollback restores them.
Migration `0008` explicitly creates the
written-test permissions before granting them. Historical migrations remain
replayable, and migration `0052` contains a frozen grant snapshot so later
runtime registry edits cannot change historical replay.

## Rollback and recovery

- Roll back application code only if the database migration is compatible with
  the previous application version.
- Do not reverse `0052` as an emergency access fix; it has no destructive
  reverse operation. Restore the application version, investigate the parity
  report, and apply a corrective forward migration if needed.
- If data repair is required, stop writes, restore the backup to a separate
  PostgreSQL database, compare role/group memberships, and obtain maintainer
  approval before production repair.

## Release blockers

Do not release until the following are explicitly resolved or accepted by the
maintainer:

- exact role and qualification capability mappings;
- unresolved legacy staff-policy contradictions;
- preview audit retention and GET-side-effect policy;
- review of stats-export access changes caused by the security-first cleanup of
  unprovenanced historical direct grants;
- clean-install, in-place, and recipient-parity validation results.
