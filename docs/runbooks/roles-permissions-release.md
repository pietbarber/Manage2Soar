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
./.venv/bin/pytest -q members/tests/test_group_permissions_migration.py
./.venv/bin/pytest -q siteconfig/tests/test_mailing_list.py
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

## Database rollout

1. Take a PostgreSQL backup and record its restore location.
2. Run migrations during the maintenance window:

   ```bash
   ./manage.py migrate --settings=manage2soar.settings
   ```

3. Confirm `members.0052_sync_registered_role_capabilities` completed.
4. Run the role registry parity test against the migrated database.
5. Compare role permissions and sensitive-action allow/deny results with the
   pre-release baseline before enabling traffic.

The registry migration only adds missing capability grants. Historical
migrations remain replayable, and migration `0052` contains a frozen grant
snapshot so later runtime registry edits cannot change historical replay.

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
- clean-install, in-place, and recipient-parity validation results.
