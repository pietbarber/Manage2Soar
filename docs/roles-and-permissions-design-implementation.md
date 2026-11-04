# Roles and permissions

This is the implementation guide for the incremental authorization work in
[PR #1140](https://github.com/pietbarber/Manage2Soar/pull/1140). It describes
what exists on this branch and what still requires review; it is not a release
approval. For route-level behavior and test gaps, see the
[authorization inventory](roles-and-permissions-authorization-inventory.md).
For deployment gates, see the [release runbook](runbooks/roles-permissions-release.md).

## Model and terminology

| Concept | Source of truth | Access implications |
| --- | --- | --- |
| Persistent role | Django `Group`, identified in new code by `RoleMetadata.key` | Group permissions grant global capabilities. Display names and profile labels do not grant access. Custom roles start without permissions. |
| Role assignment | Group membership plus `MemberRoleAssignment` provenance | A member can hold the same Group for multiple reasons; removing one reason must preserve the others. |
| Qualification | `ClubQualificationType` and current `MemberQualification` | An opted-in permission bundle can grant explicitly approved custom actions while the qualification is valid. It does not add a persistent Group membership. |
| Member tag | `MemberTag` and assignments | Presentation and optional mailing-list audience only, never authorization. |
| Operational assignment | Domain-specific records, such as `DutyAssignment` or `AircraftMeister` | Ownership, scheduling, and equipment access remain scoped to the relevant object and action. |

The Django permission codename describes a capability; the endpoint still
enforces account status, active membership, kiosk rules, ownership, workflow
state, and any other contextual constraints. UI visibility is not an access
control boundary.

## Implemented on this branch

### Roles, provenance, and administration

- `members/role_definitions.py` registers built-in role keys and incremental
  capability grants. Historical migrations seed and backfill Groups without
  discarding unrelated tenant-created Groups or permissions. Migration `0052`
  adds missing registered grants; it does not remove other grants. Exact
  role-to-action mappings still need maintainer approval.
- `RoleMetadata` gives Groups stable keys, editable display names, and
  administration and mailing-list settings. Existing Group names remain for
  legacy consumers. `admin_access` is an additive role-level signal; Django
  admin still uses `is_staff` as its entry gate. Role editing is not a general
  replacement for Django admin's per-model checks.
- Member admin routes manual Group changes through `set_manual_role()`. Legacy
  flag synchronization records its own provenance and preserves independent
  assignment reasons. Assignment creation/deletion produces snapshot-backed
  grant/revoke events. Direct `Member.groups` or through-table writes elsewhere
  can still bypass provenance and now emit an audit-only tripwire warning; see
  [direct Group write enforcement](direct-group-write-enforcement.md).
- Superusers can administer role metadata and qualification bundle grants.
  Broad Platform Administrator delegation, complete audit coverage for Group
  permission edits and qualification lifecycle, and automatic status-to-role
  mapping are not complete. The proposed status policy is documented in
  [status-role reconciliation](status-role-reconciliation-policy.md).

### Permission checks and compatibility

`members.authorization.resolve_authorization()` returns an allow/deny decision
and reason from `user.has_perm()` or a caller-supplied contextual grant, after
optional account/membership gates. It does **not** infer a grant from legacy
booleans, verify kiosk authentication, inspect objects, or write an audit event.
Callers must supply trusted kiosk context and check object ownership themselves.
Ordinary Django Group permission caches on a user instance may need refreshing
after grants change.

Selected membership, CMS, billing, roster, knowledge-test, and logsheet actions
now use explicit permissions or bounded compatibility helpers. Many routes still
depend on legacy booleans, named Groups, staff status, or object-level rules.
Do not treat the resolver as an app-wide switch or assume permission parity for
unreviewed endpoints. The
[authorization inventory](roles-and-permissions-authorization-inventory.md)
records the observed allow/deny behavior; the
[codename matrix](roles-permissions-codename-matrix.md) is an **unapproved**
proposal for remaining route migrations, not a list of implemented grants.

The safety-report officer endpoints use the existing
`members.access_safety_reports` capability through the shared resolver. The
legacy `safety_officer` flag remains useful for reporting and audiences but is
not sufficient by itself. Account and active-membership gates, superuser
compatibility, and denied POST behavior remain enforced.

Stats-dump export access is source-aware. The `stats_monger` flag owns its
`legacy:stats_monger` role assignment. Migration `0053` converts flagged
members to that source and treats any remaining unprovenanced direct export
grant as the historical `0045` grant, removing it; `0054` repeats the cleanup
for databases that already ran an earlier version of `0053`. Independently
assigned Group/role access is preserved. This security-first policy may remove
an unrecorded direct exception, so review the parity report before rollout.

Membership-application management allows directors and holders of the explicit
view capability to read, while member-manager/webmaster compatibility access is
required to modify. Staff status alone does not grant access. **Intentional
change:** shared kiosk sessions cannot list, view, or modify applications even
if the underlying account has a manager flag. Applicant-facing public routes
have a separate policy. The [endpoint matrix](roles-and-permissions-authorization-inventory.md#membership-application-management-endpoint-level-first-pass)
details methods, gates, and tests.

CMS page restrictions retain public/private, active-member/kiosk, role-OR, and
per-member editor rules. A page editor's scoped grant is not a global role.
The global `cms.view_page` capability alone does not bypass a page's stored role
restriction. The existing `cms.change_page` editor path intentionally still
implies view, and legacy officer compatibility remains a separate policy choice.
See the [CMS baseline](cms-authorization-baseline.md) before changing stored
role values or page policies.

Member editors with `members.change_member` retain the limited member-edit
policy, but cannot use Django's separate password-change endpoint to reset
another account. Superusers retain that administrative capability; self-service
password changes remain available to the limited editor.

### Qualification bundles, audiences, and preview

`ClubQualificationType.permission_group` optionally links a qualification to
a protected permission bundle. Each custom action requires an explicit
`QualificationPermissionGrant` opt-in; CRUD and sensitive administrative actions
are excluded. `QualificationPermissionBackend` resolves grants from current,
non-obsolete, non-revoked qualifications, with expiry inclusive through the
local date. It does not grant object permissions or alter `Member.groups`.
There is **no automatic mapping** from existing instructor, tow-pilot, or duty
qualifications to these bundles. Any new mapping requires an approved positive
allowlist and tests of eligibility and expiry.

Mailing lists accept additive `role:<stable-key>` and `tag:<key>` selectors
alongside existing criteria. Role selectors resolve actual Group membership,
not permissions, qualifications, or duty assignments. Eligibility limits new
role selection, not resolution of a selector already saved. Existing audience
filters and mail-server response format remain in place; real-tenant recipient
parity has not been established. Configurable notification topics and derived
aircraft-specific tags are separate future work, not features of this PR.

`members/role_preview.py` provides a session-based selected-role preview with
a banner and explicit exit. It is currently restricted to active superusers;
`RoleMetadata.admin_access` is not sufficient because it is an admin-entry
signal, not a preview capability. The preview projects permissions and
compatible role checks onto the request without changing the administrator's
stored roles. Outside DEBUG preview, unsafe HTTP methods are blocked. Preview
does **not** yet prove that GET routes have no side effects or define
audit-log retention; start/stop events are logged, not a complete preview
audit policy. Do not treat preview as safe for unrestricted deployment until
these are reviewed.

The parity management commands support a legacy-compatible projection for
pre-role-metadata databases and a full branch projection. Stable member,
permission, and recipient state is compared separately from branch-only role
metadata and assignment provenance. Recipient addresses are hashed by default;
captures run in a consistent read-only transaction where PostgreSQL permits it.

## Review and rollout boundaries

1. Approve the built-in role-to-capability mapping and any qualification-derived
   business actions. Keep global permissions distinct from ownership, active
   membership, kiosk, and workflow checks.
2. Review staff-only endpoints and legacy Group/flag consumers one route at a
   time. Compare both allowed and denied requests (including response shape and
   lack of side effects) before replacing a legacy predicate. Preserve
   superuser compatibility unless a change is explicitly approved.
3. Decide how direct Group writes, status-based assignments, and the remaining
   audit gaps will be handled before treating provenance as the sole authority.
4. Resolve preview GET-side-effect and audit-retention policies. Confirm the
   kiosk restriction on application-management routes.
5. Validate clean-install and **in-place** upgrades on disposable PostgreSQL
   databases. Compare sensitive-action results and mailing-list recipients on
   an authorized copy of representative tenant data. The synthetic migration
   check described in PR #1140 is not production parity. Follow the
   [release runbook](runbooks/roles-permissions-release.md) for backup and
   recovery gates.

Keep existing flags and Group memberships until their operational consumers
and endpoint policies are reviewed. A qualification, tag, or contextual duty
assignment must never be inferred from a similarly named role.
