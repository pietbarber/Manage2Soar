# Member Billing Ledger

*Implementation specification for extending “My Flight Charges” with member balances, treasurer ledger management, and guest-cash reconciliation*

| **Field**         | **Value**                                                                            |
|-------------------|--------------------------------------------------------------------------------------|
| Product           | Manage2Soar                                                                          |
| Target repository | pietbarber/Manage2Soar; implementation expected on invrtd fork                       |
| Status            | Implementation-ready specification                                                   |
| MVP boundary      | Member ledgers, flight posting, manual entries, reversals, member view, treasurer tools |
| Accounting role   | Member-facing operational subledger; not the club’s general ledger                   |

# 1. Executive summary

Implement a signed, auditable billing ledger for each member. The existing My Flight Charges page remains the member-facing interface. Expand it to show the member balance and complete billing history. Add a separate treasurer-only area for member search, balance review, ledger entry posting, reversals, cash-remittance tracking, filters, and CSV export.

> **Balance convention:** A positive balance means the member owes money to the club or holds club money awaiting remittance. Zero means the ledger is settled. A negative balance means the member has credit. The interface must describe the result in plain language rather than require users to interpret a signed number.

The balance is the sum of immutable, posted ledger entries. Existing flight charges become entries when a logsheet is closed at day end. Permitted changes to shared-flight allocations through month-end create auditable corrections. Payments, credits, manual charges, guest cash collected, cash remittances, opening balances, and reversals are recorded in the same ledger.

# 2. Existing-system baseline

- The current member route is logsheet:personal_charges at /logsheet/charges/personal/ and is labeled “My Flight Charges” in the user menu.

- personal_charges_summary currently shows finalized flight allocations and miscellaneous charges for the preceding 365 days.

- Flight costs are split through existing flight-allocation logic and include tow, rental, and instruction components.

- The current page and CSV export report activity, but they do not maintain a running member balance or record payments and credits.

- Logsheet finances already support miscellaneous member charges and a finalized-finances CSV workflow.

- Manage2Soar already has a configurable treasurer role; the feature must use that role plus superuser access.

> **Implementation implication:** Do not calculate the new balance by combining live flight queries with ledger entries at request time. Doing so risks double counting and allows historical balances to change when rate or flight data changes. Post a frozen ledger entry for each finalized flight allocation, and use the ledger as the sole balance source.

# 3. Scope

## 3.1 Included in the MVP

- One `Ledger` per member, created lazily or by data migration.

- Immutable, auditable `LedgerEntry` records with a debit or credit effect and a separate business category.

- Automatic idempotent posting of finalized flight charges, including split charges.

- Manual charge, payment, credit, guest cash collected, cash remitted, opening balance, and reversal workflows.

- Expanded My Flight Charges page with current balance and ledger history.

- Treasurer ledger list, member detail, posting forms, outstanding-cash workflow, and CSV export.

- Authorization, concurrency controls, migration/backfill tooling, audit logging, and automated tests.

## 3.2 Deferred

- Online payment processing or stored payment credentials.

- Automatic emails or monthly statements.

- Payment allocation to specific invoices or aging buckets.

- QuickBooks or other accounting-system synchronization.

- Configurable category administration, attachments, deposit batching, and refunds.

# 4. Terminology and financial rules

Use these backend terms consistently:

| **Concept** | **Backend term** | **Meaning** |
|---|---|---|
| Website sign-in identity | `User` | The existing Django authentication user |
| Member billing record | `Ledger` | The container for one member’s billing entries |
| Net financial position | `Ledger.balance` | The sum of all posted entry effects |
| One financial event | `LedgerEntry` | A charge, payment, credit, remittance, opening balance, or reversal |

Do not use `Account`, `BillingAccount`, `AccountBalance`, or `AccountTransaction` as backend model names. In user-facing text, use natural labels such as **Member balance**, **Balance due**, **Credit balance**, **Member ledger**, and **My Charges & Balance**.

| **Financial term**   | **Definition**                                            | **Balance effect** |
|----------------------|-----------------------------------------------------------|--------------------|
| Debit                | Increases the member balance                              | \+ amount          |
| Credit               | Decreases the member balance                              | − amount           |
| Charge               | Amount billed to a member                                 | Debit              |
| Payment              | Money received from or for a member                       | Credit             |
| Guest cash collected | Club money temporarily held by a member                   | Debit              |
| Cash remitted        | Delivery of previously collected club cash                | Credit             |
| Credit balance       | Negative balance held in the member’s favor               | Display state      |
| Reversal             | Opposite-effect entry linked to an incorrect posted entry | Opposite           |

