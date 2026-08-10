# Billing App - API Reference

## Overview

This document summarizes the primary service-layer APIs in billing/services.py and period-control APIs in billing/periods.py.

## Service Layer (billing/services.py)

### Ledger and statement APIs

- get_or_create_ledger(member)
- get_balance(ledger)
- get_statement_rows(ledger)

### Posting APIs

- post_manual_charge(member, actor, amount, effective_date, description, reason)
- post_manual_payment(member, actor, amount, effective_date, description, reason)
- post_manual_credit(member, actor, amount, effective_date, description, reason)
- post_opening_balance(member, actor, amount, effective_date, description, reason, effect)
- reverse_manual_entry(entry, actor, effective_date, reason)

### Flight charge APIs

- post_flight_charges(flight, actor, effective_date, allocations, reason)
- correct_flight_charges(flight, actor, effective_date, allocations, reason)

## Period APIs (billing/periods.py)

- close_period(year, month, actor, reason)
- reopen_period(period, actor, reason)

## Behavioral guarantees

- Immutable ledger entries and snapshots after creation.
- Validation errors surfaced as django.core.exceptions.ValidationError.
- Idempotency via source keys where applicable.
- Service-level permission checks for manual transaction operations.

## Related Documentation

- Architecture Overview: architecture.md
- Data Models: models.md
- View Functions: views.md
- Testing Guide: testing.md
