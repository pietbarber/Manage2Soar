# Billing App - Club Books (General Ledger)

The club books are an opt-in, double-entry general ledger for the treasurer.
They sit beside the member ledgers. Member ledgers still answer "what does this
member owe?". The club books answer "where is the club's money, and where did
it come from and go?": bank and cash balances, expenses such as field rent and
maintenance, other income, and the General Fund.

Treasurers and superusers reach the books from the **Club Finances** menu.
While club books are on, Member Billing moves from **Log Sheets** to that menu,
below Club Ledger.

## Enabling

| Setting (`SiteConfiguration`) | Meaning |
|---|---|
| `billing_app_enabled` | Required. Club accounting cannot be on without it. |
| `club_accounting_enabled` | Shows the Club Finances menu and allows posting. Default `False`. |
| `club_accounting_start_date` | Optional; set by the go-live wizard. The opening entry is dated on this day; every other entry must be dated on or after it. |

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
| `post_member_paid_expense(actor, date, member, expense_account, amount, memo, ...)` | A member paid a club bill out of pocket: credits their member ledger and posts Dr expense, Cr Member Receivables (that member) in one transaction. |
| `reverse_journal_entry(entry, actor, date, reason)` | Posts the mirror image. |
| `go_live(actor, start_date, rows)` | Sets the start date and posts the opening entry for bank balances. |
| `account_balance`, `account_balances`, `account_register` | Balances and running-balance registers. |
| `verify_books()` | Integrity problems as a list of strings. |

`post_journal_entry` refuses an entry when:
- club accounting is off;
- the actor isn't a treasurer or superuser (member postings excepted);
- the date is in the future, before the start date (the opening entry must be
  on it), or in a closed billing period;
- there are fewer than two lines, a line has both or neither side, or an
  amount is negative;
- debits ≠ credits;
- a line uses an inactive account;
- a manual entry touches Member Receivables. That account changes only through
  member ledgers, so it always ties to them;
- it is an opening entry and another opening entry is still in effect.

A repeated `source_key` with the same date and lines returns the existing
entry; a different payload raises.

Reversals:
- Only manual entries can be reversed here.
- Member postings are reversed from the member's ledger. Reversing a member
  ledger entry that has a journal entry (`reverse_entry` in
  `billing/services.py`) posts the journal reversal in the same transaction.
- The opening entry can't be reversed here; the go-live wizard replaces it.
- A reversal can't predate its original, can't be reversed, and can happen
  only once.

`verify_books()` also backs the `verify_books` management command, which exits
non-zero when it finds problems. It checks for:
- unbalanced entries, or entries with fewer than two lines;
- an unbalanced trial balance;
- receivables lines without a member;
- member-tagged lines outside receivables.

### Go-live

`go_live(actor, start_date, rows)` starts the books. Each row is a
`BankBalance(name, amount, account=None)`:
- An existing bank account takes the row's name, so the treasurer can rename
  110 Checking to match the bank.
- A row without an account creates a new bank account with the next free code
  in 110–119.
- A positive balance debits the bank account; a negative (overdrawn) balance
  credits it. The total goes to the **General Fund**, not Opening Balance
  Equity, because every bank balance is entered at once.

It also sets `club_accounting_start_date` and posts one `opening` entry dated on
it. It can be rerun until any other entry is posted: the current opening entry
is reversed (on its own date) and replaced, and an unchanged submission posts
nothing. Once other entries exist, it refuses, and opening balances are
corrected with a general journal entry. Member receivables aren't part of
go-live yet; they arrive with member ledger integration.

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
| `record_expense` | `books/expense/` | Expense paid by club: Dr expense, Cr cash. |
| `record_member_expense` | `books/member-expense/` | Expense paid by member: Dr expense, Cr Member Receivables (member), plus a member-ledger credit. |
| `record_income` | `books/income/` | Dr cash, Cr income. |
| `cash_transfer` | `books/transfer/` | Dr destination, Cr source (both cash accounts). |
| `general_journal` | `books/journal/` | Free-form balanced lines (e.g. unpaid bills, reserves). Member Receivables is not offered. |
| `journal_detail` | `books/entries/<id>/` | One entry, its lines, and a reversal form. |
| `journal_reverse` | `books/entries/<id>/reverse/` | POST; date and reason required. |
| `go_live` | `books/go-live/` | Start date and bank balances; posts or replaces the opening entry. Read-only once other entries exist. |

## Roadmap

These phases are planned but not yet built:

