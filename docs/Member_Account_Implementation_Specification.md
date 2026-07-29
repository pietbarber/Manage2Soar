# Member Billing Requirements

## 1. Purpose

Manage2Soar needs one reliable answer to a simple question:

> What does this member currently owe the club, or have as a credit?

The billing feature is a member ledger. It records charges and money received,
shows the resulting balance, and gives authorized staff an auditable way to
correct mistakes.

The system has a strict boundary between pricing and bookkeeping. The
`logsheet` domain is the authority for calculating what a flight costs and how
that cost is allocated. The ledger does not calculate tow, rental,
instruction, split, rate, or other flight prices. It records the transaction
that `logsheet` has already calculated and manages its financial history.

This document defines the behavior required for that outcome. It deliberately
does not prescribe Django models, URL names, migrations, or a particular
payment provider.

## 2. First Principles

1. A balance is derived from a history of financial events, not stored as an
   independently editable number.
2. `logsheet` is the sole authority for flight pricing and allocation. Billing
   consumes its results and never duplicates its rules.
3. A posted financial event is permanent. Mistakes are corrected by a new,
   linked event rather than by editing history.
4. Every event must explain who created it, when it was created, why it exists,
   and what source activity caused it when applicable.
5. Operational data and financial data are related but not interchangeable.
   A flight may be corrected operationally, but a posted charge must remain
   historically accurate.
6. The same source activity must never create the same transaction twice.
7. Members may see only their own financial history. Staff access is explicit
   and role-controlled.
8. The first release should solve member balances well. It should not become a
   general accounts-receivable, payment-processing, or guest-settlement system.

## 2.1 Tenant Billing Activation

Billing is tenant-configurable through `SiteConfiguration.billing_app_enabled`
(default `False`).

When the flag is disabled:

- Billing ledger staff views are redirected and hidden from navigation.
- Member personal charge history endpoints are redirected.
- Ledger mutation services reject writes.
- Logsheet finalization still completes operationally, but skips cost freezing
  and ledger posting.

When enabled, all MVP behaviors in this document apply.

## 3. MVP Outcome

The MVP must provide:

- A member-facing balance and billing history.
- Automatic charges from finalized member flight activity.
- Manual charges, payments, and credits entered by authorized staff.
- Reversals and replacement entries for corrections.
- A staff view for finding members, reviewing ledgers, and posting entries.
- CSV export for members and staff.
- A migration path from the existing personal-charge history.
- Reconciliation tools and tests that prove the balance is trustworthy.

The MVP does not include online payment processing, stored payment credentials,
invoice aging, payment allocation to invoices, or a full non-member receivables
system.

## 4. Terms

**Ledger**: The financial history for one member.

**Entry**: One posted financial event in a ledger.

**Charge**: A debit that increases the member's amount due.

**Payment**: A credit representing money received for the member.

**Credit**: A credit that is not a payment, such as an approved adjustment.

**Reversal**: A new entry that exactly cancels a prior entry.

**Balance**: The signed sum of all posted entries through a selected date.
Positive means the member owes money. Negative means the member has a credit.

## 5. Ledger Rules

Each member has at most one ledger. A ledger entry has, at minimum:

- Member ledger.
- Entry type: flight charge, miscellaneous charge, manual charge, payment,
  credit, opening balance, or reversal.
- Positive monetary amount.
- Debit or credit direction.
- Effective date.
- Member-visible description.
- Creator and creation timestamp.
- Optional source reference, such as a flight or existing charge.
- Optional internal staff note.
- Optional correction/reversal relationship.

The system must enforce:

- Amounts are positive and currency is rounded consistently.
- A charge cannot be recorded as a credit, and a payment/credit cannot be
  recorded as a debit.
- A reversal has the opposite direction and same amount as its original.
- An entry cannot be edited or deleted after posting through the application.
- A source event cannot be posted twice.
- A reversal cannot be created twice for the same original entry.
- Balance calculation is deterministic and includes all history by default.

Database constraints and transactional services should enforce these rules;
view validation alone is insufficient.

## 6. Flight Charges

