# Billing Development Plan

This plan implements the requirements in
`Member_Account_Implementation_Specification.md` without moving flight pricing
out of `logsheet`.

## Phase 1: Establish the Boundary

Goal: make the ownership between Logsheet and Billing explicit before adding
financial data.

- Identify the existing member-charge calculation and all callers.
- Define the Logsheet allocation result used by Billing.
- Define stable source identity and allocation version rules.
- Identify every logsheet finalization entry point.
- Identify miscellaneous and non-flight charge sources.
- Add contract tests around the current two-member allocation results,
  including deterministic rounding. Define the extension contract for future
  arbitrary percentage splits and multiple payers.

Exit criteria:

- One documented allocation API returns billed members and calculated amounts.
- Existing charge behavior is covered by tests.
- No Billing code calculates flight prices.

## Phase 2: Build the Ledger Core

Goal: store and manage immutable financial transactions.

- Add ledger and ledger-entry models.
- Add debit/credit and entry-type constraints.
- Add source identity uniqueness.
- Add reversal relationships.
- Add transactional posting, balance, and reversal services.
- Add model and service tests for invalid entries, duplicate posting,
  concurrent posting, and reversal behavior.

Exit criteria:

- A ledger can record a charge, payment, credit, and reversal.
- Balances are derived from entries.
- Posted entries cannot be edited or deleted through normal application paths.

## Phase 3: Integrate Finalization

Goal: record Logsheet-calculated charges exactly once when a logsheet is
finalized.

- Create one shared finalization service.
- Move all finalization callers to that service.
- Freeze the calculated allocation before posting.
- Post one transaction per billed member using the opaque Logsheet source key.
- Preserve each billed member's allocated amount and percentage when multiple
  payers or arbitrary percentage splits are used.
- Make finalization and ledger posting atomic.
- Make retries idempotent.
- Prevent finalized source edits from silently changing posted transactions.
- Correct a flight through its complete replacement allocation, reversing every
  active prior charge and grouping the resulting reversal/replacement rows.

Exit criteria:

- Every finalization path uses the shared service.
- A failed posting leaves the logsheet and ledger unchanged.
- Retrying finalization does not duplicate charges.
- Existing Logsheet cost tests remain green.

## Phase 4: Add Manual Staff Transactions

Goal: allow authorized staff to manage transactions that do not originate from
a flight.

- Add staff posting for manual charges, payments, credits, and opening
  balances.
- Require descriptions and reasons where appropriate.
- Reuse the same posting and audit services as automatic charges.
- Add server-side treasurer/superuser authorization.

Exit criteria:

- Staff can post and reverse manual transactions.
- Non-staff cannot post or reverse transactions.
- Every mutation records actor, timestamp, description, and reason.

## Phase 5: Member and Staff Views

Goal: expose trustworthy balances without leaking financial data.

- Update My Flight Charges to read the ledger.
- Show due and credit states, entries, and running balances.
- Preserve the current route where practical.
- Add staff member search and ledger detail views.
- Add member and staff CSV exports.
- Protect exports against spreadsheet formula injection.

Exit criteria:

- Members see only their own ledger.
- Staff permissions are enforced on every read and mutation.
- Internal notes never appear in member output.

## Phase 6: Migration and Reconciliation

Goal: transition existing charge history without inventing balances.

- Select a cutoff date and authoritative opening-balance source.
- Implement dry-run and committed migration commands.
- Match members by stable ID and report ambiguity.
- Import opening balances and post-cutoff source charges with stable keys.
- Reconcile every member against the old report and authoritative balances.
- Keep the old calculated report available to staff during rollout.

Exit criteria:

- Dry runs write nothing.
- Repeated committed runs create no duplicates.
- Every member has a reconciliation result.
- Staff sign off on unexplained differences before ledger-only reads are
  enabled.

## Phase 7: Harden and Remove Transitional Paths

Goal: make the ledger the reliable financial record.

- Add reconciliation and health checks for missing, duplicate, or broken
  source relationships.
- Update commands that mutate finalized flight costs to skip or use correction
  workflows.
- Remove or restrict direct finalized-state mutations.
- Add database-level safeguards for posted-entry immutability where supported.
- Retain only the source and correction paths defined by the requirements.

Exit criteria:

- All acceptance tests pass.
- No known finalization or mutation path bypasses the ledger contract.
- The old calculated financial view is retired or clearly limited to
  reconciliation.

## Deferred Work

Do not add these while implementing the MVP:

- Online payment providers.
- Stored payment credentials.
- Guest cash/check custody and remittance.
- Non-member receivables and invoice aging.
- Member self-service allocation changes after finalization.

Each deferred feature requires separate requirements and must preserve the
Logsheet pricing/Billing transaction boundary.