1. **Member ledger integration.** The first piece is built: an expense a
   member paid for the club credits their member ledger and posts to Member
   Receivables together, and reversing it from the member's ledger reverses
   the books too. Next, every member `LedgerEntry` posts its journal entry in
   the same transaction:
   - flight charges split into tow, rental and instruction revenue;
   - payments go to a chosen deposit account.

   It also adds member-to-member transfers and refunds, member balances in the
   go-live wizard, and a receivables-vs-member-ledgers tie-out in
   `verify_books`. Until then, Member Receivables in the books shows only the
   member-paid expenses, not each member's full balance.
2. **Reports.** Balance sheet, income statement, trial balance, and a treasurer
   dashboard.
3. **Later.** A bills/payables workflow, recurring transactions, reserve funds,
   and bank reconciliation.

## Appendix: Double-Entry Bookkeeping Info

This appendix is for a treasurer who has kept books on a spreadsheet or
checkbook register but has not used double-entry before. You don't need an
accounting background to use Club Finances, but the screens make more sense once
you know the handful of ideas below.

### The one idea

Every transaction is recorded **twice**: once for where the money came from or
what it was for, and once for where it went. The two records always have the
same total. A checkbook register (single-entry bookkeeping) records only one
side ("$450 out of checking"). Double-entry also records the other side
("...for aircraft maintenance"). That second side is what lets the club answer
"how much did we spend on aircraft maintenance this year?" without digging
through bank statements or searching a spreadsheet.

In so doing, the Accounting Equation is balanced:

> **Assets = Liabilities + Equity**

(Many clubs are likely nonprofits. Technically, for nonprofits, **Equity** is
renamed **Net Assets**. To avoid repeating "assets", this appendix uses
**Equity**.)

The two sides of each transaction are called **debit** and **credit**. Ignore
any meaning those words have at your bank. In bookkeeping they only mean
*left side* and *right side* of the entry. For every entry:

> **total debits = total credits**

The books refuse to save an entry that doesn't balance. If you can't make it
balance, the usual cause is that you've left out a side of the transaction.

### The five kinds of account

Every account in the chart of accounts is one of five types. The type decides
which side makes the balance go **up**:

| Type | What it is | Examples | Increases with |
|---|---|---|---|
| **Asset** | Things the club has | Checking, savings, cash box, Undeposited Funds, Member Receivables | Debit |
| **Liability** | Things the club owes | Accounts Payable | Credit |
| **Equity** | The club's net worth: what's left after liabilities | General Fund, Opening Balance Equity | Credit |
| **Income** | Money earned | Dues, Tow Revenue, Donations | Credit |
| **Expense** | Money spent | Field Rent, Fuel, Insurance | Debit |

Debit-normal accounts (assets and expenses) grow on the left. Credit-normal
accounts (liabilities, equity, income) grow on the right. This is why a
screen will show "Checking: $3,200" and "Dues: $3,200" as positive numbers even
though one is debited and the other is credited: the app displays each balance
in its account's normal direction.

Income and expense are temporary buckets that feed into **Equity**. Income
raises it, expenses lower it. Over a year, the difference (income minus
expenses) is the surplus or deficit that lands in the General Fund.

### Worked examples

Each row is one line of a journal entry. These are all things you can do from
the Club Finances menu.

**Paying a bill: $500 of field rent from checking** (*Record expense*)

| Account | Debit | Credit |
|---|---:|---:|
| Field Rent (expense) | 500.00 | |
| Checking (asset) | | 500.00 |

Expenses went up (debit) and the checking balance went down (credit).

**Receiving a donation: $200 deposited to checking** (*Record income*)

| Account | Debit | Credit |
|---|---:|---:|
| Checking (asset) | 200.00 | |
| Donations (income) | | 200.00 |

**Moving money between accounts: $1,000 from checking to savings** (*Cash transfer*)

| Account | Debit | Credit |
|---|---:|---:|
| Savings (asset) | 1,000.00 | |
| Checking (asset) | | 1,000.00 |

No income or expense is involved; money only changed pockets.

**Receiving a bill you haven't paid yet: $600 of insurance** (*General journal*)

| Account | Debit | Credit |
|---|---:|---:|
| Insurance (expense) | 600.00 | |
| Accounts Payable (liability) | | 600.00 |

The expense is recorded when you incur it. When you later pay the bill,
debit Accounts Payable and credit Checking. Insurance is not charged a
second time.

**Setting up the books: opening balances** (the opening entry)

