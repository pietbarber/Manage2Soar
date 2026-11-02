# Authorization Inventory and Behavior Baseline

Status: **unapproved, incomplete first-pass static inventory**, 2026-10-29.
This records observed behavior for review before migrating authorization checks;
it is not a completed baseline, approved policy, or migration specification.

## Review scope for this branch

The PR should describe the following separately; a test of one surface does not
approve every other role-to-permission mapping. Compare both allowed and denied
requests to `upstream/main` before calling a mapping equivalent.

| Change in this branch | Current contract / review decision | Evidence |
| --- | --- | --- |
| Application management | Directors, the Directors Group's view capability, and explicit view-permission holders can read; member managers and webmasters can modify. Staff alone and Member Managers Group membership alone do not grant access; a view capability does not grant write access. **Intentional restriction:** kiosk-authenticated role accounts can no longer use the management list, detail, or waitlist, even with a manager flag. List POST still renders a non-mutating response rather than returning 405. | `members/authorization.py`, `members/views_applications.py`; `members/tests/test_membership_application_access_matrix.py` |
| Role and capability backfill | Built-in role keys and their registered capability grants are explicit. Migration `0052` adds missing grants; it must not erase tenant-created Groups, memberships, or unrelated permissions. Approval is still needed for the exact business-action mapping. | `members/role_definitions.py`, `members/migrations/0052_sync_registered_role_capabilities.py`; `members/tests/test_role_definitions.py`, `test_capability_registry_migration.py` |
| CMS, billing, duty, logsheet, and membership actions | Bounded permission helpers and compatibility paths replace some direct role/staff checks. Preserve active membership, ownership, page grants, and workflow context where applicable. **Do not claim global authorization parity:** the inventory below still lists unreviewed endpoints. | `cms/permissions.py`, `billing/permissions.py`, `duty_roster/permissions.py`, `logsheet/permissions.py`, `members/authorization.py`; focused app tests |
| Role preview | A selected role projects its permissions for a request; write methods are denied outside DEBUG preview. GET-side effects and preview audit retention remain explicit release decisions. | `members/role_preview.py`; `members/tests/test_role_preview.py` |
| Qualification permissions | Only approved custom actions from an opted-in bundle can be derived from a current qualification. No existing instructor/tow-pilot/duty qualification is mapped automatically. | `members/auth_backends.py`, `instructors/models.py`; `members/tests/test_qualification_permission_bundle.py` |
| Mailing-list audiences | Role and tag selectors are additive to existing criteria; recipient parity against real tenant data is **not yet verified**. | `siteconfig/models.py`; `siteconfig/tests/test_mailing_list.py` |

Before a PR is treated as deployment-ready, record clean-install and
representative in-place migration results on disposable PostgreSQL databases,
recipient and sensitive-action parity, and the maintainer's decisions on the
unapproved rows. Local migration tests are evidence, not a substitute for
tenant-data validation.

### Local validation record (2026-11-02)

- Disposable PostgreSQL clean-install test databases: 81 focused application
  access/backfill tests, 83 authorization/CMS/logsheet tests, and 64 Group-
  permission/mailing-list tests passed. The latter assert exact Treasurer and
  Secretary capabilities rather than the pre-branch assumption of no grants.
- Disposable PostgreSQL upgrade: applied all `upstream/main` migrations, added
  three synthetic members (legacy instructor and treasurer flags, plus manual
  custom-Group membership), a custom Group permission, and a legacy mailing
  list. Applied the branch migrations through `members.0052`. The legacy and
  manual assignment sources were classified as expected; memberships, custom
  permission, and the two sampled mailing-list recipients were unchanged.
  Registered built-in role capability grants were present after upgrade.
- Both GKE and single-host settings passed `manage.py check` and
  `makemigrations --check --dry-run` against the disposable upgraded database.
- The historical `members.0021` migration still emits missing-permission
  warnings while the graph is first applied; later backfills and focused
  canonical-grant assertions passed. Preserve these warnings in the PR log.
- **Not yet validated:** a representative *tenant-data* upgrade, real mailing-
  list recipient parity, and the full endpoint-by-endpoint authorization
  baseline. The synthetic sample must not be called production parity.

## Scope and method

