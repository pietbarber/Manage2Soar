# Membership-status → role reconciliation policy

**Status:** approved implementation policy. The schema and safe per-member
reconciler are implemented; no initial status-to-role mappings are seeded.

## 1. Scope and terminology

“Role” means a Django `auth.Group` membership. “Assignment” means a
`MemberRoleAssignment` provenance row for that membership. Reconciliation
adds or removes only the `status` provenance owned by this policy; it must not
replace the member’s effective group set wholesale.

This proposal addresses the currently unused `MemberRoleAssignment.source`
choice of `status`. It does not infer which membership status grants which
role. No such mapping is present in the repository.

## 2. Current behavior (evidenced)

### Membership status

* `siteconfig.MembershipStatus` has a unique, user-visible `name`, an immutable
  normalized `key`, `is_active`, flight eligibility flags, ordering, and
  description. Explicit status-role mappings are stored separately.
* `Member.membership_status` is a nullable/blank `CharField` that stores the
  status name, not a foreign key. Form choices are read dynamically from all
  `MembershipStatus` rows, ordered by `sort_order` and name.
* `Member.is_active_member()` is true only when the stored name is in
  `MembershipStatus.get_active_statuses()`. `Member.save()` derives Django
  `is_active` from that result (except for superusers) and schedules
  reconciliation after a committed status change. Changing a status row’s
  `is_active` also schedules affected members.
* Deleting a status is blocked when any member stores its name. Renaming is
  allowed by the model/admin and changes the status name, while existing
  members still contain the old string; this is a consistency hazard.
* Membership-status administration is available to superusers, Webmasters,
  and Member Managers. Status-role mappings are restricted to superusers and
  Webmasters; the `reconcile_status_roles` command provides dry-run/apply
  reporting.

### Existing group synchronization

* `Member._sync_groups()` owns only six boolean legacy fields and six exact
  group names: `Rostermeisters/rostermeister`, `Instructor Admins/instructor`,
  `Member Managers/member_manager`, `Webmasters/webmaster`, `Secretary`, and
  `Treasurer`. It creates missing groups, creates `legacy` assignments, and
  removes stale `legacy` assignments.
* It deliberately does not replace groups. It re-adds groups represented by
  any `MemberRoleAssignment` and removes a group only when no assignment
  provenance remains. Thus manual, status, legacy, and any future sources can
  coexist.
* `Member.save()` schedules `_sync_groups()` with `transaction.on_commit()`.
  `_sync_groups()` locks and re-reads the member row before reconciling. The
  existing manual-role service uses the same member-row lock and a transaction.
* The assignment model allows sources `manual`, `status`, and `legacy`; its
  uniqueness is `(member, group, source, source_key)`. `source_key` is a
  required string. The status-role service writes only this provenance and
  never rewrites other sources.
* Manual role changes go through `set_manual_role()`. The public service requires
  an authenticated, active, canonical superuser actor, so programmatic callers
  share the admin boundary; trusted repair paths must use the private internal
  helper. A manual revoke removes only the requested manual source. It leaves
  other provenance, including legacy/status rows, intact; it also leaves an
  untracked direct group membership intact. New manual grants to
  metadata-marked non-assignable roles are rejected, while existing grants
  remain preservable.
* The member admin routes group selection through `set_manual_role()`. It
  preserves enabled legacy-flag assignments, converts a deliberately retained
  canonical group to `manual:admin` when its flag is disabled, and removes
  `manual:admin` and migration provenance only for groups deselected there.

### Current groups and historical data

* Migration `members.0021` creates the six canonical groups above and seeds
  their canonical permissions. Secretary and Treasurer intentionally have no
  model permissions; some access is enforced by member flags.
* `members.0034` adds immutable, unique `RoleMetadata.key` values for those
  six groups (`rostermeisters`, `instructor_admins`, `member_managers`,
  `webmasters`, `secretary`, `treasurer`). The metadata row is one-to-one with
  a group; the key is immutable, and protected canonical metadata cannot be
  deleted through the guarded group admin.
* `members.0036` backfilled every pre-existing group membership. Recognizable
  canonical memberships with their corresponding true flag became
  `legacy:<boolean-field>`; all other memberships became
  `manual:migration`. The migration preserves group memberships and group
  permissions.
* Groups without `RoleMetadata` remain valid legacy groups and are shown as
  `untracked` when permission sources are reported. Direct M2M membership with
  no assignment row is intentionally not “explained” or removed.

## 3. Approved policy

### 3.1 Explicit mapping, not name convention

Introduce an explicit status-to-role mapping managed as configuration. The
recommended conceptual row is:

| Field | Rule |
| --- | --- |
| membership status | FK to `MembershipStatus`; immutable identity, not display name |
| role | FK to `Group` with required `RoleMetadata` |
| enabled | Allows a mapping to be retired without deleting history |
| audit fields | created/updated timestamps and actor if the admin workflow supports it |

