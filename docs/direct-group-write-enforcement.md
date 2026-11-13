# Direct `Member.groups` write enforcement

## Scope and conclusion

This is a read-only inventory of every source-tree path found that writes the
`Member.groups` relation (Django's inherited `AbstractUser.groups` M2M). The
relation has Django's automatically generated `members_member_groups` through
table; there is no
custom `through=` model for it. `MemberRoleAssignment` is a separate
provenance table, not the M2M through table.

The current code already has the right intended boundary: role changes should
go through `set_manual_role()` or legacy/status reconciliation, while
unattributed memberships must not be silently removed. Enforcement should be
introduced as a staged migration to that boundary, not as a blanket signal
that deletes or rewrites old memberships.

Search coverage included Python production code, tests, migrations, fixtures,
admin/model forms, management commands, and the generated graph inventory.
There are no `Member.groups.set()` or `.clear()` calls in the repository. No
raw SQL writes to `members_member_groups` were found.

## Inventory

Line numbers refer to the current checkout. “Direct” means an actual
`member.groups.add/remove` (including `db_manager(...).add/remove`), not a
read, declaration, or an unrelated `Group.permissions` write.

### Legitimate automatic synchronization

* **`members/models.py:500-556` — `Member._sync_groups()`**. It creates and
  removes `MemberRoleAssignment(source="legacy")` rows from the legacy role
  flags and then adds all groups having any assignment. At **548** it removes a
  group only after the stale legacy assignment was deleted and no other
  assignment remains; at **552** it adds the union of all assignment-backed
  groups. This is intentionally additive and preserves unprovenanced/direct
  memberships.
* **`members/models.py:632-638`** schedules that synchronization after the
  member save commits. The `on_commit` boundary avoids reconciling rolled-back
  flag changes and `_sync_groups()` locks/re-reads the member.
### Manual assignment / admin path

* **`members/services/role_assignments.py:54,63,65` —
  `set_manual_role()`**. These are the actual effective-membership writes for
  a manual provenance source: add on grant, retain on revoke if another source
  exists, and remove only when this source was deleted and no source remains.
  The surrounding transaction and `select_for_update()` serialize service
  writers. Although these are direct M2M operations, they are legitimate
  internal writes and must be explicitly exempted from any guard.

* **`members/admin.py:549-563,701-710`** exposes `groups` on the Member admin
  form and maps canonical role names to legacy flags.
* **`members/admin.py:795-809`** snapshots the pre-edit group IDs.
* **`members/admin.py:896-943` — `MemberAdmin.save_related()`** removes
  `groups` from `cleaned_data` before `super().save_related()`, so Django's
  ordinary ModelForm M2M replacement does not execute. It computes the desired
  selection and routes additions/removals to `set_manual_role()` at **923,
  935, and 937-942**, with `request.user` attribution for grants. Canonical
  groups whose legacy flag is still true remain legacy-owned; leaving a
  canonical group selected while disabling its flag is converted to an
  explicit manual grant before deferred sync.
* **`members/admin.py:805-806,913-916`** are reads used to calculate the
  delta, not writes. This path is the supported manual assignment interface;
  future enforcement must preserve its actor (`request.user`) and source key.

### Migration / historical state

* **`members/migrations/0001_initial.py:297-304`** declares the inherited
  `groups` M2M field and its default auth through table; it does not populate
  member memberships.
* **`members/migrations/0036_member_role_assignments.py:15-33`** reads every
  existing membership and creates provenance. Canonical groups with their
  matching legacy boolean become `legacy`; every other pre-existing membership
  becomes `manual:migration`. It does not write the M2M relation. This is the
  compatibility anchor: existing memberships must survive enforcement and
  receive a durable historical provenance row.
* **`members/migrations/0034_role_metadata.py:47-121`** reads/validates the
  six canonical groups and creates metadata. It does not assign members.
* **`members/migrations/0021_setup_all_group_permissions.py:412-483`** and
  **`members/migrations/0025_backfill_group_permissions.py:26-92`** create
  groups and write `Group.permissions`, not `Member.groups`; they must not be
  mistaken for prohibited member assignment.
* **`loaddata/groups_and_permissions.json:1-116` and onward** contains
  `auth.group` and `auth.permission` objects only. No `members.member` object
  has a `groups` field in the repository fixtures. Thus fixture loading does
  not currently provide a member-group write path, but future member fixtures
  should be classified as historical/import input and run under an explicit
  import context.

### Test setup, fixtures, and regression coverage

These raw writes are test setup or deliberate simulation of legacy/direct data;
they should eventually use an explicit factory/context helper where the test
is intended to model a legitimate source. They are not production callers.

* **`members/tests/test_models.py:44,86`** creates direct/manual groups to
  verify legacy sync preserves unrelated and unprovenanced memberships.
* **`members/tests/test_role_assignments.py:32-33`** seeds existing groups
  before role-assignment backfill assertions.
* **`members/tests/test_permission_sources.py:77,118`** seeds group-based
  permission sources.
* **`members/tests/test_group_admin.py:215,261,271,286,296,433,472`** seeds
  memberships and simulates the pre-service admin delta. The real-form test at
  **307-367** specifically verifies Django `save_m2m()` does *not* write
  `groups` and that the service receives the actor.
* **`members/tests/test_membership_applications.py:978`** seeds the Member
  Managers group for an application-access scenario.
* **`members/tests/test_membership_application_access_matrix.py:65`** seeds
  access-matrix group membership.
* **`members/tests/test_authorization.py:76,203,205`** seeds and removes a
  group for authorization tests.
* **`members/tests/test_profile_schema.py:119`** seeds the Member Managers
  role.
* **`members/tests/test_redaction.py:48`** seeds an exemption group.
* **`members/tests/test_member_tags.py:60`** seeds a group, then snapshots
  membership to prove tag operations do not alter it.
* **`members/tests/test_role_assignment_service.py:49,78,146`** deliberately
  removes/adds direct memberships to test preservation of unrelated,
  unprovenanced, and other-source memberships.
* **`siteconfig/tests/test_mailing_list.py:382,412,454,461,467,494`** seeds
  mailing-list-eligible role memberships.
* **`logsheet/tests/test_maintenance_deadline_update.py:76`** seeds Webmaster
  access.
* **`e2e_tests/e2e/test_roster_slot_editing.py:33`** and
  **`e2e_tests/e2e/test_ortools_scheduler_integration.py:56`** seed the
  Rostermeister role.

All other `groups` matches found were reads, local Python grouping, queryset
filters, or writes to `Group.permissions`/unrelated M2Ms. In particular,
`knowledgetest`'s `through_defaults` calls are for its question/template M2M,
not `Member.groups`.

### Unexplained / unsafe direct production writes

The supported service and legacy synchronization paths now mark their M2M
writes as internal. An audit-only `m2m_changed` tripwire logs external
`Member.groups` add/remove/clear/set operations with member, group, actor, and
database context; it does not reject or repair them yet. Historical migrations
`0046` and `0047` also contain intentional direct writes and should be treated
as migration-owned exceptions. The repository's own service docstring
(`members/services/role_assignments.py:3-5`) labels arbitrary direct writes
unsupported and requires unexplained memberships to remain effective until an
operator classifies them.

## Enforcement policy

### One authoritative write API

Adopt a small role-assignment API with an explicit context object:

```text
RoleWriteContext(actor, source, source_key, operation, reason, import_id)
```

Allowed sources are at least `manual`, `legacy`, `status`, `migration`, and
`fixture/import`; actor is nullable only for system/migration sources. The API
must perform provenance upsert/deletion and effective M2M reconciliation in one
`transaction.atomic()` block, lock the member row, and use set-union semantics:

For assignment-backed memberships, the steady-state rule is:

```text
desired(member, group) = exists(MemberRoleAssignment for member/group)
```

Existing unexplained M2M edges are a compatibility exception and remain
effective until an operator classifies them; reconciliation must not interpret
absence of an assignment as permission to delete such an edge.

`set_manual_role()` should become the manual adapter; `_sync_groups()` should
become the legacy adapter. Bulk callers need a batch API that groups changes by
member, locks members in sorted PK order (preventing deadlocks), applies all
provenance changes, and reconciles each effective membership once. It must not
loop through an unbounded sequence of per-row signals.

### Reject versus reconcile

**Recommended default: reject new unattributed writes, but reconcile rather than
delete any already-existing membership.** A rejected write should raise a
dedicated exception (or a clear validation error at an admin/form boundary)
before changing either the M2M or provenance. This makes accidental privilege
grants visible and prevents a signal from guessing an actor or source.

For compatibility, first run in audit mode: log a structured event containing
member ID, group IDs, operation, database alias, request/actor if available,
and call-site/context; increment a metric; do not mutate. Then reject after
all known callers are migrated. A narrowly scoped `reconcile` mode is required
for legacy imports, fixtures, and historical rows: preserve the M2M edge and
create `manual:migration` (or the declared import source) provenance, never
remove it merely because its cause is unknown. A repair command can report
unexplained rows and require an operator-supplied source/actor; it should not
silently infer ownership.

### Signals and Django limitations

`m2m_changed` can observe `pre_add`, `post_add`, `pre_remove`, `post_remove`,
`pre_clear`, and `post_clear` for Django's default through model, and `pk_set`
is available for add/remove. It has important limits:

* It does not receive an actor, request, source, or reason. A thread-local
  actor is fragile for Celery, management commands, async work, tests, and
  nested calls, so context must be passed explicitly by the API and only used
  as an optional audit fallback.
* `bulk_create()` on the through model and raw SQL bypass model-level M2M
  signals. Database writes from another process cannot be reliably rejected by
  a Django signal.
* `clear()` gives a set of rows but no per-membership reason; `set()` is
  implemented as clear/add (with `clear=False` optimization), so a signal sees
  multiple low-level events, not the caller's intended replacement.
* Signals fire around the M2M write, while provenance must be atomic with it.
  Writing provenance from a signal can recurse through the service's own M2M
  calls, and disabling the receiver globally is unsafe under concurrency.
* `pre_*` rejection can prevent the through write, but it cannot reliably
  repair a bypass or attach attribution. `post_*` reconciliation can leave a
  short-lived M2M/provenance mismatch and cannot undo a committed external
  write safely.

Therefore use `m2m_changed` only as an audit/compatibility tripwire (with a
`ContextVar`/explicit re-entrancy token marking internal API operations), not
as the sole security boundary. Enforce at the application API/admin boundary,
and add database-level protection where the deployment permits it (restricted
DB role for the through table or an SQL trigger/outbox design). Internal
reconciliation calls must carry an origin token and the receiver must return
without attempting another reconciliation; never call `set()` from a signal.

### Concurrency and deletion semantics

Lock the member before reading assignments, lock or consistently order group
work, and reconcile from the current database state—not a stale in-memory
`Member`. Keep all provenance and through-row changes in the same transaction.
Do not remove an effective group until the last provenance source is removed.
An unexplained legacy edge is itself a preservation source until an operator
explicitly resolves it. For high-volume bulk jobs, use sorted member locks,
bounded batches, idempotent `bulk_create(..., ignore_conflicts=True)` for
provenance, and a final locked reconciliation pass.

## Staged implementation plan

1. **Baseline (no behavior change).** Add metrics/audit logging for direct
   M2M events and a management report of edges lacking provenance. Confirm the
   `0036` backfill is complete and idempotent in every supported database.
2. **Centralize context.** Define the context/source vocabulary and public
   single-member and bulk APIs. Refactor `_sync_groups`, `set_manual_role`, and
   `MemberAdmin.save_related` to use them while retaining their current
   additive/preservation behavior and actor attribution.
3. **Migrate callers/tests.** Replace production callers (none currently
   unexplained) and add test helpers such as `grant_group(..., context=...)`.
   Keep a few raw writes only in tests explicitly marked as historical/direct
   compatibility cases.
4. **Audit mode.** Install an `m2m_changed` receiver with internal-origin
   bypass, metrics, and structured logs. Verify no recursion and enumerate all
   bypasses (through `bulk_create`, SQL, fixtures, migrations).
5. **Reject mode for application writes.** Reject uncontextualized add/remove/
   set/clear at the supported API/form boundary. Keep migration/import
   contexts explicitly allowed and reconcile unknown historical edges rather
   than deleting them.
6. **Database defense and operations.** Restrict direct DB access or add a
   trigger/outbox guard where appropriate; document the migration/fixture
   command contract, alert on unexplained edges, and provide an operator repair
   workflow.

## Required tests

* **Inventory guard:** repository/static test fails on new production
  `Member.groups.add/remove/set/clear`, through-table `bulk_create`, or raw
  `members_member_groups` SQL unless explicitly allow-listed with a context.
* **API attribution:** manual grant/revoke records source, source key, actor,
  timestamps, and reason; repeated grants are idempotent and retain the first
  actor as currently tested in `test_role_assignment_service.py:58-71`.
* **Source union:** revoking one of multiple manual, legacy, status, migration,
  or import sources keeps the group; last known source removal removes it;
  unexplained direct membership remains.
* **Legacy compatibility:** flag save creates/removes only its legacy source,
  preserves unrelated groups, and a selected canonical group is converted to
  manual when its flag is disabled (existing admin tests cover this behavior).
* **Admin boundary:** real ModelForm `save_m2m()` never writes `groups`; the
  admin service receives the request actor; add/remove/set/clear-like form
  replacements preserve other provenance and cannot bypass assignability.
* **Signal behavior:** `pre/post_add`, `pre/post_remove`, and `pre/post_clear`
  audit external operations; internal API operations produce no recursive
  second write; rejection rolls back both relation and provenance.
* **Bulk/concurrency:** concurrent grants/revokes for the same member/group,
  different source keys, and concurrent legacy save serialize correctly; bulk
  changes lock members in sorted order, are idempotent, and do not deadlock.
* **Bypasses:** direct through-model `bulk_create`, raw SQL (where test DB
  permits), `loaddata`, and migration execution are either explicitly blocked
  at the database boundary or produce a detectable audit/reconciliation result.
* **Historical migration:** run `0036` against memberships for canonical,
  manual, duplicate-source, and unknown groups; assert all edges survive and
  provenance is correct, including reverse/no-op behavior.
* **Fixtures/imports:** load a fixture containing member memberships under an
  explicit import context and assert attribution; loading without context is
  rejected in application mode, never silently dropped.