The inventory covers runtime Python authorization checks using member role
booleans, Django Groups, `is_staff`/`is_superuser`, permission APIs, ownership,
and active-member/kiosk gates. It also records operational qualification and
audience logic where the same legacy role fields are used, so those uses are not
mistaken for general authorization.

The source review used repository-wide searches and focused inspection of the
shared policy helpers and representative app-specific checks. Tests listed
below are known behavior coverage, not a claim that every endpoint has a complete
allow/deny test. **No inventory row is a migration specification without the
exact source checks and route/method-level allow/deny tests.** Templates and
JavaScript visibility are not treated as security
boundaries; the server-side endpoint is the authorization source of truth.

## Existing policy vocabulary

| Policy | Current behavior | Main implementation |
| --- | --- | --- |
| Active member | Many member-facing views require authentication and an active membership status. Superuser handling is centralized in the membership helper; kiosk sessions are specially allowed by `active_member_required`. | `members/decorators.py`; `members/utils/membership.py` |
| Kiosk session | Can access some member-facing content without ordinary membership status, including private member CMS content. Kiosk sessions are rejected from sensitive account-recovery/self-service flows. | `members/decorators.py`; `members/utils/kiosk.py`; `cms/models.py` |
| Platform override | `is_superuser` grants broad overrides, but not uniformly: exact behavior depends on the endpoint and some view policies still require an active member. | App-specific checks; `members/utils/membership.py` |
| Django staff | `is_staff` is used as an application authorization proxy in selected features, including knowledge tests, roster messages, contact-info visibility, and some roster endpoints. It is not a consistent synonym for superuser or any one business role. | `knowledgetest/views.py`; `duty_roster/views.py`; `members/utils/permissions.py` |
| Role booleans | Fields such as `webmaster`, `treasurer`, `instructor`, `member_manager`, `director`, `secretary`, `rostermeister`, and `safety_officer` are used directly in views, decorators, admin methods, and query filters. | Multiple apps; examples below |
| Named Groups | Some checks still use literal Group names rather than stable role keys or permission codenames. | `siteconfig/admin.py`; `knowledgetest/admin.py`; `logsheet/views.py` |
| Ownership/context | A user may act on their own profile, their own assigned work, or an object for which they have an explicit per-object grant without holding a broad role. | Member profile views; `cms.PageMemberPermission`; duty roster and knowledge-test workflows |

## Runtime authorization inventory