The mapping must be unique per `(membership status, role)` and must reject
ambiguous duplicate active rows. A role is granted only by an enabled mapping;
`is_active`, `can_be_pilot`, and `can_be_passenger` do **not** implicitly grant
roles. In particular, “active” is not a role mapping.

**Approved default:** mappings may target only groups with `RoleMetadata`. The
initial mapping table is intentionally empty; each status-to-role pair must be
configured explicitly by an authorized administrator.

### 3.2 Stable identity and `source_key`

The current status `name` is not safe as provenance: it is user-editable and
is already the value stored on `Member`. Add an immutable, unique status key
(or use an immutable status identifier behind a documented canonical encoding)
before enabling status assignments. Display-name edits must never change it.

Use these exact provenance rules:

* `source = "status"` means the row is owned solely by the active mapping
  policy.
* `source_key = "<status-key>:<role-key>"`, where both components are stable,
  normalized keys, not names or primary keys whose meaning is undocumented.
  The role component is `RoleMetadata.key`; the status component is the new
  immutable status key. Keep the encoding versioned if keys can contain `:`;
  otherwise validate that delimiter out. Example shape only:
  `status-full-member:instructor_admins`. This is a format proposal, not an
  assertion that “Full Member” maps to Instructor Admins.
* Mapping rows and assignment rows must retain their old source key after a
  display rename. A rename changes labels only.
* The status source is per mapping, not one broad `status:<status>` grant for
  all roles. That permits one role mapping to be retired without revoking
  unrelated status-derived roles.

**Approved default:** use a normalized immutable slug generated during the
identity backfill. Display-name edits preserve that key; keys cannot contain
`:`, and the migration stops on collisions rather than guessing.

### 3.3 Preservation and removal rules

For a member’s current status, desired status rows are the enabled mapping
rows for that status. Reconciliation is set-based for `status` rows only:

1. Create missing desired `status` assignment rows and ensure the group is in
   the M2M table.
2. Remove stale `status` assignment rows owned by mappings no longer desired.
3. After each removal, remove the group from M2M only if **no** assignment row
   of any source remains.
4. Never delete or rewrite `manual`, `legacy`, or any future source.
5. Never remove a direct group membership that has no assignment row. Report it
   as unexplained instead.
6. Never infer ownership from the group name, role label, current permissions,
   or the member’s boolean flags.

This preserves both intentional manual exceptions and historical/unexplained
access. It also means a stale unexplained group can remain effective; the
reporting and admin UI must make that visible rather than silently “fixing” it.

### 3.4 Inactive statuses

Approved default: an inactive status has no desired `status` assignments.
On transition to inactive, remove only status-source rows; retain manual,
legacy, and unexplained memberships. On reactivation, recompute from current
enabled mappings and recreate missing status rows. This is consistent with
the existing use of `is_active` for member access, while avoiding destructive
loss of separately owned role grants.

Configured mappings remain available for reactivation, but inactivity revokes
only status-owned rows.

Status changes must also continue to follow existing `Member.save()` behavior:
inactive members become `is_active=False`, so a role assignment may exist as
provenance but not be effective until the member is active.

### 3.5 Rename and deletion handling

* Rename: preserve the immutable status key and mapping FKs; update labels only.
  Reconciliation must continue to find members during a compatibility period
  even if their legacy `membership_status` string is old. The migration should
  repair those rows before the new reconciler becomes authoritative.
* Deletion: retain the existing guard against deleting a status used by a
  member. Also block deletion while mapping or status assignment history
  references it, unless a separately approved archival policy exists. Preferred
  operation is deactivate/retire, not delete.
* A role metadata key is already immutable. Renaming a Group display name must
  not alter its role key or status assignment provenance. Deleting a group is
  allowed only under the existing protected/reference guards and only after
  its mapping is disabled/retired; cascading assignment rows must be included
  in the audit report.
* Never bulk-rewrite historical `source_key` values during a rename. If a key
  collision or missing identity is found, stop that row and report it.

## 4. Locking, concurrency, and transaction boundary

Implement reconciliation inside `transaction.atomic(using=member_db)` and
lock the member with `select_for_update()`, then re-read its current status and
flags. Use a deterministic lock order: member first, status/mapping rows next,
then affected groups/assignment rows. The operation must use the same database
alias as the member and existing role services.

The member-row lock serializes status reconciliation with `_sync_groups()` and
`set_manual_role()`. Use `get_or_create` under the existing unique constraint;
retry an integrity race if the database can observe concurrent mapping edits.
Do not hold locks while sending notifications or rendering reports. Commit
all assignment/M2M changes together; run post-commit cache invalidation and
queue-wide reconciliation only after commit.

Status configuration edits affect many members. Do not rely only on a single
member’s `save()` callback. Use an explicit, idempotent reconciliation command
or admin action that snapshots the affected status/mapping set, processes
members in ascending primary-key order, and records progress/errors. A worker
must re-check configuration under lock before committing each member so a
concurrent mapping edit cannot be overwritten silently.

