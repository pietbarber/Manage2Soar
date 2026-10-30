# Roles and Permissions: Implementation Plan

> **Superseded:** This earlier outline is retained for history. The current
> decisions, detailed design, phased implementation plan, and remaining
> technical questions are in
> [`roles-and-permissions-design-implementation.md`](roles-and-permissions-design-implementation.md).
> Use that document as the source of truth; the open questions below may be
> outdated.

This document describes a possible implementation process for the proposal in
[`roles-and-permissions-proposal.md`](roles-and-permissions-proposal.md). It is
intended for maintainer review and planning; it does not imply that the design
or migration details have been approved.

## Implementation principles

- Keep Django `Group` and `Permission` as the authorization foundation.
- Preserve current effective access as the initial permission configuration.
- Use stable role keys for application references; do not authorize by editable
  display names.
- Keep role grants, qualification-derived grants, and contextual operational
  assignments distinguishable, so their different scope and lifecycle are
  preserved.
- Centralize authorization decisions and use them in views, APIs, admin,
  services, templates, notifications, and mailing-list resolution.
- Keep the initial change scoped to each tenant's existing deployment/database.
- Apply the initial patch to test deployments and validate migrated data there.

## Data and permission model

### Role metadata

Add a `RoleMetadata` model with a one-to-one relationship to `auth.Group`.
Suggested fields:

- `key`: unique, stable identifier (for example, `instructor_admins`)
- `display_name`: editable user-facing role name
- `description`
- `is_builtin`, `is_protected`, `is_system_managed`, `is_assignable`
- `mailing_list_eligible`
- `sort_order`

Roles are persistent member groupings. They may grant application permissions
and provide profile tags. New custom roles have no permissions by default; an
administrator must explicitly grant permissions. A role-provided profile tag
is presentation only and does not itself authorize an action.

Keep the Group's existing name stable initially for compatibility with existing
code and data. Use the metadata key for new application references, and the
display name for presentation. Changing a display name must not change
membership, permissions, or mailing-list references.

### Role assignments and provenance

Django's member-to-Group relation does not record why a member has a Group. Add
an assignment/provenance record (or an equivalent mechanism) so the system can
distinguish manual role membership from legacy or system-managed membership.
Do not use Group membership as a substitute for recording qualifications or
contextual operational assignments. Distinguish:

- manual administrator assignments;
- membership-status-driven role assignments;
- legacy/system-managed role assignments.

The Group membership remains the effective persistent role membership. The
assignment records are used to reconcile it safely: remove the Group membership
only when no valid role-assignment source remains. Define uniqueness and update
rules so synchronization is idempotent. Qualification-derived permissions and
tags should resolve from the qualification record's current status and validity,
not from a copied persistent role assignment. Expiration or revocation removes
those derived effects immediately and is auditable.

Profile tags are presentation data/effects supplied by a role or qualification;
they do not independently grant authorization. Operational assignments remain
contextual records (such as a duty, aircraft, roster, or event assignment).
Policies may consider an assignment within its scope, but it must not become a
persistent administrative Group merely because it is called a role in the
operational UI.

Before implementation, confirm how to handle legacy Group memberships that
were not produced by `Member._sync_groups()`. The migration must preserve them
or explicitly map them; it must not silently discard manually added groups.

### Permissions

- Keep Django CRUD permissions on `Group.permissions`.
- Define workflow-specific permissions in application code/model metadata and
  migrations (for example, `roster.publish` or `finance.reverse_transaction`).
- Let authorized administrators assign available permissions to roles; do not
  imply that administrators can create executable application behavior merely
  by entering an arbitrary permission string.
- Mark any essential permissions that must be protected from removal, if the
  maintainers identify such permissions.

### Membership status, qualification, and assignment effects

Provide admin-managed mappings from membership statuses to automatic baseline
roles. Preserve existing active-member access rules and make status changes
reconcile only status-sourced assignments. The assignment service is
authoritative for new supported Group writes; existing unexplained/manual
memberships remain valid until explicitly reviewed and must not be silently
removed.

Qualifications may provide configured permissions/eligibility and profile tags
while valid. Derive those effects from the qualification record and its
award/expiry/revocation state; do not create an administrative Group membership
unless that is separately and explicitly intended. Expiration or revocation
removes qualification-derived effects immediately, while any independently
granted administrative role remains unaffected.

