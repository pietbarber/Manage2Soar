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
| Request approval | The member submits a change request; a member manager must approve it before it updates the profile. |

Staff-created information requests are different from member-created change
requests: valid member responses to staff requests apply automatically. A staff
request asking for an email address is the exception: the new email remains
pending until the member verifies it.

Password and profile-photo changes support only `disabled` and `direct`.
Passwords must never be retained in a request record, and uploaded photos need
an explicit attachment workflow before approval requests can be supported.

### Supported Data

* Structured emergency contacts are the source of truth; legacy free-text data
  remains display-only during migration.
* Contact visibility applies independently to email, phone, and postal address.
* The same visibility decision is used by profile pages, directory output,
  vCards, and QR contact cards.
* Profile requests retain the requested fields, submitted values, status,
  source, reviewer, timestamps, and audit events.

## Phase 0: Stable Baseline

1. Repair PostgreSQL collation metadata so Django can create `test_manage2soar`.
2. Land this contract and the test matrix below.
3. Run the profile test suite on a clean `upstream/main` worktree.

### Database Administrator Runbook

The local PostgreSQL databases report collation version `2.43` while the
operating system provides `2.44`. An administrator must reindex affected
databases before refreshing their collation metadata. Schedule this outside
active use because `REINDEX DATABASE` takes locks.

```bash
sudo -u postgres psql -d template1 -c "REINDEX DATABASE template1;"
sudo -u postgres psql -d postgres -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;"
sudo -u postgres psql -d manage2soar -c "REINDEX DATABASE manage2soar;"
sudo -u postgres psql -d postgres -c "ALTER DATABASE manage2soar REFRESH COLLATION VERSION;"
sudo -u postgres psql -d postgres -c "REINDEX DATABASE postgres;"
sudo -u postgres psql -d postgres -c "ALTER DATABASE postgres REFRESH COLLATION VERSION;"
```

Afterward, run:

```bash
.venv/bin/pytest members/tests -q
```

## Phase 1: Data Foundation

1. Add the `EmergencyContact` model and application-to-member mapping.
2. Add per-field `Member.contact_visibility` data.
3. Add site policy storage and safe defaults.
4. Write data migrations and legacy fallbacks.

Verification gate:

* Migrations apply cleanly to a copy of production-like data.
* Legacy emergency-contact text remains visible.
* Model and migration tests pass.

## Phase 2: Emergency Contacts

1. Render structured contacts with click-to-call links.
2. Implement direct add, edit, and remove flows.
3. Require `NO EMERGENCY CONTACT` before removing the final contact.
4. Support approval requests for member-originated contact changes.
5. Ensure an approved edit updates its target contact rather than duplicating it.

Verification gate:

* Add, edit, remove, final-contact decline, direct, and request-policy tests pass.

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

## Phase 4: Information Request Workflow

1. Build staff request list, create, detail, and review screens.
2. Build member action-needed indicators and a response screen.
3. Add audit events, due dates, overdue reminders, and manager notifications.
4. Make valid staff-request responses apply automatically.
5. Keep member-originated approval requests pending until manager completion.

Verification gate:

* Tests cover requested, submitted, completed, declined, rejected, cancelled,
  and overdue statuses.
* Applying a request is idempotent.

## Phase 5: Field-by-Field Policy Integration

Integrate one field at a time. Do not start the next field until all three
applicable policy modes pass their tests.

Order:

1. Username
2. Phone
3. Address
4. Nickname
5. Emergency contacts
6. Contact visibility
7. Biography
8. Email verification
9. Profile photo and password direct/disabled controls

## Phase 6: Username Completion

1. Validate format, uniqueness, and no-op submissions.
2. Make request-policy UI explicitly say `Request Username Change`.
3. Auto-complete valid staff-requested username changes.
4. Send distinct security emails to the member and active member managers on
   every completed username change.

Verification gate:

* Direct, request, disabled, staff-requested, approval, email-recipient, and
  no-op tests pass.

## Test Matrix

| Area | Required checks |
| --- | --- |
| Every policy field | disabled control and endpoint rejection; direct update; request remains pending |
| Staff request | valid response applies once; invalid response stays open |
| Member request | submission does not alter source data; manager approval applies once |
| Privacy | profile, directory, QR, and vCard agree; hidden data is absent from markup |
| Emergency contacts | add, edit, remove, final decline, request approval, no duplicate on edit |
| Username | format, collision, no-op, each policy, audit events, member and manager email |
| Email | verification token, expiry, resend, old address unchanged until verification |
| Notifications | recipient set, URL, duplicate suppression where required, command idempotence |

## Delivery Rules

* One phase per branch and pull request.
* One acceptance checklist per phase.
* One focused test module per behavior, not only manual shell checks.
* No unrelated formatting, cleanup, or media-path changes in profile-work PRs.
* Update the project graph after each completed phase.
