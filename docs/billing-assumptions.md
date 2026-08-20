# Billing Assumptions

This document records the working assumptions for billing issue #981 and its
open billing work. Agents should use these rules unless a later decision
explicitly changes them.

## Ledger Rules

- Every member charge is posted to the member ledger.
- Ledger entries are never netted away. A charge and matching payment remain as
  separate immutable entries even when the resulting balance is zero.
- Payments may be partial, advance payments, or overpayments.
- A payment credit may exist before a charge and may leave a credit balance.
- Only a treasurer may add a payment credit to a member account.
- A payment method selection alone does not create a payment credit.
- Flight charges use the flight/logsheet date; payment credits use the date the
  treasurer confirms receipt.

## Member Settlement

- The pilot is the responsible member by default unless another responsible
  member is explicitly selected.
- Member payment rows default to `account`.
- `account` posts the charge only; the member balance remains due.
- Cash, check, and Zelle credits are posted only after treasurer confirmation.
- Payments can be any amount and do not need to match an existing charge.

## Guest Settlement

- Commercial rides are treated as prepaid and do not create a member or guest
  settlement obligation; the commercial-ride flag is the explicit charge type.
- Every guest flight must have a payment method before the logsheet can close.
- Supported guest methods are cash, check, and Zelle.
- Guest cash, check, and Zelle use the remittance workflow.
- A guest payment is recorded as `guest_payment_pending` against the responsible
  member until the treasurer confirms full remittance.
- Guest remittance must equal the full pending amount for the MVP; partial
  remittance is not supported.
- Guest Zelle remains the responsible member's liability until the treasurer
  confirms that the correct amount was received.
- If a guest payment is never confirmed, the pending amount remains the
  responsible member's charge.
- The responsible member defaults to the pilot unless explicitly overridden.
- Guest payment records should retain the guest name, flight when available,
  payment method, amount, collecting/responsible member, and confirmation
  audit data.

## Scope Boundaries

- Payment-provider integration is out of scope.
- Guest cash/check/Zelle remittance is an internal recording and confirmation
  workflow, not an external payment processor.
- Partial guest remittance is deferred.
- Historical migration and reconciliation remain separate rollout work.

## Required Invariants

- Posting a charge and a confirmed matching payment is atomic.
- Remitting a guest payment is atomic and can happen only once.
- Reversals preserve the original entries and require an audit reason.
- A guest pending entry cannot be cleared for less than its full amount.
- Unauthorized users cannot add member payments or confirm guest remittance.
