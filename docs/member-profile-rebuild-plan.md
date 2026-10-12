# Member Profile Rebuild Plan

This plan replaces the current incremental profile work with a dependency-ordered
implementation from `upstream/main`. Each phase is independently reviewable and
must meet its verification gate before the next phase begins.

## Product Contract

### Field Policies

Each supported member-editable field has one policy:

| Policy | Member behavior |
| --- | --- |
| Disabled | No member control is shown; direct endpoint access is rejected. |
| Direct | A valid submitted value updates the profile immediately. |

The rebuild supports only `disabled` and `direct`. A stored `request` policy is
reserved for future investigation; no member-manager approval workflow is part
of this rebuild.

Email is the exception to immediate persistence: a direct email change is held
in `pending_email` with `pending_email_requested_at` until the member verifies
the new address.

Password and profile-photo changes support only `disabled` and `direct`.
Passwords must never be retained in a request record, and uploaded photos need
an explicit attachment workflow before approval requests can be supported.

### Supported Data

* Structured emergency contacts are the source of truth; legacy free-text data
  remains display-only during migration. Admin/member management and structured
  export operate on `EmergencyContact` records.
* Contact visibility applies independently to email, phone, and postal address.
  An omitted key is the effective `inherit` state; explicit `share` and `hide`
  values override the site defaults.
* The same visibility decision is used by profile pages, directory output,
  vCards, and QR contact cards.
* Profile changes in this rebuild use direct or disabled policies; no
  member-created approval-request record or manager-review workflow is required.

## Phase 0: Stable Baseline

1. Land this contract and the test matrix below.
2. Run the profile test suite on a clean `upstream/main` worktree.

## Phase 1: Data Foundation

1. Add the `EmergencyContact` model and application-to-member mapping.
2. Add per-field `Member.contact_visibility` data.
3. Add contact-sharing defaults and direct/disabled profile policies to site configuration.
4. Write data migrations and legacy fallbacks.

Verification gate:

* Migrations apply cleanly to a copy of production-like data.
* Legacy emergency-contact text remains visible.
* Model and migration tests pass.

## Phase 2: Emergency Contacts

1. Render structured contacts with click-to-call links.
2. Implement direct add, edit, and remove flows, including admin management.
3. Require `NO EMERGENCY CONTACT` before removing the final contact.
4. Ensure an edited contact updates its target record rather than duplicating it.

Verification gate:

* Add, edit, remove, final-contact decline, direct, and disabled-policy tests pass.

## Phase 3: Contact Privacy and Contact Cards

1. Add site defaults and member overrides for email, phone, and address.
2. Apply the shared visibility decision to profile and directory pages.
3. Ensure hidden email addresses do not appear in HTML attributes or JavaScript
   data.
4. Add vCard and QR contact-card output using the same decision.
5. Add staff-only explanation of a member's effective visibility.

Verification gate:

* Role-based tests cover member, privileged staff, and public directory output.
* Rendered HTML and vCards contain no hidden values.

## Phase 4: Field-by-Field Policy Integration

Integrate one field at a time. Do not start the next field until both supported
policy modes pass their tests.

Order:

1. Phone
2. Address
3. Nickname
4. Emergency contacts
5. Contact visibility
6. Biography
7. Email verification
8. Profile photo and password direct/disabled controls

## Test Matrix

| Area | Required checks |
| --- | --- |
| Every policy field | disabled control and endpoint rejection; direct update |
| Privacy | profile, directory, QR, and vCard agree; hidden data is absent from markup |
| Emergency contacts | structured add, edit, remove, admin management, final decline, no duplicate on edit |
| Email | verification token, expiry, resend, old address unchanged until verification |
| Notifications | recipient set, URL, duplicate suppression where required, command idempotence |

## Delivery Rules

* One phase per branch and pull request.
* One acceptance checklist per phase.
* One focused test module per behavior, not only manual shell checks.
* No unrelated formatting, cleanup, or media-path changes in profile-work PRs.
* Update the project graph after each completed phase.

## Out Of Scope

* Username self-editing is deferred for future investigation.
* Member-manager approval workflows and request-policy behavior are deferred;
  this rebuild does not implement them.
* Global email uniqueness is not enforced. Existing upstream behavior allows
  multiple member accounts to share an email; any change requires separate
  investigation across login, reset, imports, and visiting-pilot lookup.