Qualification-derived permissions use a positive allowlist. Permission
codenames cannot establish intent by themselves. Administrative,
authentication, member-management, qualification-management, broad
management, impersonation, and export permissions are excluded unless a
separate review explicitly approves them.

Keep operational assignments scoped to their context. Define object-level
policies for actions that depend on the specific duty, aircraft, roster, or
event; do not treat a contextual assignment as a global role permission.

Privileged administrative roles remain manually assigned. When a member becomes
inactive, retain the Group memberships and manual assignment records, but
remove their effective ability to use those permissions. Inactive members
cannot log in under the existing account-status policy; the authorization
resolver must also deny effective role/qualification permissions if an inactive
identity is evaluated directly. No automatic cleanup may silently remove the
underlying Groups or assignments.

## Admin experience

Add or configure admin screens for:

1. **Roles:** metadata, permissions, protected/system-managed flags, and
   mailing-list eligibility.
2. **Member roles:** assign/remove manual roles and show automatic assignment
   sources and effective roles.
3. **Membership-status mappings:** select the automatic baseline roles granted
   by each status.
4. **Notification topics:** select which roles receive each existing
   role-based notification.
5. **Audit history:** review role and permission changes, restricted to
   Platform Administrators.

Only Platform Administrators can create roles or edit protected built-in role
permissions. Changes to role permissions affect all members with that role
immediately and should display that consequence before saving.

Roles are composable bundles of focused capabilities, not monolithic access
profiles. The migration target is parity with the current intended deployment
behavior while reducing each role to only the capabilities required for its
job. A Member Manager retains legitimate membership-management capabilities,
but generic or unrelated access obtained only through `is_staff` or an overly
broad legacy Group is not folded into the new role. Additional capabilities
are assigned through separate roles or permissions.

Permission administration should have a small number of authoritative sources:

1. registered Django model/workflow permissions assigned to roles;
2. explicitly approved qualification-derived permissions; and
3. code-owned contextual policies for ownership, workflow state, kiosk,
   active-member, and operational-assignment rules.

Admin screens should assign existing registered permissions and show their
view/add/change/delete effect. They must not create arbitrary executable
permission names. Django admin visibility and mutation checks, application
views, APIs, and services should consume the same permission/resolver contract
instead of maintaining independent staff, boolean, or hard-coded Group-name
exceptions. The initial migration prioritizes parity: preserve current
role-to-permission assignments as closely as possible while representing them
in one understandable role/capability structure.

Administrative-site access is separate from business permissions. The new
explicit admin-access capability/flag is the source of truth for whether a role
should have administrative-site access, while Django's existing `is_staff`
field remains the technical gate for entering the admin during this migration.
The role configuration must control the admin-access decision and the
model/action permissions separately. This lets administrators add or remove
individual permissions without granting unrelated application access merely
because a role can see the admin menu. Superuser behavior remains a separate
compatibility path pending maintainer review. Replacing the Django admin gate
itself is deferred; first migrate the permission sources and application
authorization paths.

While Django's `is_staff` remains as a temporary technical admin-site gate,
every staff-derived behavior must be rebound explicitly to the appropriate
role capability or contextual policy. `is_staff` must not itself authorize an
application action. Legacy boolean fields remain temporarily as compatibility
and operational data sources, but authorization consumers must migrate to the
new role/resolver system. New supported writes should update role assignments
or contextual records rather than using boolean flags as the authorization
source. Operational booleans such as instructor, tow-pilot, duty-officer, and
safety-officer must be mapped explicitly to qualification or contextual
policies rather than mechanically converted into global administrative roles.

## Central authorization and migration of checks

Create shared helpers for role and permission checks, then migrate existing
authorization code to them. Inventory and update:

- direct boolean checks (`treasurer`, `webmaster`, `instructor`, etc.);
- hard-coded Group-name checks;
- `is_staff` checks that currently stand in for application permissions;
- specialized decorators and service-level policy functions;
- admin `has_*_permission()` methods;
- CMS page-level role permissions;
- templates, navigation, and action visibility;
- APIs, background tasks, and notification recipient queries.

Keep `is_superuser` behavior as close as possible to the current deployment
until maintainer review. Do not redesign superuser semantics or turn
superuser or staff status into a new universal bypass while migrating
authorization. Existing `is_staff` checks must be superseded by explicit new
permissions/resolver checks on the affected endpoints, while preserving their
endpoint-specific semantics. `is_staff` must not become a universal
application permission. Separate Django admin access from
operational/business permissions.
Template visibility is not an authorization boundary: each protected request
and service operation must enforce permissions server-side.