| Subsystem / surface | Current allow policy | Current deny / contextual policy | Existing coverage / notes |
| --- | --- | --- | --- |
| Shared member gates | Active members pass `active_member_required`; superusers are handled by `is_active_member`; kiosk sessions can bypass the membership-status check on this decorator. | Anonymous users are redirected to login; non-active members are forbidden unless an explicit exception applies. `non_kiosk_member_required` rejects shared kiosk sessions. | `members/tests/` contains membership and kiosk policy coverage; add endpoint-specific tests when migrating. |
| Contact/profile privacy | Own profile fields are accessible to the subject. Privileged viewers include superusers, staff, selected legacy roles (`webmaster`, `treasurer`, `member_manager`, `rostermeister`), and configured `MEMBERS_REDACT_EXEMPT_GROUPS`. Other viewers follow subject preferences and club defaults. | A hidden field or legacy full-redaction setting denies ordinary viewers; profile field-policy and kiosk rules constrain self-service. | `members/utils/permissions.py`; `members/tests/test_contact_visibility.py`, `test_member_profile_policy_controls.py`, `test_kiosk_auth.py`. Staff and exempt Groups are a separate policy dimension, not a role mapping assumption. |
| Membership applications / waitlist | See endpoint matrix below: authenticated non-kiosk active-member gate (with a superuser nuance), then explicit view permission or legacy-role fallback for read; modification still requires member-manager or webmaster compatibility access. | GET and POST are not interchangeable; public applicant routes use different rules. | `members/views_applications.py`; `members/tests/test_membership_applications.py`, `test_membership_application_access_matrix.py`. These views do not use the general resolver yet. |
| Member profile administration and personal account actions | Self-service is governed by configured per-field profile policies. Superusers have several cross-member edit paths. | Non-self users are denied absent the relevant elevated access; account recovery is blocked in kiosk sessions. | `members/views.py`; `members/tests/test_member_profile_policy_controls.py`, `test_views.py`. Distinguish self-service from admin authorization. |
| Instructor records and training | Instructor-specific decorators require active membership plus the instructor boolean; instructor-or-safety paths require either role, with explicit superuser handling in one decorator. Several record views permit the subject member or an instructor. | Other users are denied; object ownership and member status remain contextual. | `instructors/decorators.py`, `instructors/views.py`; `instructors/tests/` includes instructor/safety/superuser cases. Multiple direct checks need a focused route-to-test map before migration. |
| Safety workflows | Safety-officer decorator permits superusers or active members with `safety_officer=True`. | Anonymous, inactive ordinary members, and members without the flag are denied. | `members/decorators.py`; `members/tests/test_safety_officer_interface.py`, `test_safety_dashboard.py`. |
| Duty roster management | Rostermeister-only endpoints check `rostermeister`; other endpoints also permit member-manager, director, staff, or superuser. Instructor self-service additionally checks the instructor flag and/or the user’s assignment to the relevant duty day/slot. | Some requests require being the assigned primary/surge instructor or the owner of an action; active-member and kiosk gates apply by endpoint. Current staff bypasses differ by endpoint. | `duty_roster/views.py`, `views_swap.py`; tests include `duty_roster/tests.py`, `test_roster_message.py`, volunteer and instruction-request tests. Do not flatten role eligibility, roster administration, and assignment ownership into one permission. |
| Logsheet / finance | Unfinalized logsheets can be edited by authenticated users who passed the surrounding active-member gate. Unfinalizing is allowed to superusers, treasurers, webmasters, or the duty officer who finalized the sheet. Some finalized split/correction actions allow the pilot or treasurer; finance and exports have additional owner/treasurer/stats-monger checks. | Finalized edits require the relevant unfinalize/correction policy; export jobs are restricted to their requester or superuser in some endpoints. Webmaster-only aircraft maintenance paths still include literal Group-name checks. | `logsheet/utils/permissions.py`, `logsheet/views.py`, `billing/permissions.py`, `billing/views.py`; `logsheet/tests/test_permissions.py`, finance and export tests. Preserve both broad role and per-logsheet ownership/context rules. |
| CMS view/edit | Public pages are public. Private pages require active membership or a kiosk exception, unless an edit grant makes the editor able to view. Page role restrictions use OR semantics over stored role values. Edit rights include superuser, director/secretary/webmaster, or a page-specific member grant. Webmaster can create top-level pages and edit homepage content. | A private restricted page denies a member who lacks every required role and lacks an editor grant. Per-member editor grants are object-specific and must remain separate from global roles. | `cms/models.py`, `cms/views.py`, `cms/admin.py`; `cms/tests/test_editing_permissions.py`, `test_access.py`, `test_parent_chain_access.py`, `test_subpage_creation.py`, `test_kiosk_cms_access.py`. CMS role-value migration is a distinct compatibility task. |
| Site configuration admin | Multiple ModelAdmin methods permit superusers or users in the literal `Webmasters` Group; selected membership/billing models also permit `Member Managers`. Other admin classes use Django model permissions or their own policy. | Users outside the relevant Group/permission set are denied. Admin visibility must not be treated as a substitute for checks on non-admin service/API operations. | `siteconfig/admin.py`; coverage is distributed among `siteconfig/tests/` and app admin tests. Inventory individual ModelAdmins before centralizing. |
| Knowledge tests | Several views allow staff, the student/attempt owner, assignment instructor, or test-template creator, depending on operation. Preset admin grants webmasters/superusers access; Chief Flight Instructor may add/change but not delete presets. | Non-owner/non-assignee ordinary users are denied; staff remains a distinct legacy override. | `knowledgetest/views.py`, `knowledgetest/admin.py`; `knowledgetest/tests/test_quiz_flow.py`, `test_knowledgetest.py`. The `Chief Flight Instructor` Group is not among the canonical role metadata mappings. |
| Billing operations | Manual reversal and financial workflows use superuser/treasurer or specific ownership/service policies. | Non-treasurer users cannot perform restricted corrections; member-ledger access is constrained to the subject unless separately authorized. | `billing/permissions.py`, `billing/views.py`; `billing/tests/test_manual_transactions.py`, `test_views.py`. |
| Analytics / exports | Analytics access commonly requires active membership; selected CSV/export endpoints require `stats_monger` or superuser, and export-job access is requester-scoped. | A different non-superuser cannot retrieve another user’s export job. | `analytics/views.py`; `logsheet/views.py`; `logsheet/tests/test_stats_dump_csv.py` and export tests. `stats_monger` is not a canonical role in the metadata seed. |
| Direct Django permissions | Canonical Groups carry Django permissions; the qualification backend grants explicitly approved global permissions while a valid qualification exists. The backend denies object permissions and gates grants on active membership. | Sensitive/admin permissions and standard CRUD prefixes are excluded from qualification grants. | `members/auth_backends.py`; `members/tests/test_qualification_permission_bundle.py`, `test_group_permissions_migration.py`. This is a narrow foundation mechanism, **not** a general authorization resolver: instructor/tow-pilot boolean eligibility and operational assignment eligibility are separate; future qualification-derived tags do not grant access. Existing app checks do not consistently call `has_perm()`. |