The canonical calculation is:

```text
ledger.balance = SUM(entry.signed_effect)
DEBIT  => +amount
CREDIT => -amount
```

- Amounts are USD Decimal values with two fractional digits; floating-point types are prohibited.

- Input amount is always strictly greater than zero. Effect supplies the sign.

- Balances may be positive, zero, or negative without validation errors.

- Posted entries cannot be edited or deleted through application or admin workflows.

- Corrections are made only by reversal, optionally followed by a replacement entry.

# 5. Functional requirements

## 5.1 Member-facing My Flight Charges

- Keep the existing route name and URL for backward compatibility.

- Show a prominent balance card: “Balance due: \$75.00,” “Balance settled,” or “Credit balance: \$25.00.”

- Show outstanding guest cash separately when nonzero: “Includes \$30.00 cash awaiting remittance.”

- Display a single chronological billing history with date, category, member-visible description, debit, credit, and running balance.

- Link flight-derived entries to the related flight view when the user is authorized to view it.

- Never expose treasurer-only notes, internal references, creator IP information, or other members’ records.

- Retain CSV export and update it to export the ledger for the selected/default date range.

- Default to the most recent 365 days for rows, but calculate and display the balance over all posted history.

- Provide filters for date range and entry category without allowing arbitrary-member selection.

## 5.2 Treasurer ledger list

- Add a treasurer navigation entry labeled “Member Billing.”

- Search by member name, username, or member number where available.

- Filter by active/inactive status, balance due, credit balance, settled balance, outstanding guest cash, category, and date range.

- Show balance, outstanding guest cash, last-entry date, and membership status.

- Show summary totals separately: member balances due, member credit balances, outstanding guest cash, and net ledger balance.

- Export the current filtered result set to CSV with spreadsheet-injection sanitization.

## 5.3 Treasurer member-ledger detail

- Show the selected member, balance in plain language, outstanding guest cash, and complete ledger.

- Allow posting of manual charge, payment, general credit, and guest cash collected.

- Allow a cash-remittance action only against one or more open guest-cash entries.

- Allow reversal only for an unreversed posted entry.

- Show creator, created timestamp, effective date, internal note, source link, reversal link, and operational status.

- Before confirmation, preview the resulting balance in plain language.

## 5.4 Logsheet charge defaults and validation

The logsheet must make the payer and settlement method explicit while minimizing routine entry work for club members.

- When the charged party is an active member, default the payment arrangement to Member Balance. The user may deliberately select another permitted arrangement when club rules allow it.

- When the charged party is a guest, organization, reciprocal-club pilot, or other non-member, do not infer a payment arrangement. Require an explicit charge type before the flight can be marked financially complete or the day can be closed.

- Supported charge types for non-member parties must be an explicit enum or configured choice set, such as Cash Collected, Card/Electronic Payment, Check, Invoice/Receivable, Waived/No Charge, or Charged to Sponsoring Member. The exact enabled choices are a club configuration decision.

- Charged to Sponsoring Member requires selection of an active member and posts the flight charge to that member’s ledger. Cash received by a member or board member must use Guest Cash Collected so it enters the remittance workflow rather than appearing as an ordinary member purchase.

- Waived/No Charge requires an authorized role and a member-visible reason. A blank charge type is never equivalent to zero charge or paid.

- Server-side validation must enforce these rules for form submissions, imports, APIs, and administrative workflows; a browser default alone is insufficient.

# 6. Guest cash workflow

Guest cash is operationally distinct from a personal purchase even though both debit the receiving member’s ledger. The ledger must preserve that distinction and give the treasurer an outstanding-cash queue.

1.  A guest pays cash for a flight to a member or board member.

2.  An authorized user posts Guest Cash Collected against the receiving member, including the guest/payer name and related flight when available.

3.  The entry debits the receiving member’s ledger and is marked Awaiting Remittance.

4.  The treasurer receives the cash and selects the open collected entry.

5.  The system atomically posts a linked Cash Remitted credit and marks the collected entry Remitted.

6.  If either entry was erroneous, the treasurer reverses it; the system preserves both the original and correcting history.

| **Entry**            | **Effect** | **Operational state** | **Linked record**      |
|----------------------|------------|-----------------------|------------------------|
| Guest Cash Collected | +\$100     | Awaiting remittance   | Flight (optional)      |
| Cash Remitted        | −\$100     | Remitted              | Clears collected entry |