When a daily logsheet is finalized, the system posts the member charges that
the existing logsheet cost-allocation logic has calculated.

Requirements:

- Finalization and charge posting succeed or fail together.
- Recording is idempotent and safe to retry.
- Existing tow, rental, instruction, rate, and split calculations remain in the
  logsheet domain. Billing receives the calculated member allocation as an
  input and records it without recalculating or changing the amount.
- A split flight produces one charge for each billed member.
- Arbitrary percentage splits and multiple payers are supported whenever the
  Logsheet allocation service provides them.
- The posted transaction preserves the source flight and the calculated amount
  needed to explain and reconcile it. Any component detail comes from the
  logsheet result; billing must not derive a second component breakdown.
- Commercial and non-member activity remains outside the MVP unless an active
  member is explicitly the payer.
- A posted flight charge is not changed when source fields are later edited.
  A correction creates a reversal and replacement entry.

There must be one domain-level finalization path. UI actions, commands, admin
actions, imports, and APIs must not be able to finalize a logsheet around that
path.

### 6.1 Logsheet Integration Requirements

The ledger depends on `logsheet` for flight pricing. The following requirements
define the boundary between the two domains.

`logsheet` must provide one canonical allocation service that returns the
calculated billing input for a flight. For each billed member, the result must
include:

- Flight ID and billed member ID.
- Total amount to record.
- Tow, rental, and instruction components when those components exist in the
  calculation result.
- The applied split or allocation rule.
- The payer set and each payer's percentage or allocated amount when multiple
  payers or arbitrary percentage splits are used.
- A calculation/allocation version.
- A stable source identity for idempotent recording.

For the current MVP, Logsheet supports the existing two-member `even`, `tow`,
`rental`, and `full` allocation modes. Arbitrary percentages and more than two
payers require a Logsheet allocation-model extension before Billing consumes
them.

The allocation service must be the sole authority for flight pricing. Billing
must consume its result and must not recalculate tow, rental, instruction,
rates, splits, rounding, or other flight costs.

The allocation service must use deterministic currency quantization. Component
amounts must reconcile to the total amount, and an intentional zero charge
must be distinguishable from a missing or invalid calculation.

Finalization must use one domain service across every entry point, including
views, admin actions, management commands, imports, and APIs. The service must
calculate and freeze the final allocation before asking billing to record it.
Finalization and the required ledger transactions must succeed or fail as one
database transaction. Retrying the service must not create duplicate
transactions.

Once a transaction has been recorded, the source pricing inputs must not be
casually changed. Changes to finalized pricing inputs, participants, aircraft,
rates, or flight data require an explicit correction workflow. That workflow
must provide the prior and replacement allocation, preserve the calculation
version, and allow billing to record a reversal and replacement without
editing the original transaction.

`logsheet` must expose existing non-flight charge sources, including
miscellaneous charges and towplane-related charges, through stable source
records. Billing must be able to identify whether each source has been posted
without guessing or posting the same charge twice.

The Logsheet test suite must cover the current two-member allocation modes,
deterministic rounding, zero charges, missing calculations, stable source
identities, retries, and correction results. Tests for arbitrary percentage
splits and multiple payers are required when that Logsheet allocation-model
extension is introduced. Existing member-charge behavior must remain covered
while the ledger is introduced.

Logsheet owns allocation version and source-key generation. Each allocation
result supplies an opaque, stable source key; Billing stores and validates that
key but does not construct its format.

## 7. Manual Entries

Authorized billing staff may post:

- Manual charges.
- Payments received for a member.
- General credits.
- Opening balances during migration.

Every manual entry requires a member-visible description. Charges and credits
require an internal reason. Payments may record a method and reference, but
the MVP records the payment; it does not verify or process the payment through
an external provider.

Manual entries must use the same ledger service and audit rules as automatic
flight transactions. Manual entry is the only MVP case where an authorized
staff member supplies the amount directly; flight amounts always come from
`logsheet`.

## 8. Corrections

Posted entries are history. Staff must not edit them to repair a mistake.

A correction must:

- Identify the original entry.
- Record the authorized actor, timestamp, and reason.
- Post an exact reversal.
- Post a replacement entry when the corrected event still exists.
- Preserve links between the original, reversal, and replacement.
- Complete atomically or make no change.

A flight correction receives the complete replacement allocation for that
flight, reverses every active flight charge that it supersedes, and posts every
replacement charge atomically. Reversals and replacements from one correction
share a durable correction-group identifier, including when the payer set
changes.

Unfinalizing a logsheet must not silently alter posted billing history. If an
operational correction changes a posted charge, it must use the same audited
correction workflow.

Existing commands that update finalized flight costs must either skip posted
flights or call the correction workflow.

## 9. Member Experience

The existing My Flight Charges area becomes the member's billing history.
It must show:

- Current balance.
- Clear due or credit state.
- Effective date.
- Category.
- Description.
- Debit and credit amounts.
- Running balance.
- Related flight reference when safe to display.

Members may view and export only their own ledger. Internal notes, staff-only
metadata, and other members' financial data must never appear in member views
or exports.

The initial release should preserve the existing route where practical to avoid
breaking bookmarks and training material.

## 10. Staff Experience

Treasurers and superusers may:

- Search members.
- View a member's complete ledger and balance.
- Post manual charges, payments, and credits.
- Reverse entries with a required reason.
- Export ledger data.
- Run reconciliation reports.

Authorization must be checked server-side for every read and mutation. A valid
form or altered URL must not bypass it.

The system should use the existing configurable treasurer-role mechanism rather
than hard-coding a display title or username.

## 11. Migration

Migration cannot invent a trustworthy balance from only the current 365-day
display.

Before implementation, the club must identify:

- A cutoff date.
- The authoritative opening balance for each member, including zero where
  appropriate.
- The source of historical miscellaneous charges.
- The person responsible for reconciliation sign-off.

The migration must support:

- Dry-run reporting with no writes.
- Deterministic, rerunnable imports.
- Stable member matching; never silently fuzzy-match names.
- Row-level errors and duplicate/ambiguous member reports.
- Reconciliation of every member's opening balance plus post-cutoff activity.

During rollout, new finalized activity must not be missed or duplicated while
historical data is being imported. The old calculated report should remain
available to staff until reconciliation is complete.

## 12. Reliability and Security

- Ledger mutations use database transactions.
- Concurrent duplicate posting cannot double-charge a member.
- Concurrent reversal cannot reverse an entry twice.
- Source and ledger identifiers are included in structured logs; sensitive
  payment details are not.
- CSV exports protect against spreadsheet formula injection.
- Sensitive files and secrets are never copied into ledger descriptions or
  logs.
- The system provides a health/reconciliation check for duplicate sources,
  broken reversal links, missing sources, and balance mismatches.

## 13. Minimum Acceptance Tests

1. A $100 charge produces a $100 due balance.
2. A $60 payment reduces that balance to $40.
3. A $50 credit changes a $40 due balance to a $10 credit.
4. A finalized flight posts each billed member's calculated charge exactly once.
5. Retrying finalization does not create another charge.
6. A failed finalization leaves both the logsheet and ledgers unchanged.
7. A correction leaves the original entry intact and creates a linked reversal
   and replacement.
8. Members cannot read or mutate another member's ledger.
9. Non-staff cannot post or reverse entries.
10. Direct attempts to edit or delete posted entries are rejected.
11. Migration dry runs write nothing and committed reruns create no duplicates.
12. Reconciliation identifies a missing, duplicate, or mismatched source entry.

## 14. Deferred Decisions

The following require separate requirements if they become part of a later
release:

- Online payment verification or provider integration.
- Member-held guest cash/check custody and remittance.
- Non-member settlement and receivables.
- Invoice and aging workflows.
- Member self-service changes to shared-flight allocation after finalization.
- Cached balances and high-volume accounting reports.

These features must not complicate the MVP ledger or weaken its audit rules.

## 15. Launch Gate

The ledger is not authoritative until the member and staff views, server-side
staff authorization, CSV protections, migration/reconciliation tooling, and
health checks in this document are complete and accepted. Until then, it is an
internal dual-write record used for validation.