### Membership application management: endpoint-level first pass

All three routes are in `members/urls.py` and now use
`members.decorators.non_kiosk_member_required`: kiosk sessions receive 403
before the wrapped active-member gate. Other unauthenticated requests redirect
to login; authenticated non-kiosk users must pass
`members.utils.membership.is_active_member` (configured active status, with its
default superuser override) or receive 403. The view checks the explicit
`members.view_membership_applications` permission or legacy director/manager/
webmaster compatibility for read; modify still requires manager/webmaster
compatibility. `is_staff` alone is not a grant. Group membership grants read
only when its Group actually carries the view capability (e.g. Directors).
No ownership/assignment grant applies to these management
routes. There is no per-HTTP-method decorator on them; describe the observed
GET/POST branches below, not an exhaustive method contract.

In the matrix, **gate** means authenticated → login redirect if anonymous;
configured active status → 403 if inactive, except superuser passes
`is_active_member`; kiosk → 403 even with an allowed role flag. **Privilege** means
superuser passes the view-role check; `is_staff` alone does not. An explicit
view capability, direct or through a Group, grants read but not write. Kiosk
is not a role override. These facts apply independently
to *each* row and are repeated as compact column references for readability.

| Route / source | Method | Auth / active / kiosk | Superuser / staff | Legacy role | Object/context | Expected result | Existing tests | Planned policy and gaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `members:membership_applications_list` (`applications/`); `membership_applications_list`, `_can_view_membership_applications` | GET | Gate | Privilege | View capability OR `director OR member_manager OR webmaster` | `status`/`q` filters; `can_modify` computed separately | Reader 200; role-denied 403; anonymous 302; inactive account redirects at login gate | `test_management_get_access` covers staff, kiosk, view-only, Group-only and legacy roles | Review permission-derived read path alongside legacy checks. |
| `members:membership_applications_list`; same source | POST | Gate | Privilege | Same read check; **no write check** | No POST mutation branch: renders filtered list | Reader 200; role-denied 403, not automatically 405 | `test_list_post_uses_same_read_gate_as_get` covers staff, kiosk, view-only, and legacy roles | Preserve actual non-mutating behavior pending review. |
| `members:membership_application_detail` (`applications/<uuid:application_id>/`); `membership_application_detail`, `_can_view_membership_applications` | GET | Gate | Privilege | View capability OR director/manager/webmaster compatibility | Existing application UUID required (`get_object_or_404`); no ownership grant | Reader 200; role-denied 403; missing UUID 404 after role check | `test_management_get_access` covers anonymous, inactive, kiosk, staff-only, Group-only, view-only, ordinary, manager, webmaster and superuser | Review permission-derived read path and preserve object checks. |
| `members:membership_application_detail`; `membership_application_detail`, `_can_modify_membership_applications` | POST | Gate | Privilege | Read check, then `member_manager OR webmaster` for write; director alone read-only | Existing UUID; form/action and state govern `approve`, `waitlist`, `reject`, `need_info`, `save_notes` | Director 403/no mutation; permitted validated action redirects; missing UUID 404 after role check | `test_director_cannot_modify_application_review`, `test_approval_sends_account_setup_email_after_commit`, `test_save_notes_without_status_change`, `test_add_to_waitlist_already_waitlisted_keeps_position` | Preserve write gate, validations and side effects; test denied principal classes and positive webmaster/superuser POST for detail. |
| `members:membership_waitlist` (`applications/waitlist/`); `membership_waitlist`, `_can_view_membership_applications` | GET | Gate | Privilege | View capability OR director/manager/webmaster compatibility | Only `status="waitlisted"`, ordered by `waitlist_position`; `can_modify` separate | Reader 200; role-denied 403 | `test_management_get_access` covers principal/active/kiosk/staff/Group/view-only cases | Review permission-derived read path and preserve status-scoped read. |
| `members:membership_waitlist`; `membership_waitlist`, `_can_modify_membership_applications` | POST | Gate | Privilege | Read check, then `member_manager OR webmaster` for write; director alone read-only | Requires `action` and `application_id`; target must be waitlisted, positions/action determine mutation | Director 403/no reorder; permitted move redirects; absent/no-op action redirects without reorder | `test_director_cannot_reorder_waitlist`, `test_waitlist_move_to_top`, `test_waitlist_move_to_bottom`, `test_webmaster_and_superuser_can_view_and_modify_waitlist` | Preserve waitlisted-target check/non-mutating no-ops; test other denied classes and non-mutation. |

