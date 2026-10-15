# Billing App - Club Books (General Ledger)

The club books are an opt-in, double-entry general ledger for the treasurer.
They sit beside the member ledgers. Member ledgers still answer "what does this
member owe?". The club books answer "where is the club's money, and where did
it come from and go?": bank and cash balances, expenses such as field rent and
maintenance, other income, and the General Fund.

Treasurers and superusers reach the books from the **Club Finances** menu.
Member Billing stays under **Log Sheets**.

## Enabling

| Setting (`SiteConfiguration`) | Meaning |
|---|---|
| `billing_app_enabled` | Required. Club accounting cannot be on without it. |
| `club_accounting_enabled` | Shows the Club Finances menu and allows posting. Default `False`. |
| `club_accounting_start_date` | Optional. The opening entry is dated on this day; every other entry must be dated after it. |

Nothing about a particular club is hard-coded. Bank account names, their
opening balances, and the start date are data the treasurer enters.

## Models (`billing/models.py`)

### `Account`

One row in the chart of accounts.

| Field | Notes |
|---|---|
| `code`, `name` | Unique code (e.g. `500`) and display name; both editable. |
| `type` | `asset`, `liability`, `equity`, `income`, or `expense`. Locked once the account has entries, and always for system accounts. |
| `is_cash` | A bank or cash account. Only assets can be cash accounts. Cash accounts appear as "paid from" and "deposit to" choices. |
| `system_role` | Unique. Marks accounts the books use automatically (below). System accounts cannot be deleted, deactivated, or given an incompatible type. |
| `is_active`, `description` | Inactive accounts can't receive new postings. |

Asset and expense accounts are debit-normal; the others are credit-normal.
Balances on screen are shown in each account's normal direction.

**System roles:**
- `member_receivables`: the control account for member ledgers.
- `undeposited_funds`: payments received but not yet deposited.
- `general_fund` and `opening_balance_equity`.
- Revenue: `tow_revenue`, `rental_revenue`, `instruction_revenue`, `guest_flight_revenue`, `default_charge_revenue`.
- Contra and loss accounts: `member_credits`, `bad_debt`.

Migration `0012` seeds a generic chart with every role, plus common accounts:
Accounts Payable, Dues, Donations, Field Rent, Aircraft Maintenance, Fuel,
Insurance, Utilities and Bank Fees. It seeds one bank account, **110
Checking**, for the treasurer to rename (for example, to the bank's name).
Additional bank accounts go in the same block: 111, 112, and so on.

### `JournalEntry` and `JournalLine`

A journal entry is a header (date, description, payee, reference, internal
note, source, creator) plus two or more lines. Each line debits or credits one
account. Every entry balances: total debits equal total credits.

- `source`: `manual`, `member_posting`, `opening`, `reversal`, `recurring`.
- `member_entry`: one-to-one link to the member `LedgerEntry` that produced
  this entry (used by member-ledger integration).
- `reverses`: one-to-one link from a reversal to the entry it cancels.
- `source_key`: unique idempotency key, like `LedgerEntry.source_key`.
- `JournalLine.member`: required on Member Receivables lines and forbidden on
  every other line, so receivables can be broken down per member.

Both tables are append-only. `save()` on an existing row, `delete()`, and
`bulk_create()` raise `ValidationError`. Rows can only be created by the
ledger service. Database triggers, installed by migration `0012` on PostgreSQL
and SQLite, reject `UPDATE` and `DELETE`.

## Services (`billing/ledger_services.py`)

| Function | Purpose |
|---|---|
| `post_journal_entry(actor, date, lines, memo, ...)` | The single write path. |
| `post_expense`, `post_income`, `post_cash_transfer` | Plain-language wrappers used by the forms. |
| `reverse_journal_entry(entry, actor, date, reason)` | Posts the mirror image. |
| `account_balance`, `account_balances`, `account_register` | Balances and running-balance registers. |
| `verify_books()` | Integrity problems as a list of strings. |

`post_journal_entry` refuses an entry when:
- club accounting is off;
- the actor isn't a treasurer or superuser (member postings excepted);
- the date is in the future, on or before the start date (except the opening
  entry, which must be on it), or in a closed billing period;
- there are fewer than two lines, a line has both or neither side, or an
  amount is negative;
- debits ≠ credits;
- a line uses an inactive account;
- a manual entry touches Member Receivables. That account changes only through
  member ledgers, so it always ties to them.

A repeated `source_key` with the same date and lines returns the existing
entry; a different payload raises.

Reversals:
- Only manual entries can be reversed here.
- Member postings are reversed from the member's ledger.
- The opening entry can't be reversed.
- A reversal can't predate its original, can't be reversed, and can happen
  only once.

`verify_books()` also backs the `verify_books` management command, which exits
non-zero when it finds problems. It checks for:
- unbalanced entries, or entries with fewer than two lines;
- an unbalanced trial balance;
- receivables lines without a member;
- member-tagged lines outside receivables.

## Views (`billing/ledger_views.py`)

Every view requires `billing_app_required`, `treasurer_required`, and
`club_accounting_required`, in that order. URLs live under `/billing/books/`.

| URL name | Path | Purpose |
|---|---|---|
| `club_ledger` | `books/` | All journal entries, newest first, with cash balances. Filters: date range, account, source, text search. |
| `club_ledger_csv` | `books/export/` | Same filters, one CSV row per line, formula-sanitized. |
| `chart_of_accounts` | `books/accounts/` | Accounts grouped by type, with balances and integrity warnings. |
| `account_create` / `account_edit` | `books/accounts/new/`, `books/accounts/<id>/edit/` | Add or edit accounts. |
| `account_register` / `account_register_csv` | `books/accounts/<id>/`, `.../export/` | One account with a running balance; defaults to the current year. |
| `record_expense` | `books/expense/` | Dr expense, Cr cash. |
| `record_income` | `books/income/` | Dr cash, Cr income. |
| `cash_transfer` | `books/transfer/` | Dr destination, Cr source (both cash accounts). |
| `general_journal` | `books/journal/` | Free-form balanced lines (e.g. unpaid bills, reserves). Member Receivables is not offered. |
| `journal_detail` | `books/entries/<id>/` | One entry, its lines, and a reversal form. |
| `journal_reverse` | `books/entries/<id>/reverse/` | POST; date and reason required. |

## Roadmap

These phases are planned but not yet built:

1. **Member ledger integration.** Every member `LedgerEntry` posts its journal
   entry in the same transaction:
   - flight charges split into tow, rental and instruction revenue;
   - payments go to a chosen deposit account.

   It also adds member-to-member transfers and refunds, a go-live wizard that
   posts opening balances with the General Fund as the plug, and a
   receivables-vs-member-ledgers tie-out in `verify_books`.
2. **Reports.** Balance sheet, income statement, trial balance, and a treasurer
   dashboard.
3. **Later.** A bills/payables workflow, recurring transactions, reserve funds,
   and bank reconciliation.