| Account | Debit | Credit |
|---|---:|---:|
| Checking (asset) | 5,000.00 | |
| Savings (asset) | 12,000.00 | |
| General Fund (equity) | | 17,000.00 |

When the books start, the club already has money. The opening entry debits each
bank account for its starting balance and credits equity (the General Fund) for
the total, so the entry balances. The **Go-Live Setup** page under Club
Finances posts this entry for you.

### Member accounts

Member ledgers are a **subledger**: a detailed list behind one control
account, **Member Receivables** (*receivable* means the club expects to
receive this money from members). The control account's balance should equal
the sum of what members owe. This is why the app forbids manual entries to it:
if you could post to it by hand, it would drift away from the member ledgers.
Entries that touch it always post a member ledger entry at the same time.
(`JournalLine.member` splits the balance per member.)

When a member is charged, the flow works like this:

| Account | Debit | Credit |
|---|---:|---:|
| Member Receivables (asset) | 60.00 | |
| Tow Revenue (income) | | 60.00 |

The club has earned revenue and is owed money. When the member pays, Member
Receivables is credited and cash (or Undeposited Funds) is debited. Both
legs are planned for the member-ledger integration (Roadmap, phase 1).

**A member pays a club bill out of pocket: $700 field rent in cash**
(*Expense paid by member*)

| Account | Debit | Credit |
|---|---:|---:|
| Field Rent (expense) | 700.00 | |
| Member Receivables (asset, that member) | | 700.00 |

The club still had the expense, but no club money left the bank. Instead the
club now owes the member $700, or the member owes $700 less. Their member
ledger gets a matching $700 credit, which their dues or flying charges then
use up.

**A negative Member Receivables balance is not an error.** Receivables is an
asset, so a positive balance means members owe the club. A negative balance
means the club owes its members: for example, the $700 above, until the
member's charges use it up. Negative amounts are shown in parentheses, as in
`($700.00)`, the usual accounting style. The same applies to a single member
on their own ledger, where `($700.00)` is a credit balance in their favor.

### Mistakes: reverse, don't edit

Journal entries can never be changed or deleted, even by a superuser (the
database itself rejects it). An auditor can then trust that last year's books
are the same books they saw last year.

To fix a mistake, **reverse** the entry from its detail page. This posts a new
entry with every debit and credit swapped, and links the two. Then post the
correct entry. Both the mistake and the correction stay visible in the history,
which is the point. A reversal needs a date and a reason, and should be dated
in the period you're correcting if that period is still open.

### Habits that keep the books clean

- **Record the transaction when it happens**, with the date it happened, not
  the date you got around to entering it. The books refuse future dates and
  dates in closed billing periods.
- **Use the memo, payee and reference fields.** Put the check number or invoice
  number in the reference. A future treasurer, or an auditor, will thank you.
- **Pick the most specific account.** If nothing fits, add an account (*Chart
  of accounts → New*) rather than using a catch-all. Rename accounts freely; the
  type is locked once an account has entries, so choose it carefully.
- **Don't delete accounts you've stopped using; deactivate them.** History
  stays intact and the account stops appearing in new entries.
- **Compare the books to the bank statement every month.** The bank's ending
  balance should equal the ledger balance for that account on the same date,
  after allowing for checks or deposits still in transit. Differences are
  usually a missed transaction, a typo, or a bank fee. Automated reconciliation
  is on the roadmap; until then, use the account register and compare line by
  line.
- **Run `verify_books` after any unusual work.** It checks that every entry
  balances and that member postings and control accounts are consistent. A clean
  run exits zero.

### Glossary

| Term | Meaning |
|---|---|
| Chart of accounts | The list of all accounts the club uses. |
| Journal entry | One transaction: a date, a description, and balanced lines. |
| Line | One debit or credit to a single account within an entry. |
| General journal | The free-form entry screen, for anything the simple forms don't cover. |
| Register | One account's lines in date order with a running balance (like a checkbook register). |
| Trial balance | Every account's balance listed together; total debits must equal total credits. |
| Control account / subledger | A summary account (Member Receivables) backed by a detailed list (the member ledgers). |
| Contra account | An account that offsets another, with the opposite normal balance. |
| Accrual | Recording income or expense when it is earned or incurred, not when cash moves. |
| General Fund | The club's accumulated net worth: the equity account where each year's surplus or deficit ends up. |
| Opening Balance Equity | A temporary equity account that balances the opening entry. |
| Undeposited Funds | Payments received but not yet deposited at the bank. |