`members/tests/test_membership_application_access_matrix.py` now exercises the
listed routes and both method branches across ordinary, director, manager,
webmaster, superuser, staff-only, Group-only, view-only, anonymous, inactive-manager, and
kiosk principals. **Maintainer migration note (approved policy change):** before
the `non_kiosk_member_required` change, a kiosk-authenticated Role Account with
`member_manager=True` could view application details and POST changes to review
notes: `active_member_required` bypassed the membership-status gate and the
view's role-flag check still passed. The new decorator rejects kiosk sessions on
all three management routes, even if the underlying account has director,
manager, webmaster, or superuser flags. This intentionally narrows access and
must be called out when the patch is merged/deployed. The public application
submission and applicant-status/withdrawal routes were not changed.

Related **public** routes are not the management policy: `members:membership_application`
(`membership_application`) allows anonymous GET/POST only when the feature is
enabled and redirects logged-in users; `members:membership_application_status`
(`membership_application_status`) exposes limited status by application UUID and
allows POST withdrawal only for pending/under-review/additional-info-needed
applications (`members/views_applications.py`). Their own access/privacy review
is required before changing them. The named tests above include
baseline additions in `test_membership_applications.py`; presence of tests is
not baseline approval.

### Current resolver foundation contract (not wired to these routes)

`members.authorization.resolve_authorization(user, permission, *, context_allow,
require_active_member, kiosk_authenticated, allow_kiosk_membership_bypass)`
returns `AuthorizationDecision(allow, reason)`. Its reason identifies the first
failed account/membership gate or the global/contextual grant used; it is not
an audit event. The caller supplies trusted kiosk context and computes any
object-owner/assignment grant for the specific action. The resolver delegates
global permissions to `user.has_perm()` (including the narrow, expiry-aware
qualification backend). It never infers permission from legacy flags, changes
Group memberships, caches its own result, or grants preview access. Django's
ordinary user/Group permissions may be cached on a `Member` instance; after
mutating those grants, use a fresh instance or invalidate Django's caches.

This API is only a **foundation contract**. No migration may assume it covers
every operational action: the target permission codenames need an explicit
positive allowlist; ownership and assignment checks belong to domain policies;
later preview must supply a separate effective principal rather than inherit
the administrator's grants. Audit writes belong at grant/mutation services,
not in this read-only resolver. A corresponding endpoint matrix and parity
tests are required before replacing a legacy check.

## Baseline allow/deny matrix

This is a coarse, **not yet approved** behavior matrix for the principal identity types. “Contextual” means
access depends on the resource, request, assignment, configured policy, or the
specific endpoint; it is not a blanket grant.