- Partial remittance is out of MVP scope; one remittance clears one collected entry in full.

- A collected entry cannot be remitted twice; enforce this with a database uniqueness constraint.

- A related guest flight must not also remain categorized as unpaid in any future payment-status feature.

# 7. Data model

Create a dedicated Django app named billing. This prevents authentication ambiguity around “accounts” and keeps ledger concerns out of the already large logsheet models module.

## 7.1 Ledger

| **Field**  | **Type / constraint**          | **Purpose**                                   |
|------------|--------------------------------|-----------------------------------------------|
| id         | BigAutoField                   | Primary key                                   |
| member     | OneToOneField(Member, PROTECT) | One ledger per member                         |
| created_at | DateTimeField(auto_now_add)    | Audit timestamp                               |
| updated_at | DateTimeField(auto_now)        | Operational timestamp; not the balance source |

Do not store a mutable balance in the MVP. Calculate it with an indexed aggregate over posted entries. A cached balance may be introduced later only with database locking and reconciliation checks.

## 7.2 LedgerEntry

| **Field**          | **Type / constraint**                        | **Purpose**                          |
|--------------------|----------------------------------------------|--------------------------------------|
| ledger             | FK Ledger, PROTECT                           | Ledger containing the entry          |
| kind               | TextChoices                                  | Business meaning                     |
| effect             | DEBIT or CREDIT                              | Mathematical direction               |
| amount             | Decimal(12,2), \> 0                          | Unsigned magnitude                   |
| effective_date     | DateField                                    | Statement date                       |
| member_description | CharField(255)                               | Visible to member                    |
| internal_note      | TextField(blank=True)                        | Treasurer only                       |
| created_by         | FK Member, PROTECT                           | Posting actor                        |
| created_at         | DateTimeField(auto_now_add)                  | Immutable posting timestamp          |
| flight             | FK Flight, SET_NULL, nullable                | Related source flight                |
| misc_charge        | FK existing charge model, SET_NULL, nullable | Legacy/source link                   |
| source_key         | CharField(160), nullable                     | Idempotency key                      |
| reverses           | OneToOne self, PROTECT, nullable             | Original entry reversed              |
| cash_collection    | OneToOne self, PROTECT, nullable             | Collection cleared by remittance     |
| guest_name         | CharField(150, blank=True)                   | Guest/payer label                    |
| payment_method     | TextChoices, nullable                        | Cash/check/card/ACH/other            |
| reference          | CharField(100, blank=True)                   | Check, receipt, or deposit reference |

Ledger-entry kinds:

FLIGHT_CHARGE, MISC_CHARGE, MANUAL_CHARGE, PAYMENT, CREDIT,  
GUEST_CASH_COLLECTED, CASH_REMITTED, OPENING_BALANCE, REVERSAL

- Check constraint: amount \> 0.

- Check constraint: kind/effect combinations must be valid; REVERSAL effect must oppose the referenced original.

- Unique constraint on non-null source_key for idempotent automatic/import posting.

- Unique one-to-one reversal relation prevents multiple reversals of the same entry.

- Unique one-to-one cash_collection relation prevents duplicate remittance.

- Indexes: (ledger, effective_date, id), kind, source_key, created_at, and open guest-cash lookup.

# 8. Posting services and invariants

All ledger changes must go through `billing/services.py`. Views, admin actions, signals, and management commands must not create entries directly.

| **Service**                              | **Responsibility**                                                         |
|------------------------------------------|----------------------------------------------------------------------------|
| post_entry(...)                          | Validate kind/effect, quantize currency, set actor, create immutable entry |
| post_flight_charges(flight, actor)       | Create one idempotent debit per billed member allocation                   |
| post_misc_charge(charge, actor)          | Create idempotent debit for existing miscellaneous member charge           |
| reverse_entry(entry, actor, reason)      | Lock original; create linked opposite-effect reversal                      |
| remit_guest_cash(collection, actor, ...) | Lock collection; create linked credit; prevent duplicates                  |
| get_balance(ledger, as_of=None)          | Sum signed effects through an optional date                                |
| reconcile_ledger(ledger)                 | Compare source records with ledger and report anomalies                    |

- Wrap posting, reversal, and remittance in `transaction.atomic()`.

- Use `select_for_update()` for reversal and remittance targets.

- Use database uniqueness, not an application-only pre-check, for idempotency.

- Catch `IntegrityError` from duplicate source keys and return the existing entry when it is semantically identical.

- Reject future effective dates by default for MVP unless a deliberate configuration decision enables them.

