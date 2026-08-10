# Billing App - Testing Guide

## Test modules

Current billing tests live in billing/tests:

- test_billing_disabled.py
- test_ledger.py
- test_manual_transactions.py
- test_periods.py
- test_views.py

## Targeted test runs

- pytest billing/tests/test_billing_disabled.py -q
- pytest billing/tests/test_views.py -q
- pytest billing/tests/test_periods.py -q

## Full billing test suite

- pytest billing/tests -q

## What to verify when editing docs

- URL examples match billing/urls.py exactly.
- Decorator locations match module definitions.
- Model field types and relationships match billing/models.py.
- Cross-links in docs reference files that exist in billing/docs.

## Related Documentation

- README: README.md
- Architecture Overview: architecture.md
- Data Models: models.md
- View Functions: views.md
- Decorators: decorators.md
- API Reference: api.md
- Development Guide: development.md