| Identity / condition | Active-member pages | Role-restricted operation | Object/assignment action | CMS view/edit | Admin / Django permission |
| --- | --- | --- | --- | --- | --- |
| Anonymous | Deny; login redirect or public-only surface | Deny | Deny except explicit public/token workflow | Public view allowed; private/edit denied | Deny |
| Active ordinary member | Allow where active-member gate is the only policy | Deny unless endpoint is self-service or contextual policy allows | Allow only own/assigned/object-specific action | Private unrestricted page view allowed; restricted page requires any configured role; edit requires explicit editor/officer policy | Django permissions inherited through user/group assignments and eligible active qualification bundles apply; legacy role booleans alone do not necessarily imply `has_perm()` |
| Inactive non-superuser | Deny on active-member-gated surfaces | Normally deny; endpoint-specific ungated checks require review | Deny unless explicit public/token exception | Private page denied except kiosk or explicit page-editor behavior; public remains public | Verify per endpoint and backend; qualification-derived grants are denied |
| Member with relevant legacy role | Pass active-member gate and the specific role check, subject to any other policy | Allow only actions currently keyed to that role (e.g. treasurer correction, webmaster edit, instructor flow) | Still subject to ownership/assignment checks where present | Role restriction uses role-field truth; editor role or member grant can imply view | Group permissions apply independently; role fields alone do not imply Django `has_perm()` |
| `is_staff=True`, not superuser | Not a universal bypass | Allowed only where code explicitly tests staff (notably knowledge tests, contact privacy, some roster surfaces) | Contextual; staff does not imply object ownership | No general CMS override | Django admin access still depends on active/staff and model permissions; exact custom Admin overrides vary |
| Superuser | Passes `is_active_member` by default; verify endpoint-specific gates | Usually override, but not every endpoint is identical | Often override, but object/HTTP rules may still apply | Can edit; private-page view and route-level active-member behavior still vary | Broad Django override and bootstrap role administration |
| Kiosk session | May bypass membership status on explicit kiosk-aware gates | No general role grant | Must not gain account takeover or unrelated mutation rights | Can view member content on configured CMS paths; not a CMS edit grant | No general admin grant |
| Explicit page editor / assigned operator | Depends on active-member and endpoint gate | Does not imply unrelated role authority | Allows only the scoped page/assignment action | Page editor can also view that page; no global role implied | No global Django permission implied |

## Important classification: authorization versus eligibility/audience

The search also finds role-field usage that is not itself an access-control
decision. Keep these categories separate when replacing booleans:

- **Operational eligibility:** instructor/tow-pilot/duty-officer qualification
  used to select a participant, assign a schedule slot, validate a flight, or
  determine duty-roster availability (`logsheet/eligibility.py`, logsheet forms,
  `duty_roster` role-resolution and scheduling code).
- **Ownership/context:** checking whether the requester is the pilot, assigned
  instructor, creator, or object-specific editor.
- **Audience/notification routing:** querying role-flagged users to send mail or
  notifications. These recipient sets are not permissions. Mailing-list role/tag
  selectors are additive; existing boolean criteria remain in effect. A role
  selector uses actual Group membership, never a qualification or an operational
  assignment unless that membership has separately been granted.
- **Presentation/discovery:** role labels, badges, filters, counts, navigation,
  and button visibility. UI visibility does not replace server authorization.
- **Data synchronization/import:** `Member._sync_groups`, member imports, and
  migrations transform or reconcile data; they are not request authorization.

Before changing any such use, identify the correct domain abstraction (for
example, qualification, operational assignment, audience topic, or role key).
Do not mechanically replace every `member.instructor` read with
`user.has_perm(...)`.

## Known legacy inconsistencies and migration risks

1. **`is_staff` has multiple meanings.** It is a Django admin gate in some
   contexts and an application-role shortcut in others. Replacing it globally
   with a business role would change access.
2. **Role fields and Groups can disagree.** Some authorization uses fields,
   some uses Groups, and some member/admin flows reconcile the two. Stable role
   metadata does not itself make those checks consistent.
3. **Role names are not a complete permission catalog.** Examples outside the
   seeded roles include `stats_monger`, `duty_officer`, `Chief Flight
   Instructor`, and dynamic duty roles.
4. **Active-member checks are not uniform.** Some policies explicitly wrap role
   checks in active-member gates; others rely on authentication or object
   ownership. Preserve endpoint-by-endpoint behavior until the baseline is
   reviewed.
5. **CMS has stored values and object permissions.** Preserve old role values,
   OR behavior, public/private rules, kiosk exception, editor-implied-view, and
   per-member grants during any stable-key conversion.
6. **UI checks can hide actions without protecting endpoints.** Verify both the
   underlying view/service and the display condition for every migrated surface.