# 9. Flight-charge integration

## 9.1 Posting point

At successful day-end logsheet closure, freeze the operational flight record and post the then-current flight allocation. Shared-flight allocations remain adjustable through the applicable month-end cutoff under Section 9.4. Register the posting call in the same database transaction as finalization. A post-save signal alone is not sufficient because it obscures error handling and can fire during maintenance tasks.

## 9.2 Entry granularity

- Create one `FLIGHT_CHARGE` entry per billed member per flight. Its amount is that member’s total allocated tow, rental, and instruction charge.

- Preserve component amounts in a structured snapshot field or companion FlightChargeSnapshot model for display/export diagnostics.

- For split flights, generate independent entries with source keys such as flight:{flight_id}:member:{member_id}:v1.

- Commercial rides excluded by current personal-charge logic remain excluded unless a member is explicitly the payer.

- Zero-dollar allocations do not produce ledger entries.

## 9.3 Corrections after posting

Once a flight charge is posted, source edits must not mutate the ledger row. A correction service compares the new allocation to the posted snapshot. If different, it reverses the old entry and posts a replacement using a new source version. The correction must be explicit and auditable.

> **Compatibility requirement:** The existing `update_flight_costs` command must either skip ledger-posted flights by default or invoke the correction service. It must never change a posted flight’s source costs without reconciling the ledger.

## 9.4 Day-end closure and month-end allocation window

Separate operational closure from financial allocation lock. Closing a daily logsheet must not require leaving the entire flight record editable for the rest of the month.

- An authorized duty officer or existing logsheet closer may close the logsheet at the end of the operating day. Closure freezes flight times, aircraft, tow data, participants, rates, miscellaneous charges, and all other operational fields.

- After closure, a member who is one of the billed participants on a shared flight may edit only that flight's cost-allocation split. The member may not change participants, total billable amount, rate inputs, flight data, charge category, or another unrelated flight.

- A shared allocation must continue to total exactly 100 percent, or the exact frozen flight charge when fixed currency shares are supported. Rounding must be deterministic and preserve the original total.

- The self-service allocation window ends at 11:59:59 p.m. on the last calendar day of the flight's month in the configured club timezone. Store the cutoff calculation centrally; do not rely on browser time.

- Every allocation change must record the actor, timestamp, previous split, new split, reason (optional for members and required for staff overrides), and affected flight. Notify or visibly identify all affected members.

- Applying a post-closure allocation change must atomically reverse the superseded FLIGHT_CHARGE entries and post replacement entries for every affected member. It must not reopen the daily logsheet or mutate posted ledger rows.

- After the cutoff, members have read-only access. A treasurer or other explicitly authorized financial role may correct an allocation only through the same audited correction service with a required reason.

- Month-end locking is per flight month, not a rolling number of days. The system should expose Open for allocation changes and Allocation locked states in the member and treasurer interfaces.

# 10. URLs, views, forms, and templates

| **Route name**                | **Suggested path**                                | **Access**          |
|-------------------------------|---------------------------------------------------|---------------------|
| logsheet:personal_charges     | /logsheet/charges/personal/                       | Own ledger only     |
| logsheet:personal_charges_csv | /logsheet/charges/personal/export/csv/            | Own ledger only     |
| billing:ledger_list           | /billing/ledgers/                                 | Treasurer/superuser |
| billing:ledger_detail         | /billing/ledgers/\<member_id\>/                   | Treasurer/superuser |
| billing:entry_create          | /billing/ledgers/\<member_id\>/entries/new/       | Treasurer/superuser |
| billing:entry_reverse         | /billing/entries/\<pk\>/reverse/                  | Treasurer/superuser |
| billing:cash_remit            | /billing/cash/\<pk\>/remit/                       | Treasurer/superuser |
| billing:ledger_export         | /billing/ledgers/export/csv/                      | Treasurer/superuser |

- Use POST-only endpoints for posting, reversal, and remittance; include CSRF protection.

- Forms must resolve members and ledgers on the server. Never trust a hidden ledger ID without authorization checks.

- Entry-form fields vary by kind and must reject irrelevant combinations.

- The confirmation page or form preview must display current balance, signed effect, and predicted resulting balance.

- Preserve Bootstrap 5 styling and existing responsive table patterns.

# 11. Permissions and privacy