## 5. Ambiguity and operational reporting

Provide dry-run and apply modes. Every run reports counts and member/group
identifiers for:

* active mapping rows targeting a missing/deleted group or missing role key;
* duplicate active mappings or conflicting status keys;
* members whose status string has no matching immutable status identity;
* status assignments whose mapping no longer exists or is disabled;
* direct group memberships with no assignment rows (`unexplained`);
* rows with unknown source/source_key, including legacy data outside the known
  formats; and
* changes suppressed because an inactive-status policy decision is unresolved.

Ambiguous rows are no-op by default: preserve existing access and do not guess.
The command exits non-zero when required configuration is ambiguous, while
still emitting a machine-readable report and an operator-readable summary.
Permission-source/admin summaries should label status rows with both the
stable key and current display names, and distinguish “configured but
ineffective because member is inactive” from “unexplained.”

## 6. Migration and rollout strategy

1. **Inventory (read-only):** count statuses, names, members, groups,
   assignment sources, duplicate group names, missing metadata, and
   unexplained memberships. Back up before any write. No database seeding is
   part of this proposal.
2. **Schema compatibility:** add the immutable status identity and mapping
   table/constraints without changing effective group membership. Keep the
   current name-based `Member.membership_status` column while compatibility
   data is repaired.
3. **Identity backfill:** assign keys to existing status rows; detect and stop
   on collisions. Resolve members whose stored names do not match exactly.
   Do not guess renamed statuses. Preserve a review table/report for unresolved
   rows. Keep the existing delete guard.
4. **Provenance validation:** validate existing `MemberRoleAssignment` rows.
   Do not recategorize `manual:migration`, untracked direct groups, or legacy
   rows as status without explicit evidence. Add no status mappings until
   product-approved configuration exists.
5. **Dual-read/dry-run:** calculate desired status assignments and emit reports
   without writes. Compare results with product-approved fixtures and review
   every ambiguity.
6. **Feature-gated dual-write:** enable status reconciliation for selected
   environments/statuses. On member status changes, reconcile after commit;
   on mapping/activity changes, enqueue the affected member set. Continue
   honoring all existing source-preservation rules.
7. **Backfill approved mappings:** run the idempotent command in batches with
   per-member transactions, metrics, resumable progress, and a rollback plan.
   Re-running must produce zero changes when configuration and data are stable.
8. **Cutover and cleanup:** only after parity and audit review, make the
   reconciler default. Retain the legacy status string and migration evidence
   until a separate, approved foreign-key migration proves no unresolved rows.

## 7. Acceptance criteria

* No status-to-role pair is granted unless an explicit enabled mapping exists;
  no undocumented initial mappings are assumed.
* A status rename does not change effective role membership or provenance.
* Inactive transitions remove only status-owned rows (or follow the separately
  approved inactive policy), and reactivation is idempotent.
* Revoking a status mapping never removes a group still supported by manual,
  legacy, or another status source; unexplained direct membership remains.
* Manual admin group workflows and `_sync_groups()` continue to pass unchanged
  preservation semantics.
* Concurrent manual, legacy, member-status, and mapping updates serialize
  without lost assignments or duplicate provenance rows.
* Missing mappings, stale assignments, unknown identities, duplicate groups,
  and unexplained memberships are visible and do not trigger guessed changes.
* Dry-run output is deterministic, apply is resumable, and a second apply is a
  no-op.
* Existing six canonical groups, stable role keys, permissions, and mailing
  list role selectors remain intact.

## 8. Implementation and test plan

1. Add the status identity/mapping models and constraints; add admin preview,
   guarded edits, and audit logging. Add a service with `plan(member)` and
   transactional `apply(member)` so planning is testable without writes.
2. Refactor `_sync_groups()` only as needed to call the shared “ensure group
   for all assignment sources” helper; keep legacy-flag ownership separate
   from status ownership. Add a queue/management command for bulk runs.
3. Add unit tests for exact source-key construction, mapping uniqueness,
   rename stability, inactive behavior, missing identities, and no-op plans.
4. Add database tests for: status grant/revoke; two status mappings to one
   group; manual/status/legacy coexistence; unexplained direct membership;
   deleting/renaming statuses and groups; non-assignable roles; duplicate or
   missing metadata; and permissions remaining unchanged.
5. Add migration tests that snapshot all groups, memberships, assignment
   provenance, and permissions before/after. Verify the inventory/backfill is
   idempotent and never converts `manual:migration` or unknown data.
6. Add transaction/concurrency tests using two writers for member status,
   manual role changes, legacy flag sync, and mapping edits. Assert no lost
   assignment, no duplicate `(member, group, source, source_key)`, and correct
   final M2M membership.
7. Add admin and command tests for dry-run/apply permissions, deterministic
   ambiguity reports, resumability, non-zero failure on unresolved required
   configuration, and post-commit behavior.