7. **Provenance is not yet authoritative for arbitrary direct Group edits.**
   Member admin removes `groups` from the ModelForm's `cleaned_data` while
   `save_m2m()` runs and routes each selected change through
   `set_manual_role(..., source_key="admin")`. That transactional service grants
   or revokes only the exact manual source and preserves every other assignment
   reason for the Group. `Member._sync_groups()` remains the writer for legacy
   role-field sources. Direct `member.groups.add/remove/set/clear` calls and
   through-table writes elsewhere still bypass provenance and are unsupported.
   Do not authorize using assignment rows as the sole source until those direct
   writes have an agreed enforcement or migration policy.

## Test baseline map

Start with these existing focused suites when a surface is migrated:

- Shared membership, profile, and privacy: `members/tests/test_views.py`,
  `test_member_profile_policy_controls.py`, `test_contact_visibility.py`,
  `test_kiosk_auth.py`, `test_membership_applications.py`.
- Instructor and safety: `instructors/tests/`,
  `members/tests/test_safety_officer_interface.py`,
  `members/tests/test_safety_dashboard.py`.
- Duty roster: `duty_roster/tests.py`,
  `duty_roster/tests/test_roster_message.py`,
  `test_instruction_request_ui.py`, and the volunteer/role tests.
- Logsheet/billing: `logsheet/tests/test_permissions.py`, finance and
  commercial-ticket tests, `billing/tests/test_manual_transactions.py`,
  `billing/tests/test_views.py`.
- CMS: `cms/tests/test_editing_permissions.py`, `test_access.py`,
  `test_parent_chain_access.py`, `test_subpage_creation.py`,
  `test_kiosk_cms_access.py`.
- Knowledge tests: `knowledgetest/tests/test_quiz_flow.py` and
  `test_knowledgetest.py`.
- Role Group/permission migration and qualification grants:
  `members/tests/test_group_permissions_migration.py`,
  `test_role_metadata.py`, `test_role_assignments.py`, and
  `test_qualification_permission_bundle.py`.

## Next work

### Approved policy decisions

- `is_staff` is not a universal application bypass. Existing staff-enabled
  endpoints will be migrated to explicit new permissions/resolver checks while
  preserving their endpoint-specific behavior.
- Existing `is_superuser` behavior remains as close as possible to the current
  deployment during this work. It is not expanded into a universal bypass,
  and superuser-specific details are deferred for maintainer review. The role
  inventory should document current superuser behavior rather than redesign it.
- Inactive members retain their Groups and assignment records, but lose the
  effective ability to use those permissions. They cannot log in under the
  existing inactive-account policy, and direct authorization evaluation must
  deny their effective role/qualification permissions as well. Existing
  superuser behavior matches current behavior for now; the direct-evaluation
  edge case is explicitly deferred for later review.
- The assignment service is authoritative for new supported Group writes.
  Existing unexplained/manual memberships remain valid until explicitly
  reviewed; they are not silently removed during enforcement.
- Qualification-derived permissions use a positive allowlist. Permissions are
  not granted merely because a codename appears safe. Admin/authentication,
  member-management, qualification-management, broad management,
  impersonation, and export permissions remain excluded unless separately
  approved.
- The target is current intended-behavior parity with narrower, composable
  roles. Existing Groups should be decomposed into focused capabilities that
  can be combined or added independently. Preserve legitimate current access,
  but do not preserve accidental access caused only by broad legacy Groups or
  generic `is_staff` checks. Member Manager permissions should represent the
  current membership-management job, while unrelated staff-derived access is
  represented separately.

The remaining major policy gate is the global-versus-contextual resolver
contract. The inactive-superuser direct-evaluation edge case is also recorded
for later review.

1. Review and approve a completed baseline against product intent, especially staff, superuser,
   dynamic operational roles, and staff-only admin behavior.
2. Expand the matrix into endpoint-level allow/deny tests where behavior is
   currently undocumented or untested.
3. Review and approve the implemented shared resolver contract for global
   permissions versus caller-supplied contextual grants. Keep ownership, kiosk,
   active membership, and qualification validity explicit rather than implicit
   role grants.
4. Migrate a bounded first slice only after its exact checks and endpoint-level
   allow/deny tests are accepted; compare
   before/after allow and deny results before proceeding to other subsystems.