| **Capability**                   | **Member** | **Treasurer** | **Superuser** |
|----------------------------------|------------|---------------|---------------|
| View own balance/history         | Yes        | Yes           | Yes           |
| Export own billing history       | Yes        | Yes           | Yes           |
| View another member’s ledger     | No         | Yes           | Yes           |
| Post ledger entry                | No         | Yes           | Yes           |
| Reverse/remit                    | No         | Yes           | Yes           |
| View internal notes/audit fields | No         | Yes           | Yes           |
| Edit/delete posted row           | No         | No            | No            |

- Centralize authorization in billing permissions/decorators using the existing configurable treasurer role utility.

- Apply checks in every view and service entry point; template visibility is not authorization.

- Return 404 or 403 consistently with existing project policy for unauthorized cross-member access.

- Django admin must be read-only for posted fields; allow approved reversal action rather than delete/edit.

- Do not place internal_note in member templates, member CSVs, notifications, or generic serialization.

# 12. Migration and rollout

1.  Create billing app, schema, constraints, services, permissions, and read-only admin.

2.  Deploy the schema with the feature disabled; create ledgers lazily.

3.  Run a dry-run backfill report over finalized flights and existing miscellaneous charges.

4.  Select a ledger cutoff date and obtain each member’s opening balance as of the preceding day.

5.  Post OPENING_BALANCE entries at the cutoff, then backfill source charges on or after the cutoff with deterministic source keys.

6.  Reconcile sample members against the legacy sheet/accounting records and current My Flight Charges output.

7.  Enable automatic posting during finalization and the treasurer UI.

8.  Switch My Flight Charges to ledger reads; retain the old calculation temporarily as a staff-only reconciliation report.

> **Required business decision before migration:** Choose the ledger cutoff date and authoritative opening balances. Backfilling only the current page’s last 365 days without an opening balance will produce incorrect member balances.

## 12.1 Import command

```bash
python manage.py import_member_balances file.csv --as-of YYYY-MM-DD --dry-run
python manage.py import_member_balances file.csv --as-of YYYY-MM-DD --commit
```

- Match by stable member ID first, then approved secondary identifiers; never silently fuzzy-match names.

- Report missing, duplicate, inactive, and ambiguous members.

- Use an import batch ID and deterministic source keys to make reruns safe.

- Produce counts, totals, row-level errors, and a machine-readable reconciliation CSV.

# 13. Reporting and reconciliation

- Member CSV: effective date, category, description, debit, credit, running balance, related flight reference.

- Treasurer CSV: member, membership status, entry ID, category, effect, amount, effective date, source/reference, creator, created timestamp, reversal state, and cash state.

- Sanitize cells beginning with =, +, -, or @ before CSV output.

- Provide a management command that reports orphaned source records, duplicate source keys, reversed-without-replacement items, and remittance mismatches.

- Summary totals must show receivables, credits, guest cash, and net separately; do not imply they are economically identical.

# 14. Error handling and observability

- A finalization must fail atomically if required ledger posting fails; show an actionable error without partial charges.

- Log entry ID, ledger ID, kind, actor ID, and source key. Do not log internal notes or guest contact information.

- Use Django messages for success and failure feedback. Preserve submitted form values after validation errors.

- Add structured warnings for reconciliation mismatches and duplicate semantic conflicts.

- Add a system check confirming the billing app and required database constraints are installed.

# 15. Test specification

## 15.1 Model and service tests

- Debit increases and credit decreases balance; negative balances are accepted.

- Zero/negative amount and invalid kind/effect combinations are rejected.

- Duplicate flight posting is idempotent under sequential and concurrent calls.

- Split flight creates exactly one correct entry per billed member.

- Reversal creates one opposite entry and a second reversal attempt fails safely.

- Cash remittance clears exactly one collection and duplicate remittance is prevented.

- Internal notes never appear in member-facing serialization.

## 15.2 View and permission tests

- A member can view and export only their own ledger.

- Changing a URL cannot expose another member’s ledger.

- A non-treasurer POST is rejected even if form fields are valid.

- Treasurer and superuser can view and post; configurable treasurer title changes do not break authorization.

- CSRF and POST-only protections apply to every mutation.

- Member page correctly renders due, settled, and credit states.

- A member payer defaults to Member Balance; a non-member payer cannot be completed without an explicit valid charge type.

- Guest cash received by a member creates Guest Cash Collected rather than an ordinary manual or flight charge.

## 15.3 Integration and migration tests

- Finalizing a logsheet posts all expected nonzero member allocations once.

- A finalization failure rolls back both finalized state and ledger entries.

- Flight correction produces reversal plus replacement without modifying original.

- Opening balance plus post-cutoff activity matches the expected member balance.

