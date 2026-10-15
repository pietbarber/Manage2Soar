# Billing App Documentation

This directory contains comprehensive documentation for the **billing** Django app within Manage2Soar.

## Contents

- [Architecture Overview](architecture.md) - High-level system architecture and design principles
- [Data Models](models.md) - Detailed model relationships and constraints
- [View Functions](views.md) - View functions, forms, and URL routes
- [Decorators](decorators.md) - Authentication and authorization decorators
- [Club Books (General Ledger)](general-ledger.md) - Opt-in double-entry club books under the Club Finances menu
- [Development Guide](development.md) - How to work with the billing app
- [API Reference](api.md) - Service-layer entry points and usage patterns
- [Testing Guide](testing.md) - Test layout, fixtures, and validation commands

## Quick Start

The billing app handles:
- Member financial ledgers (immutable transaction history)
- Monthly billing period management (open/closed state)
- Flight charge allocation from Logsheet data
- Manual charges and payments
- Financial statement generation
- Opt-in double-entry club books: bank accounts, expenses, income, transfers ([details](general-ledger.md))

### Enable Billing App

```python
# In siteconfig.models.SiteConfiguration
billing_app_enabled = True
```

## Core Concepts

1. **Ledger** - Immutable financial record for each member
2. **BillingPeriod** - Monthly state tracking (open/closed)
3. **LedgerEntry** - Individual transactions (charges, payments, reversals)
4. **FlightChargeSnapshot** - Frozen allocation evidence from flights
5. **Account / JournalEntry / JournalLine** - The club's chart of accounts and balanced, immutable journal entries

## File Index

| File | Purpose |
|------|---------|
| `admin.py` | Django admin configuration |
| `decorators.py` | Billing, treasurer, and club-accounting gate decorators |
| `exceptions.py` | Custom exceptions (BillingDisabledError, ClubAccountingDisabledError) |
| `ledger_services.py` | Club books posting, reversal, balances, `verify_books` |
| `ledger_forms.py` | Club books forms |
| `ledger_views.py` | Club books views (Club Finances menu) |
| `forms.py` | Web forms for charges/payments |
| `management/commands/` | Cron jobs (period closing) |
| `migrations/` | Database schema migrations |
| `models.py` | Data models (Ledger, BillingPeriod, etc.) |
| `periods.py` | Period close automation logic |
| `permissions.py` | Permission decorators |
| `services.py` | Core billing service layer |
| `templates/` | HTML templates for billing views |
| `tests/` | Test suite |
| `urls.py` | URL routing |
| `views.py` | View functions |
