# Billing App - Development Guide

## Local workflow

1. Create or activate your virtual environment.
2. Install dependencies from requirements.txt.
3. Run migrations before billing tests.
4. Run focused billing tests while iterating.

## Working conventions

- Keep billing writes inside service functions where possible.
- Preserve immutability guarantees for LedgerEntry and FlightChargeSnapshot.
- Use explicit audit reasons for manual financial changes.
- Keep docs synchronized with billing/urls.py, billing/views.py, and billing/models.py.

## Suggested validation commands

- pytest billing/tests/test_views.py -q
- pytest billing/tests/test_ledger.py -q
- pytest billing/tests/test_periods.py -q

## Related Documentation

- Architecture Overview: architecture.md
- API Reference: api.md
- Data Models: models.md
- Testing Guide: testing.md