Preserve CMS page-level behavior during the migration. If those rules move to
stable role keys, migrate existing stored role values and retain compatibility
for old values until conversion is verified.

## Mailing lists and notifications

### Mailing lists

- Preserve existing criterion codes and subscriber behavior.
- Add role criteria stored as stable keys (for example,
  `role:weekend_coordinator`).
- Show only roles marked mailing-list eligible in the Mailing List admin.
- Preserve active-member, valid-email, and other current subscriber filters.
- Keep the mail-server API response format unchanged.
- Warn/block role retirement while a mailing list references that role.

### Notifications

Keep notifications independent from permissions. Create configurable
notification topics and map each topic to eligible roles. Seed mappings from
the current recipient logic. Resolve active recipients from those roles,
deduplicate them, and preserve current channel/preferences and fallback rules.

## Session-based role preview

Add a Platform Administrator-only session preview after centralized permission
resolution is available.

- Store the selected role in the session; do not create or modify a user account.
- Display a persistent preview banner and an explicit exit action.
- Evaluate access as the selected role, without inheriting the administrator's
  other elevated roles. Confirm whether the Active Member baseline is included.
- Make preview read-only: reject unsafe HTTP methods and block external side
  effects such as email sending, transaction posting, role/permission changes,
  and background-job submission.
- Audit preview start/exit under the real administrator identity.
- Ensure session expiry, logout, role retirement, and failed preview setup
  safely clear or invalidate preview state.

Audit GET endpoints and other side-effecting paths as well; HTTP method checks
alone do not prevent every mutation or external action.

## Test-deployment migration process

1. **Inventory and baseline:** capture current Groups, permissions, boolean
   assignments, staff status, CMS role rules, notification recipients, and
   mailing-list subscribers in test data.
2. **Schema migration:** add role metadata and assignment provenance, plus any
   status/notification mappings.
3. **Seed built-ins:** create metadata for existing Groups without changing
   their initial permissions or display behavior.
4. **Backfill:** convert existing boolean/group state into manual or automatic
   assignment sources according to an explicit mapping. Report ambiguous or
   conflicting records rather than silently guessing.
5. **Switch authorization:** migrate code paths to centralized role/permission
   checks and update admin/template/API behavior.
6. **Update dependent systems:** migrate mailing-list criteria, notification
   routing, imports/exports, and test factories.
7. **Add role preview:** implement after authorization checks are centralized.
8. **Validate:** compare pre/post effective access and recipient sets; run
   focused tests for each migrated subsystem.
9. **Retire legacy authorization use:** once validation passes, stop using
   boolean fields as authorization sources. Keep fields temporarily if needed
   for operational data compatibility, with a documented later removal step.

Since the patch targets test deployments, maintainers should decide whether
existing test databases must be migrated in place or can be recreated. In-place
migration is needed to validate data conversion; a clean rebuild alone does not
exercise that path.

## Acceptance criteria

- Existing built-in roles retain their current effective permissions after
  migration.
- Custom roles can be created, configured, and assigned through admin.
- Role display-name changes do not break authorization or mailing-list
  references.
- Status synchronization is repeatable and does not remove manual role
  assignments.
- Qualification-derived permissions, eligibility, and tags follow qualification
  validity and disappear immediately on expiration or revocation.
- Tags are presentation only; authorization is enforced by permissions and
  contextual policies, never by the presence of a tag.
- Existing direct authorization behavior is represented by Django or
  business-action permissions and covered by allow/deny tests.
- CMS page access, navigation, APIs, notifications, and mailing lists retain
  intended behavior.
- Role preview reflects the selected role, shows a clear banner, and cannot
  mutate data or trigger side effects.
- Role and permission changes, automatic assignment changes, and preview
  sessions are auditable by Platform Administrators.
- Migration reports unresolved or ambiguous assignments rather than silently
  losing access.

## Decisions to confirm during review

- Whether test databases must be migrated in place or may be recreated.
- The policy for manually assigned privileged roles when a member becomes
  inactive.
- Whether role preview includes the Active Member baseline.
- Which permissions, if any, are protected from removal.
- Whether CMS page-level roles migrate in this patch or retain a compatibility
  layer.
