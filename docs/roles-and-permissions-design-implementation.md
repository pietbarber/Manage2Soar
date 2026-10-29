# Roles, Permissions, and Qualifications: Design and Implementation Handoff

This document is the detailed design/context handoff for future sessions working
on the proposed authorization changes. The shorter maintainer-facing overview is
in [`roles-and-permissions-proposal.md`](roles-and-permissions-proposal.md).

This is a design, not an authorization to deploy. The initial implementation is
intended for test deployments and should use the project's normal in-place Django
migration process.

## 1. Goals

- Make permissions and persistent administrative roles understandable and
  manageable through Django admin.
- Reuse Django `Group` and `Permission`, rather than replace them with a new
  permission engine.
- Preserve current effective access as the initial configuration.
- Let qualifications provide time-valid permissions/eligibility and profile
  tags without confusing qualifications with persistent administrative roles.
- Keep contextual operational assignments and per-object grants contextual.
- Improve discoverability of aircraft-specific responsibilities, including
  Aircraft Meisters (related issue #904).
- Support custom roles, role-aware mailing lists, configurable notification
  audiences, reusable custom tags with variable-based labels, and an accurate
  read-only role preview.
- Migrate existing test-deployment data in place and report ambiguous state.

## 2. Settled vocabulary and semantics

### Role

A persistent member grouping represented by a Django `Group`. A role may:

- grant application permissions through `Group.permissions`;
- provide a profile tag;
- be used as an audience source for a mailing list or notification topic when
  configured as eligible.

New custom roles start with **no permissions**. Creating or assigning one does
not grant access until permissions are explicitly added. A role-provided tag is
presentation only and does not itself authorize an action.

### Qualification

An awarded or recorded member status with its own source, award date, validity,
expiry, and revocation lifecycle. A qualification may:

- provide permissions through an associated Django Group permission bundle;
- provide operational eligibility while current;
- provide a profile tag.

Qualification-derived permissions and tags end immediately when the
qualification expires or is revoked. A qualification is not automatically a
persistent administrative role.

### Member tag

A permissionless profile/audience label. Tags may be manually assigned or
derived from a role, qualification, or contextual record. For example, a
current Tow Pilot qualification may display a Tow Pilot tag and provide
tow-related eligibility, while an aircraft assignment may derive an
aircraft-specific tag. The tag itself is never an authorization source.

Clubs should also be able to create reusable custom tags whose labels can be
generated from generic variables/placeholders (for example, a tag template
combining an equipment identifier with a club-defined responsibility label).
The exact authoring workflow, supported variables, and assignment UX are
intentionally deferred to the miscellaneous club-equipment design. That work
should define how template instances stay linked to their source records and
how stale derived tags are removed. Custom tags remain permissionless; selecting
a tag for an audience is an explicit audience configuration, not an implicit
subscription or permission grant.

### Operational assignment

A responsibility in a specific context, such as a person assigned to a duty on
a date, aircraft, roster, or event. It remains separate from persistent Group
membership. A policy may authorize actions within the assignment's context.

### Permission and authorization policy

A permission is an application capability. A policy decides whether an action is
allowed and may combine permissions with membership status, a current
qualification, an operational assignment, object ownership, kiosk context, or
other rules. Possessing a permission does not automatically bypass those other
checks.

### Notification audience

The recipients resolved for a particular notification. Roles can be one source
of recipients, but event, assignment, aircraft, and other contextual recipients
must remain supported.

## 3. Chosen architecture

```text
Member ── Django Group membership ──> Role
                                      ├── Group.permissions
                                      └── RoleMetadata (one-to-one)

Member ── MemberQualification ──> QualificationType ──> permission Group (optional)
                                      └── current/expiry/revocation controls its effects

Member ── contextual record ──> Operational assignment
```

### Role metadata

Add `RoleMetadata` one-to-one with `auth.Group`. Expected metadata includes:

- stable unique `key`;
- editable `display_name` and description;
- built-in/protected/system-managed/assignable indicators;
- mailing-list eligibility;
- display order.

Keep existing `Group.name` values stable initially for compatibility. New code
uses the stable metadata key for references and the display name for UI. A
display-name change must not change permissions, membership, or mailing-list
criteria.

### Permission storage

- Django CRUD permissions and implemented business-action permissions remain
  attached to `Group.permissions`.
- Built-in groups start with the current permission sets and effective behavior.
- Custom groups start empty.
- Permission definitions must exist in application code/migrations; an admin
  assigning an available permission does not create new executable behavior.

### Qualification permission bundles

A qualification type may reference a Django Group used as its permission
bundle. A member receives those permissions only while the corresponding
qualification is current. Do not permanently add the bundle Group to
`Member.groups` on award: ordinary Group membership does not encode expiry and
could accidentally make the grant permanent or collide with a manual grant.

Implement a centralized resolver or Django authentication backend that combines
ordinary Group permissions with permissions from current qualification-linked
Groups. The exact implementation must be selected after checking Django backend
behavior and existing `has_perm()` use. It must:

- check both `is_qualified` and `expiration_date` using the project's local-date
  conventions;
- stop returning qualification permissions immediately on expiration or
  revocation, without relying on a later scheduled cleanup;
- keep qualification-derived grants distinguishable from role membership;
 - require explicit per-permission opt-in for every qualification-derived
   action. Permission codenames cannot safely establish intent: unapproved
   `manage_*`, `impersonate_*`, `export_*`, and other custom permissions are
   denied. CRUD/view, authentication/admin, member-management, and
   qualification-administration permissions are never eligible for opt-in;
- avoid granting broad admin permissions through operational qualifications;
- support object/context policies separately where Group permissions are too
  broad.

The existing instructor/tow-pilot booleans are not proven to map one-to-one to
`ClubQualificationType`. Inventory them before assigning qualification bundles;
do not infer a mapping solely from similar names.

## 4. Existing project behavior to preserve and account for

### Existing Groups and role flags

Canonical Group permissions are seeded in
`members/migrations/0021_setup_all_group_permissions.py`. The current canonical
groups include Instructor Admins, Webmasters, Member Managers, Rostermeisters,
Secretary, and Treasurer. Other access is implemented outside those permission
sets, including direct boolean, group-name, `is_staff`, and `is_superuser`
checks.

`Member._desired_group_names()` and `_sync_groups()` in `members/models.py`
derive Groups from selected booleans. The current `_sync_groups()` has a first
provenance-aware slice: it reconciles `legacy` assignment rows and no longer
replaces all Group memberships. This is **not** a completed assignment service:
Member admin now routes its Group edits through the source-specific manual-role
service, but arbitrary direct `member.groups` and through-table writes still
need a defined enforcement/migration contract before retiring legacy flags or
relying on assignment rows as the sole authorization source.

Existing Groups/permissions not explained by known automatic defaults are
classified as **manual and preserved** during backfill. The migration should
report uncertain mappings rather than silently discard or guess.

### Qualification records

- `instructors.ClubQualificationType` defines club qualification types.
- `instructors.MemberQualification` records a member's qualification, awarder,
  award date, expiry, qualified status, and notes.
- `QualificationAssignForm` and instructor/safety-officer workflows award or
  update these records; qualifications are also displayed on profiles.
- Duty qualifications use a separate `MemberDutyQualification` model and have
  their own current/expiry semantics.

These qualification mechanisms must not be assumed interchangeable. Map each
permission-bearing qualification explicitly.

### Operational duty roles and assignments

The duty roster has dynamic role definitions and qualification requirements, as
well as date-specific `DutyAssignment` and normalized `DutyAssignmentRole`
records. These describe scheduling and responsibility, not persistent
administrative Group membership. Preserve their date/location/eligibility
semantics. Do not turn every duty role into a global application role.

### Aircraft Meister discoverability (issue #904)

Issue #904, “Members: No obvious way to show aircraft meisters,” is a
discoverability/UI requirement: members should be able to find who is assigned
as meister for a particular aircraft. It is not a request to create a global
Aircraft Meister administrative role or a generic tag that stands in for the
assignment.

- `AircraftMeister` remains the source of truth for the member-to-aircraft
  assignment.
- Proposed presentation: provide an automatically linked, aircraft-specific
  tag, using the aircraft registration/name plus a club-configurable label, for
  example `N123AB Maintenance Officer`, `N123AB Meister`, or
  `N123AB Crew Chief`. The club configures the descriptive suffix; the aircraft
  identity comes from the aircraft record.
- The tag is derived from the aircraft-specific assignment and must not be
  independently assigned as a way to grant meister status. Assignment changes
  should update who receives the tag automatically.
- Display the assigned meister(s) on an appropriate aircraft-facing surface,
  such as aircraft details or the maintenance view; a member profile may also
  list the aircraft-specific tags/assignments they hold.
- Make the aircraft-specific tag selectable as a notification or mailing-list
  audience where useful. Resolve those recipients from the current assignment
  (or its derived tag membership), so removing an assignment removes the member
  from that aircraft's audience. It must not subscribe every meister to every
  aircraft's notifications.
- Keep maintenance authorization and notifications scoped to the relevant
  aircraft assignment.
- This remains a permissionless presentation/audience label, not an
  authorization grant; maintenance access continues to follow the existing
  aircraft-specific policy.

Treat this as a related, separately scoped UI enhancement. Do not expand the
roles/permissions migration to change the existing assignment model unless
implementation review finds a concrete need.

### CMS page access

CMS role checks are a separate subsystem and are **in scope for migration**:

- `PageRolePermission` stores a hard-coded member-role choice for private-page
  viewing and uses OR semantics (any configured role is sufficient).
- Private pages still apply active-membership rules, with the existing kiosk
  exception; public pages are public.
- `PageMemberPermission` grants a specific member edit access to a specific
  page. It also grants view access to that page when private. Keep this as a
  separate object-specific permission; do not convert it into a global role.
- Existing officer and superuser edit behavior must be represented/preserved.

Migrate role-based page restrictions to the new stable role/qualification
resolver while preserving page visibility, OR behavior, active-member/kiosk
rules, individual editor grants, and edit/view interactions. No parallel
boolean-and-new-role authorization period is required for the Treasurer-style
identity mapping; migrate existing data and checks directly, validating against
the baseline.

### Mailing lists

`siteconfig.MailingList` stores criteria in JSON. Its `get_subscribers()` and
`_criterion_to_query()` currently support legacy status/boolean/ownership
criteria **and additive** `role:<stable-key>` (and `tag:<key>`) selectors. Role
selectors match actual Group membership, not permission inheritance; eligibility
limits new selection, not continued resolution of existing configured selectors.
Do not replace or remove the legacy selectors. Preserve active-member/email
filtering, OR behavior, and the mail-server API response when changing audiences.
Each club has a separate deployment/database, so role assignments do not need
a tenant foreign key.

### Notifications

Notification audiences are not equivalent to permissions. Existing recipient
logic can depend on event, aircraft, roster, assignment, student/instructor
relationship, and current role. Add configurable notification topics with roles
as one possible audience source; retain contextual resolvers, preferences,
filters, deduplication, and fallback behavior. Seed topic mappings to reproduce
current role-based recipient behavior.

### Deployment/bootstrap

Deployment docs provide an Ansible `gke_create_superuser` flow and a manual
`createsuperuser` flow for initial setup and account recovery. Use that existing
operator bootstrap path:

- existing superusers become Platform Administrators during migration;
- subsequent Platform Administrator grants are made by an existing Platform
  Administrator;
- protect the last active Platform Administrator;
- retain `is_superuser` as an emergency override, separate from ordinary role
  administration.

Relevant references: `docs/runbooks/ansible-playbook-guide.md`,
`docs/runbooks/deployment-updates.md`, and `docs/multi-tenant-deployment.md`.

## 5. Role assignment and audit semantics

The member-to-Group relation does not record why membership exists. Add
provenance for persistent role assignments (or an equivalent design) to
distinguish at least:

- manually assigned role;
- status-driven role;
- legacy/system-managed role.

Qualification grants are derived from qualification records and must not be
represented as persistent Group assignments. Operational assignments remain in
their domain records.

Reconciliation rule: a Group is present as an effective persistent role while
at least one valid role-assignment source exists. Removing one source must not
remove a Group still granted by another source. Direct Groups edited through
Django admin must either be recorded as manual assignments or the UI must route
edits through the assignment service. Make reconciliation idempotent and
transaction-safe; define behavior for concurrent edits.

Manual role grant/removal is a single source-specific service operation (for
example `set_manual_role(member, group, enabled=..., source_key=..., actor=...)`).
Revoking `manual:admin` must not delete `manual:import`, `status:...`, or
`legacy:...` reasons for the same Group. A member permission breakdown must
show *every* contributing source for a permission: direct user grant, each
granting Group with its separate assignment reasons (including unknown legacy
Group memberships), and active approved qualification grants. The superuser
override is displayed separately. A tag is never a permission source. An
effective allow/deny result alone is not an adequate explanation.

Audit role/permission changes and automatic assignment changes. Platform
Administrators can review the audit history. Record actor, target member, role,
source, timestamp, and relevant before/after state. Qualification award,
expiry/revocation, and resulting permission changes should be attributable to
the underlying qualification record and actor where available.

## 6. Admin experience requirements

Platform Administrators should be able to:

- create custom roles with no permissions by default;
- edit role metadata and assign available permissions;
- customize protected built-in roles;
- assign and remove manual roles from member records;
- create/manage custom tags, including reusable variable-based tag templates;
- inspect automatic assignment sources and effective permissions;
- map membership statuses to baseline roles;
- link eligible qualification types to Group permission bundles;
- mark roles as mailing-list eligible;
- configure notification topics and eligible roles;
- review role/permission audit history.

Admin UX must clearly distinguish manual role assignments, status grants,
qualification-derived grants, tags, and contextual operational assignments.
Only Platform Administrators can create roles or customize protected built-ins.
Permission changes take effect immediately and should warn that all members
with the role are affected. Members can see role names and qualification-derived
profile tags; tags alone never provide access.

The exact layout (inline on Member, separate assignment admin, or both) is a UX
design task and can proceed while backend contracts are developed.

## 7. Session-based role preview

Preview is for a Platform Administrator to see what a generic member with a
selected role can access—not to impersonate another member or overlay a role on
the administrator's real identity.

Preview principal/context:

- ordinary authenticated active-member baseline plus the selected role;
- no administrator's `is_superuser`, `is_staff`, other Groups, qualifications,
  operational assignments, ownership grants, or per-member CMS editor grants;
- real administrator identity remains responsible for authentication and audit.

Requirements:

- session-based, time-limited, visible banner, explicit exit;
- server-side permission evaluation through a preview-aware authorization
  context, not only template filtering;
- read-only behavior; block data mutations and external side effects, including
  emails, financial posting, role changes, uploads, background jobs, and admin
  actions;
- audit preview start/exit and ensure logout/session expiry clears preview;
- inspect GET routes for side effects; rejecting unsafe methods alone is not
  sufficient.

Implement preview only after centralized authorization resolution exists.

## 8. Migration and deployment approach

Use ordinary Django schema/data migrations, consistent with project practice.
Migrate test-deployment databases **in place**; do not make database reset the
normal path. A clean install may be an additional check, but is not a substitute
for testing backfill against existing data.

Migration sequence:

1. Capture a baseline of Groups, permissions, member flags/staff state, CMS page
   role/editor data, mailing-list subscriber sets, and notification recipients.
2. Add metadata, provenance, qualification-to-Group mapping, status mapping,
   notification-topic mapping, and audit structures as approved by schema
   review.
3. Seed metadata for existing canonical Groups without changing their initial
   permissions. Give existing superusers Platform Administrator authority.
4. Backfill member Group provenance. Preserve unexplained existing memberships
   as manual; produce a report for ambiguous/inconsistent records.
5. Migrate CMS role values and checks while preserving per-member editor grants.
6. Switch authorization and dependent systems to centralized resolution.
7. Validate effective access and audience sets against the baseline; resolve
   differences before retiring boolean authorization checks.
8. Keep legacy fields while operational consumers are reviewed. Retire their
   use as authorization sources first; remove fields only in a later, explicitly
   validated change if appropriate.

Do not add a destructive reset, broad test-database deletion, or production
rollout as part of this test-deployment patch. Follow project migration
conventions and provide an operator-visible backfill report and recovery
instructions. Review migration reversibility rather than assuming every data
migration can reconstruct its prior state.

**Maintainer-visible access change:** Membership-application management
(`members:membership_applications_list`, `membership_application_detail`, and
`membership_waitlist`) now rejects shared kiosk sessions before the legacy role
check. Previously a kiosk Role Account bearing `member_manager=True` could view
applications and POST updated review notes. The new restriction applies even
when that account bears a manager/webmaster flag; public applicant routes are
unchanged. See the endpoint-level matrix and regression tests in
`roles-and-permissions-authorization-inventory.md` and
`members/tests/test_membership_application_access_matrix.py`. Call out the
intentional narrowing in the merge/deployment notes.

## 9. Phases and parallel work

### Phase 1 — Baseline and contract (gate for authorization behavior changes)

- Inventory current checks and build allow/deny behavior matrix.
- Agree model/service contracts for metadata, grants, permission resolution,
  qualification validity, and audit attribution.
- Record migration classification rules.

The **incomplete, unapproved** first-pass static inventory and behavior matrix
are tracked in
[`roles-and-permissions-authorization-inventory.md`](roles-and-permissions-authorization-inventory.md).
Review and extend it with exact source checks and endpoint/method-level allow
and deny tests before changing legacy authorization behavior. No summary row
is itself a migration specification. The membership application list/detail/
waitlist matrix is a worked first pass, not an approved policy mapping; the
baseline tests in `members/tests/test_membership_applications.py`
cover some cases but do not use a resolver and do not complete the baseline.

This gate **does not block additive foundation** (metadata/provenance schema,
diagnostics, narrowly scoped qualification permission bundles, additive
mailing-list selectors, tests or admin UX design) that does not alter the
existing legacy checks. It **does** block switching application/admin/API/
service/CMS checks to a resolver, removing legacy flags, or asserting equivalent
access until the relevant contract and route-level baseline are approved. Do
not treat a foundation slice as proof of authorization parity.

Before that switch, explicitly resolve: direct Group writes and the
provenance-aware assignment service (including concurrent edits), status-to-role
mappings, a positive per-action qualification permission allowlist, audit events
and attribution, the fate of legacy flags/consumers, and baseline/contract
approval. Existing deny filters alone are not the positive allowlist. These
are blockers for behavior migration, not for non-behavior-changing foundation.

### Phase 2 — Parallel design/foundation work

**Backend:** role metadata/provenance models, permission resolver design,
qualification Group mapping design (not enabling legacy mappings), status
mapping design, bootstrap/last-admin policy, migration and diagnostic report.

**Admin UX:** wireframes/workflow for role editor, member assignment, permission
display, qualification mapping, notification topics, mailing-list eligibility,
custom-tag authoring (with detailed variable/workflow design deferred to the
miscellaneous club-equipment work), warnings and audit views. Use the agreed
contract or mock data; do not create a competing data model.

**Verification:** baseline tests and inventory-to-test mapping.

### Phase 3 — Authorization and integrations

After resolver/API contracts stabilize, work can proceed in parallel on:

- application/admin/API/service authorization checks;
- CMS migration and CMS-specific regression tests;
- further mailing-list audience integration (additive role criteria already exist);
- notification topic audience integration;
- admin forms and member-facing role/tag display.

All workstreams use the shared resolver and preserve their existing contextual
policies.

### Phase 4 — Role preview

Implement after the authorization context and read-only protections are tested.
Exercise every migrated surface under preview, including CMS editor grants and
side-effecting endpoints.

### Phase 5 — In-place test validation

Run migrations against representative test data; compare access and recipients
with the baseline; test ambiguous-data reporting, clean installation, and
rollback/recovery instructions. Resolve mismatches before declaring the patch
ready.

## 10. Acceptance criteria

- Existing built-in Groups retain current effective permissions and behavior.
- Custom roles are permissionless by default and can be configured/assigned in
  admin by authorized Platform Administrators.
- Stable keys—not display names—drive new code and mailing-list references.
- Existing Groups not explained by automatic defaults are preserved as manual.
- Qualification-linked Group permissions and tags are active only for current
  qualifications and stop immediately on expiry/revocation.
- Qualifications, persistent roles, operational assignments, and member tags
  remain distinguishable in UI and authorization logic.
- Issue #904's discoverability need is addressed by displaying existing
  aircraft-to-meister assignments and, if adopted, deriving aircraft-specific
  tags with a club-configurable label; these do not become global roles or
  permission grants.
- Membership/status reconciliation does not remove manually assigned roles.
- CMS role restrictions retain existing OR, active-member, kiosk, private/public,
  and editor-implied-view behavior; per-member editor grants remain separate.
- Mailing-list results and notification audiences preserve current filters,
  context, preferences, fallbacks, and deduplication.
- Platform Administrator bootstrap, self-escalation prevention, last-admin
  protection, and emergency superuser override are tested.
- Role preview reflects the selected role rather than the real administrator's
  privileges, blocks writes/side effects, and is auditable.
- In-place migration reports ambiguous data and does not silently discard
  assignments or broaden access.
- Authorization tests include both allow and deny cases for sensitive actions.

## 11. Remaining technical questions for implementation review

These do not reopen the agreed semantics; resolve them before or during Phase 1:

1. Which permission resolver/backend integration best honors qualification-linked
   Group permissions and current expiry without polluting persistent
   `user.groups` membership?
2. Exact role-assignment provenance schema and transaction/locking strategy;
   ensure direct Group admin edits are captured as manual grants.
3. Exact set of qualification types that map to permission Groups. In particular,
   do not assume existing `instructor`/`towpilot` booleans map automatically.
4. Exact current-to-new permission matrix, including direct checks, `is_staff`,
   kiosk, ownership, and object-level policies.
5. Any protected permissions or prohibited combinations for custom roles.
6. Final admin navigation/layout after the workflow design is reviewed.

## 12. Codebase entry points for a new session

- `members/models.py`: `RoleMetadata`, `MemberRoleAssignment`, manual
  `MemberTag`/assignment, Member flags, `is_staff` derivation, and provenance-aware
  Group synchronization.
- `members/migrations/0034_role_metadata.py`,
  `members/migrations/0035_member_tags.py`, and
  `members/migrations/0036_member_role_assignments.py`: initial metadata/tag/
  assignment schema and in-place backfills.
- `members/admin.py`: superuser bootstrap Group/role editor, custom-tag editor,
  and Member admin manual-role provenance. Platform Administrator-based access
  is still a follow-up; do not broaden these surfaces prematurely.
- `members/tests/test_role_metadata.py`, `members/tests/test_group_admin.py`,
  `members/tests/test_member_tags.py`, and
  `members/tests/test_role_assignments.py`: focused coverage for the initial
  foundation slices.
- `members/migrations/0021_setup_all_group_permissions.py`: canonical Group
  permission sets.
- `members/tests/test_group_permissions_migration.py`: current permission
  assertions.
- `instructors/models.py`: `ClubQualificationType` and `MemberQualification`.
- `instructors/forms.py` and `instructors/views.py`: qualification award flows.
- `duty_roster/models.py` and `duty_roster/utils/role_resolution.py`: contextual
  duty roles, assignments, and qualification eligibility.
- `cms/models.py`: `PageRolePermission`, `PageMemberPermission`, and page access
  policies; `cms/admin.py` contains admin integration.
- `siteconfig/models.py` and `siteconfig/admin.py`: legacy mailing-list criteria
  remain alongside additive `role:<stable-key>`/`tag:<key>` audiences. Eligibility
  limits new role selections; already configured role audiences remain active
  until explicitly removed. Group deletion is blocked while a mailing list
  references its stable role key.
- `members/api.py`: mail-server list API.
- `docs/runbooks/ansible-playbook-guide.md` and
  `docs/runbooks/deployment-updates.md`: superuser bootstrap and migrations.

## 13. Qualification permission slice: implementation handoff

The qualification permission slice is **narrow foundation**, implemented in the
current working tree; it is not qualification eligibility migration or a
replacement for the legacy authorization checks:

- `ClubQualificationType.permission_group` is an optional, protected ForeignKey
  to `auth.Group`; saving a qualification type validates that the group has
  opted-in `RoleMetadata` and is not built-in, protected, or system-managed.
- Each permission requires an explicit `QualificationPermissionGrant` row for
  the Group. Custom names alone do not establish safety: unapproved
  `manage_*`/`impersonate_*`/`export_*` actions are ignored. CRUD/view,
  auth/admin, member-management, and qualification-administration permissions
  cannot be opted in. No current qualification type is mapped. Grant rows and
  deny filters are **not** a reviewed positive allowlist of business actions;
  approve one before mapping types or broadening qualification-derived grants.
- `QualificationPermissionGrant` is manageable only by active superusers in
  Django admin. Group choices require opted-in metadata and exclude
  built-in/protected/system-managed Groups. Permission choices are limited to
  safe custom actions already present in the selected Group's
  `Group.permissions`. The workflow is to opt in the Group, configure its
  permissions, grant each action explicitly, then select the Group on a
  qualification type. `ClubQualificationTypeAdmin` offers eligible Groups only
  after they have at least one grant.
- `members.auth_backends.QualificationPermissionBackend` resolves current,
  non-obsolete, qualified records on every permission call. Expiry is inclusive
  through the local date and `NULL` expiry is current. Qualification-derived
  grants never modify `Member.groups`, and object-level checks are denied by
  this global-only backend.
- The backend is registered after Django's `ModelBackend` in both settings
  modules. Django 5.2's ordinary `ModelBackend` cache remains available for
  ordinary Group permissions, but qualification permissions are returned only
  by this uncached backend; no global auth cache behavior is overridden.
- Grants also suspend when `Member.is_active_member()` is false, in addition to
  `User.is_active=False`. This follows the dynamically configured active-status
  policy (`siteconfig.MembershipStatus`). Focused tests cover same-user
  `has_perm()` and `get_all_permissions()` refresh
  after expiry/revocation, inactive users, inclusive/NULL expiry, obsolete and
  unmapped types, object denial, no Group membership, and bundle/admin denylist
  behavior. `instructors/tests/test_qualification_permission_admin.py` covers
  superuser-only grant management and safe choice filtering.

The slice does not yet map any existing instructor, tow-pilot, duty, or legacy
boolean qualification to a permission bundle; neither operational eligibility
nor boolean-role semantics are implemented by the backend. Those mappings
require an approved positive allowlist, explicit permission matrix, and
eligibility inventory. Contextual/object policy integration, assignment-service
and audit completion, status mappings, CMS migration, notification integration,
and role preview remain future work. Mailing-list role selectors already exist
additively; further audience migration is future work. Do not infer a mapping
from a similar qualification name.
