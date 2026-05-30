# Issue #933 - Duty Swap Auto-Expiry for Past Open Requests

**GitHub Issue**: #933  
**Status**: Complete ✅  
**Date**: May 2026  
**Branch**: `feature/issue-duty-swap-auto-expiry`

## Technical Analysis

### Problem Statement
Open duty swap requests could remain in `open` status after the duty date had already passed. This caused stale records to linger and created confusing member notifications when users manually cancelled old requests long after they were actionable.

### Solution Architecture
The fix introduces a nightly, distributed-lock-safe management command that:
1. Finds `DutySwapRequest` records with `status="open"` and `original_date < today`.
2. Transitions each request to `status="expired"`.
3. Transitions all pending related offers to `status="auto_declined"` with `responded_at` set.
4. Sends dedicated expiry notifications so this system-driven closure remains distinct from user-initiated cancellation.

The command is implemented using `BaseCronJobCommand` to preserve multi-pod safety in Kubernetes.

### Implementation Details
- Added command: `duty_roster/management/commands/expire_past_swap_requests.py`
- Added notification helper: `send_request_expired_notifications` in `duty_roster/views_swap.py`
- Added requester template: `duty_roster/templates/duty_roster/emails/swap_request_expired_requester.html`
- Added offerer template: `duty_roster/templates/duty_roster/emails/swap_request_expired_offerer.html`
- Added K8s schedule entry in `k8s-cronjobs.yaml`

## Quality Assurance

### Testing Coverage
Targeted swap tests were added to validate:
- Past-dated open requests become expired.
- Pending offers become auto-declined.
- Dry-run mode produces no mutations.
- Future open requests and non-open historical requests remain unchanged.

Validation run:
- `pytest duty_roster/tests/test_duty_swap.py -k SwapRequestExpiryCronjob -q`
- Result: passing.

### Performance Impact
The command executes a filtered date/status query and processes only stale open requests. Runtime overhead is low and bounded by stale-request volume, with a 5-minute active deadline in Kubernetes.

### Security Analysis
No new permissions or public endpoints were introduced. Changes are constrained to backend scheduled processing and existing email pathways. Distributed lock handling prevents duplicate multi-pod execution.

## Business Value

### Benefits Achieved
- Eliminates stale open swap requests from persisting indefinitely.
- Reduces confusing member communication around old-duty cancellations.
- Improves data hygiene and status accuracy for duty swap lifecycle analytics.

### Future Enhancements
- Add admin-facing reporting of expired-request counts over time.
- Optionally include one-time backfill command output summary in operations dashboard.

### Integration Notes
The expiry workflow complements existing manual cancellation and offer acceptance paths without changing their semantics.

## Documentation

### Files Modified/Created
- `duty_roster/management/commands/expire_past_swap_requests.py`
- `duty_roster/views_swap.py`
- `duty_roster/templates/duty_roster/emails/swap_request_expired_requester.html`
- `duty_roster/templates/duty_roster/emails/swap_request_expired_offerer.html`
- `duty_roster/tests/test_duty_swap.py`
- `k8s-cronjobs.yaml`
- `docs/resolved-issues/README.md`
- `docs/workflows/duty-swap-workflow.md`
- `docs/duty-swap-user-guide.md`
- `docs/cronjob-architecture.md`

### Migration Strategy
No schema migration required. Behavior change is delivered through command logic and scheduled execution.

### Lessons Learned
- Status enums alone are not sufficient without lifecycle automation.
- Keeping auto-expiry separate from manual cancellation prevents user-facing ambiguity.
- Existing distributed CronJob infrastructure made rollout low-risk and consistent with other scheduled tasks.