- Dry-run import writes nothing; committed rerun creates no duplicates.

- CSV output is correct and protects against spreadsheet formula injection.

# 16. Acceptance criteria

1.  A treasurer posts a \$100 manual charge; the member sees “Balance due: \$100.00.”

2.  The treasurer records a \$60 payment; the member sees “Balance due: \$40.00.”

3.  A \$50 additional credit produces “Credit balance: \$10.00.”

4.  A finalized split flight posts the correct frozen charge to each participating member exactly once.

5.  A member or unauthenticated caller cannot access or change another member’s ledger.

6.  Each posted item records creator, created timestamp, effective date, category, effect, and source where applicable.

7.  No posted entry can be edited or deleted; a correction is represented by a linked reversal.

8.  A \$100 guest cash collection appears as outstanding cash and a debit; remittance posts a linked \$100 credit and clears the outstanding state.

9.  Concurrent duplicate posting or remittance cannot alter the balance twice.

10. The migration can be dry-run, rerun safely, and reconciled to authoritative opening balances.

11. Closing a day locks operational logsheet fields while leaving only eligible shared-flight allocation controls available through month-end.

12. An affected member can change a valid shared-flight split before the cutoff; the change reverses and replaces ledger entries atomically without reopening the day.

13. A member cannot change a shared-flight split after the club-timezone month-end cutoff, and cannot change the total charge or flight details at any time after day-end closure.

14. Concurrent or stale allocation edits are rejected safely and cannot create duplicate or unbalanced ledger entries.

# 17. Implementation sequence

| **Phase**              | **Deliverables**                                    | **Exit condition**                            |
|------------------------|-----------------------------------------------------|-----------------------------------------------|
| 1\. Ledger core        | Models, constraints, services, admin, unit tests    | Manual service posting and balance tests pass |
| 2\. Flight integration | Finalization hook, snapshots, corrections, backfill | Finalized flights post idempotently           |
| 3\. Treasurer UI       | List/detail/forms/cash workflow/export              | Treasurer acceptance scenarios pass           |
| 4\. Member UI          | Expanded page, history, balance, CSV                | Members see only their own complete ledger    |
| 5\. Migration          | Cutoff, opening balances, import, reconciliation    | Totals signed off by treasurer                |
| 6\. Rollout            | Feature flag, monitoring, docs                      | Ledger is authoritative for My Flight Charges |

# 18. Decisions required before coding

1.  What cutoff date and authoritative source will supply opening balances?

2.  Who besides the treasurer may record Guest Cash Collected: duty officers, board members, or treasurer only?

3.  Should future-dated entries be prohibited or hidden until their effective date?

4.  Should the My Flight Charges navigation label remain unchanged or become “My Charges & Balance”?

5.  Which existing miscellaneous-charge model is authoritative, and may finalized miscellaneous charges currently be deleted?

6.  How are commercial/guest flights currently marked paid, and what rule will prevent duplicate guest-flight billing?

7.  Which non-member charge types are enabled, and which roles may select Waived/No Charge or Invoice/Receivable?

8.  What configured timezone defines day-end and month-end for the club?

9.  May any affected participant submit a shared split, or must every affected member confirm it before posting? Recommended MVP: allow an affected member to submit, record full audit history, and notify the others.

10. Which roles may perform a post-month-end allocation correction in addition to treasurer and superuser?

# Appendix A. Suggested file layout

```text
billing/
├── admin.py
├── apps.py
├── forms.py
├── models.py
├── permissions.py
├── selectors.py
├── services.py
├── urls.py
├── views.py
├── management/
│   └── commands/
│       ├── backfill_ledgers.py
│       ├── import_member_balances.py
│       └── reconcile_ledgers.py
├── templates/
│   └── billing/
└── tests/
```

Modify logsheet finalization to call billing services; modify personal_charges_summary and its CSV view to read the ledger; update templates/base.html for treasurer navigation; add billing to INSTALLED_APPS and project URLs.

# Appendix B. Source references inspected

- Manage2Soar repository README and current project structure.

- logsheet/urls.py routes for personal charges, CSV export, logsheet finances, and member miscellaneous charges.

- logsheet/views.py personal_charges_summary and personal_charges_summary_csv behavior.

- logsheet/models.py Flight cost fields, split participants, guest-name fields, and cost calculation context.

- templates/base.html navigation entry for My Flight Charges.

- members/utils/roles.py configurable role utility.

This specification is based on the upstream main branch as inspected July 24, 2026. Reconfirm exact model and finalization function names against the implementation branch before coding.
