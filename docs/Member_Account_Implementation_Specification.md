# Member Billing Ledger

*Implementation specification for extending “My Flight Charges” with member balances, treasurer ledger management, and guest-cash reconciliation*

| **Field**         | **Value**                                                                            |
|-------------------|--------------------------------------------------------------------------------------|
| Product           | Manage2Soar                                                                          |
| Target repository | pietbarber/Manage2Soar; implementation expected on invrtd fork                       |
| Status            | Draft specification; Section 18 decisions must be resolved before coding              |
| MVP boundary      | Member ledgers, flight posting, manual entries, reversals, member view, treasurer tools |
| Accounting role   | Member-facing operational subledger; not the club’s general ledger                   |

# 1. Executive summary

Implement a signed, auditable billing ledger for each member. The existing My Flight Charges page remains the member-facing interface. Expand it to show the member balance and billing history, with recent activity shown by default and older activity available through filters. Add a separate treasurer-only area for member search, balance review, ledger entry posting, reversals, cash/check remittance tracking, filters, and CSV export.

> **Balance convention:** A positive balance means the member owes money to the club or holds club money awaiting remittance. Zero means the ledger is settled. A negative balance means the member has credit. The interface must describe the result in plain language rather than require users to interpret a signed number.

The balance is the sum of immutable, posted ledger entries. Existing flight charges become entries when a logsheet is closed at day end. Treasurer/superuser changes to shared-flight allocations create auditable corrections. Payments, credits, manual charges, guest cash/check collected, remittances, opening balances, and reversals are recorded in the same ledger.

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

- Manual charge, payment, credit, guest cash/check collected, remittance, opening balance, and reversal workflows.

- Expanded My Flight Charges page with current balance and ledger history.

- Treasurer ledger list, member detail, posting forms, outstanding remittance workflow, and CSV export.

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
| Guest cash/check collected | Club money temporarily held by a member             | Debit              |
| Cash/check remitted        | Delivery of previously collected club funds          | Credit             |
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

- The canonical statement order is `(effective_date, created_at, id)` ascending. The `id` tie-breaker is mandatory so running balances are deterministic.

- A running balance shown for a filtered date range starts with the all-history balance before the first included effective date, then applies the visible entries in canonical statement order. Backdated entries therefore change later running balances but never mutate an existing entry.

- MVP rejects future effective dates in every write path. Future-dated posting may be added later only with an explicit rule for whether future entries contribute to current balances.

# 5. Functional requirements

## 5.1 Member-facing My Flight Charges

- Keep the existing route name and URL for backward compatibility.

- Show a prominent balance card: “Balance due: \$75.00,” “Balance settled,” or “Credit balance: \$25.00.”

- Show outstanding guest cash/check separately when nonzero: “Includes \$30.00 awaiting remittance.”

- Display a single chronological billing history with date, category, member-visible description, debit, credit, and running balance.

- Link flight-derived entries to the related flight view when the user is authorized to view it.

- Never expose treasurer-only notes, internal references, creator IP information, or other members’ records.

- Retain CSV export and update it to export the ledger for the selected/default date range.

- Default to the most recent 365 days for rows, but calculate and display the balance over all posted history.

- Provide filters for date range and entry category without allowing arbitrary-member selection.

- Label the first running-balance value for a filtered range as a brought-forward balance when older entries exist.

## 5.2 Treasurer ledger list

- Add a treasurer navigation entry labeled “Member Billing.”

- Search by member name, username, or member number where available.

- Filter members by active/inactive status, all-history balance state, and outstanding guest cash/check. Category and date filters select members having at least one matching entry and constrain the entry-level CSV export; they do not recalculate member balances.

- Show balance, outstanding guest cash/check, last-entry date, and membership status.

- Show summary totals separately: member balances due, member credit balances, outstanding guest cash/check, and net ledger balance.

- Export entries for the currently selected members and date/category filters to CSV with spreadsheet-injection sanitization. Summary totals remain all-history totals over the selected members.

## 5.3 Treasurer member-ledger detail

- Show the selected member, balance in plain language, outstanding guest cash/check, and complete ledger.

- Allow posting of manual charge, payment, general credit, and guest cash/check collected.

- Allow a remittance action only against one or more open guest cash/check entries.

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

## 5.5 Payment-method handling

Payment handling depends on whether money was paid directly to the treasurer/club account or temporarily handed to a member/board member.

| **Payer / method** | **MVP behavior** |
|--------------------|------------------|
| Member, On Account | Post the flight charge only; the member balance increases. |
| Member, Zelle | Post the flight charge plus a `PAYMENT` credit only after the treasurer or authorized verifier confirms the Zelle payment was sent directly to the treasurer/club account. |
| Member, Cash or Check | Payment is uncommon. The member receives a payment credit when the cash/check is accepted, but Section 18 must confirm whether the receiving board member also gets a remittance-tracked custody entry until the treasurer receives it. |
| Guest, Cash or Check handed to a member/board member | Treat as remittance-style handling: record who received the funds and create a guest cash/check collection that remains outstanding until remitted to the treasurer. |
| Guest, Zelle | Require verification that the payment was sent directly to the treasurer/club account before the flight is marked paid; do not create a member-held cash remittance entry. |

- A Zelle reference, confirmation note, or verifier must be recorded before a Zelle-paid flight is treated as financially complete.

- Cash or check handed to a member/board member is not equivalent to direct club payment until remitted or otherwise reconciled.

# 6. Guest cash/check remittance workflow

Guest cash/check is operationally distinct from a personal purchase even though it debits the receiving member’s ledger. The ledger must preserve that distinction and give the treasurer an outstanding remittance queue. The existing `GUEST_CASH_COLLECTED` kind covers guest cash and guest checks received by a member/board member for MVP, with `payment_method` distinguishing cash from check.

1.  A guest pays cash or check for a flight to a member or board member.

2.  An authorized user posts Guest Cash Collected against the receiving member, including the guest/payer name, payment method, reference when applicable, and related flight when available.

3.  The entry debits the receiving member’s ledger and is marked Awaiting Remittance.

4.  The treasurer receives the cash/check and selects the open collected entry.

5.  The system atomically posts a linked Cash Remitted credit and marks the collected entry Remitted.

6.  If the remittance was erroneous, the treasurer reverses the remittance and the collection becomes Awaiting Remittance again.

7.  A collection with an active remittance cannot be reversed. The remittance must be reversed first; the now-open collection may then be reversed.

| **Entry**            | **Effect** | **Operational state** | **Linked record**      |
|----------------------|------------|-----------------------|------------------------|
| Guest Cash Collected | +\$100     | Awaiting remittance   | Flight (optional)      |
| Cash Remitted        | −\$100     | Remitted              | Clears collected entry |

- Partial remittance is out of MVP scope; one remittance clears one collected entry in full.

- A collected entry cannot be remitted twice; enforce this with a database uniqueness constraint.

- Remittance state is derived, not stored mutably: a collection is Reversed when it has an active reversal; Remitted when it has an unreversed linked remittance; otherwise it is Awaiting Remittance. A reversed remittance does not clear the collection.

- `remit_guest_cash` and both reversal paths lock the collection, its linked remittance when present, and their reversal rows in one transaction before validating the transition.

- A related guest flight must not also remain categorized as unpaid in any future payment-status feature.

# 7. Data model

Create a dedicated Django app named billing. This prevents authentication ambiguity around “accounts” and keeps ledger concerns out of the already large logsheet models module.

## 7.1 Ledger

| **Field**  | **Type / constraint**          | **Purpose**                                   |
|------------|--------------------------------|-----------------------------------------------|
| id         | BigAutoField                   | Primary key                                   |
| member     | OneToOneField(Member, PROTECT) | One ledger per member                         |
| created_at | DateTimeField(auto_now_add)    | Audit timestamp                               |

Do not store a mutable balance or ledger-level update timestamp in the MVP. Calculate the balance with an indexed aggregate over posted entries. A cached balance may be introduced later only with database locking and reconciliation checks.

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
| flight             | FK Flight, PROTECT, nullable                 | Related source flight                |
| misc_charge        | FK existing charge model, PROTECT, nullable  | Legacy/source link                   |
| source_key         | CharField(160), nullable                     | Idempotency key                      |
| reverses           | OneToOne self, PROTECT, nullable             | Original entry reversed              |
| cash_collection    | OneToOne self, PROTECT, nullable             | Collection cleared by remittance     |
| guest_name         | CharField(150, blank=True)                   | Guest/payer label                    |
| payment_method     | TextChoices, nullable                        | Cash/check/Zelle/card/ACH/other      |
| reference          | CharField(100, blank=True)                   | Check, receipt, or deposit reference |

Ledger-entry kinds:

FLIGHT_CHARGE, MISC_CHARGE, MANUAL_CHARGE, PAYMENT, CREDIT,
GUEST_CASH_COLLECTED, CASH_REMITTED, OPENING_BALANCE, REVERSAL

| **Kind**              | **Allowed effect** | **Notes**                                      |
|-----------------------|--------------------|------------------------------------------------|
| FLIGHT_CHARGE         | DEBIT              | Posted from finalized flight allocation        |
| MISC_CHARGE           | DEBIT              | Posted from existing miscellaneous charge      |
| MANUAL_CHARGE         | DEBIT              | Treasurer-entered charge                       |
| PAYMENT               | CREDIT             | Money received from or for a member            |
| CREDIT                | CREDIT             | Adjustment in the member's favor               |
| GUEST_CASH_COLLECTED  | DEBIT              | Guest cash/check held by the member            |
| CASH_REMITTED         | CREDIT             | Clears one guest cash/check collection         |
| OPENING_BALANCE       | DEBIT or CREDIT    | Debit for amount owed; credit for member credit |
| REVERSAL              | Opposite original  | Must match the reversed entry amount           |

- Check constraint: amount \> 0.

- Check constraints enforce amount, local kind/effect combinations, and locally testable required/forbidden fields. PostgreSQL/Django row checks cannot compare a reversal or remittance with another row.

- Cross-row rules—including opposite reversal effect and amount, same-ledger reversal/remittance links, valid source kind, and remittance amount—are enforced by the locked posting services and covered by concurrency tests.

- Source foreign keys use `PROTECT` so a posted ledger entry cannot silently lose its audit source. If a source record genuinely cannot be retained as a foreign key during migration, the importer must store a stable `source_key`, reference, and member-visible description that preserve traceability.

- Unique constraint on non-null source_key for idempotent automatic/import posting.

- Unique one-to-one reversal relation prevents multiple reversals of the same entry.

- Unique one-to-one cash_collection relation prevents duplicate remittance.

- Indexes: `(ledger, effective_date, created_at, id)`, kind, source_key, created_at, and the fields used to derive open guest remittance state.

## 7.3 FlightChargeSnapshot

Create a companion snapshot row for every `FLIGHT_CHARGE` entry. This row is the immutable billing evidence used for later corrections and reconciliation.

| **Field**            | **Type / constraint**                        | **Purpose**                                      |
|----------------------|----------------------------------------------|--------------------------------------------------|
| ledger_entry         | OneToOneField(LedgerEntry, PROTECT)          | The posted `FLIGHT_CHARGE` entry                 |
| flight               | FK Flight, PROTECT                           | Source flight                                    |
| billed_member        | FK Member, PROTECT                           | Member charged by this allocation                |
| tow_amount           | Decimal(12,2), \>= 0                         | Frozen tow component                             |
| rental_amount        | Decimal(12,2), \>= 0                         | Frozen aircraft rental component                 |
| instruction_amount   | Decimal(12,2), \>= 0                         | Frozen instruction component                     |
| total_amount         | Decimal(12,2), \> 0                          | Frozen total billed to this member               |
| allocation_rule      | CharField(50)                                | Rule used, such as full/even/tow/rental/custom   |
| allocation_version   | PositiveIntegerField                         | Source version for correction source keys        |
| allocation_snapshot  | JSONField                                    | Frozen inputs needed to explain the calculation  |
| created_at           | DateTimeField(auto_now_add)                  | Snapshot creation timestamp                      |

- `total_amount` must equal the linked ledger entry amount.

- `tow_amount + rental_amount + instruction_amount` must equal `total_amount`; enforce locally where possible and in the posting service with Decimal quantization.

- Snapshot rows are append-only. A correction creates reversal entries and replacement snapshots with a higher allocation version.

## 7.4 Site configuration additions

Add a configurable shared-flight split grace period to `SiteConfiguration`.

| **Field**                       | **Type / constraint** | **Purpose** |
|---------------------------------|-----------------------|-------------|
| member_split_grace_period_hours | PositiveIntegerField  | Hours after day-end closure when eligible billed members may change only the split selection |

- A value of 0 disables member self-service split changes after closure.

- The grace-period deadline is calculated from the logsheet's finalized timestamp in `SiteConfiguration.club_timezone`.

- The billing-readiness check must fail if the grace-period value is missing or invalid. The exact MVP value/default is a club policy decision recorded in Section 18.

# 8. Posting services and invariants

All ledger changes must go through `billing/services.py`. Views, admin actions, signals, and management commands must not create entries directly.

| **Service**                              | **Responsibility**                                                         |
|------------------------------------------|----------------------------------------------------------------------------|
| post_entry(...)                          | Validate kind/effect, quantize currency, set actor, create immutable entry |
| post_flight_charges(flight, actor)       | Create idempotent entries required by the frozen allocation and settlement |
| post_misc_charge(charge, actor)          | Create idempotent debit for existing miscellaneous member charge           |
| reverse_entry(entry, actor, reason)      | Lock original; create linked opposite-effect reversal                      |
| remit_guest_cash(collection, actor, ...) | Lock collection; create linked credit; prevent duplicates                  |
| get_balance(ledger, as_of=None)          | Sum signed effects through an optional date                                |
| reconcile_ledger(ledger)                 | Compare source records with ledger and report anomalies                    |

- Wrap posting, reversal, and remittance in `transaction.atomic()`.

- Use `select_for_update()` for reversal and remittance targets.

- Use database uniqueness, not an application-only pre-check, for idempotency.

- Catch `IntegrityError` from duplicate source keys and return the existing entry when it is semantically identical.

- A duplicate source key whose persisted ledger, kind, effect, amount, effective date, or source identity differs is a semantic conflict: raise a domain error, log structured identifiers, and fail the surrounding transaction.

- Every mutating service requires a non-null `Member` actor. Management commands that post or correct entries require an explicit `--actor` member ID or username and record that member in `created_by`; dry-run commands do not require an actor.

- Treat ledger immutability as a database contract, not only a view/admin convention. Add PostgreSQL triggers or equivalent migration-managed safeguards that reject `UPDATE` and `DELETE` on `LedgerEntry` and `FlightChargeSnapshot` after insertion, except during explicit controlled migrations documented in the migration file.

- Application code should still mark model fields read-only and avoid exposing save/delete paths, but tests must prove that direct ORM update/delete attempts fail or are otherwise prevented by the chosen database safeguard.

# 9. Flight-charge integration

## 9.1 Posting point

At successful day-end logsheet closure, freeze the operational flight record and post the then-current flight allocation. Shared-flight allocations retain the repository's existing two-member split choices for MVP. Eligible billed members may change only the split selection during the configured grace period; after that, only treasurer or superuser may change the allocation through the correction workflow in Section 9.4. Register posting in the same database transaction as finalization. A post-save signal alone is not sufficient because it obscures error handling and can fire during maintenance tasks.

The repository currently has more than one finalization entry point. Extract one domain service that locks the logsheet and its flights, validates financial completeness, snapshots costs, posts all ledger entries, marks the logsheet finalized, and creates the revision record. Every UI, admin, command, and API finalization path must call this service.

## 9.2 Entry granularity

- Create one `FLIGHT_CHARGE` entry per billed member per flight. Its amount is that member’s total allocated tow, rental, and instruction charge.

- Keep cost calculation and ledger posting separate. Logsheet/domain cost-allocation code computes the billable components and split allocation; billing receives that result as frozen input and posts ledger entries. Billing code must not reimplement tow, rental, instruction, rate, or split calculation rules.

- The MVP allocation model keeps the existing two-member split choices: `even`, `tow`, `rental`, and `full`. Implement the allocation API so later arbitrary percentages or more than two payers can be added without changing ledger-entry semantics.

- Preserve component amounts in a one-to-one `FlightChargeSnapshot` companion model linked to the `FLIGHT_CHARGE` entry. Store the frozen tow, rental, instruction, and total amounts plus the allocation rule/version used. The component sum must equal the ledger-entry amount.

- For split flights, generate independent entries with source keys such as flight:{flight_id}:member:{member_id}:v1.

- Commercial rides excluded by current personal-charge logic remain excluded unless a member is explicitly the payer.

- Zero-dollar allocations do not produce ledger entries.

- A flight allocation version starts at 1 when the flight is first posted. Any replacement caused by a post-closure allocation correction increments the version and uses a new source key. Reusing a previous source key for changed economics is a semantic conflict, not idempotency.

## 9.3 Corrections after posting

Once a flight charge is posted, source edits must not mutate the ledger row. A correction service compares the new allocation to the posted snapshot. If different, it reverses the old entry and posts a replacement using a new source version. The correction must be explicit and auditable.

A ledger-posted logsheet cannot return to the repository's unrestricted editable state. Existing “revise/unfinalize” entry points must reject it and direct authorized users to audited correction workflows. Operational corrections that are genuinely required after posting must use a dedicated service that locks the logsheet, records the reason and before/after snapshot, and reverses/replaces every affected ledger entry atomically; merely toggling `finalized` is prohibited.

> **Compatibility requirement:** The existing `update_flight_costs` command must either skip ledger-posted flights by default or invoke the correction service. It must never change a posted flight’s source costs without reconciling the ledger.

## 9.4 Day-end closure, grace period, and allocation corrections

Separate operational closure from narrow split correction. Closing a daily logsheet must not leave the entire flight record editable.

- An authorized duty officer or existing logsheet closer may close the logsheet at the end of the operating day. Closure freezes flight times, aircraft, tow data, participants, rates, miscellaneous charges, and all other operational fields.

- During the configured grace period, a member who is one of the billed participants on a shared flight may change only that flight's split selection. The member may not change participants, total billable amount, rate inputs, flight data, charge category, another unrelated flight, or any non-split financial field.

- A shared allocation must continue to total exactly 100 percent, or the exact frozen flight charge when fixed currency shares are supported. Rounding must be deterministic and preserve the original total.

- The member-facing grace-period form must expose only the existing MVP split choices unless a later feature explicitly expands the allocation model. It must reject stale submissions after the deadline using server-side club-timezone calculation.

- Every allocation change must record the actor, timestamp, previous split, new split, reason, and affected flight. Reason is optional for member changes during the grace period and required for treasurer/superuser corrections.

- Applying a post-closure allocation change must atomically reverse the superseded FLIGHT_CHARGE entries and post replacement entries for every affected member. It must not reopen the daily logsheet, mutate posted ledger rows, or bypass the cost-allocation API.

- After the grace period expires, members have read-only access. Only treasurer and superuser may change a posted shared-flight allocation, and only through the audited correction service with a required reason.

- The configured `SiteConfiguration.club_timezone` defines day-end, grace-period deadlines, and reporting month boundaries.

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

- Source records linked from posted entries, including flights and miscellaneous charges, must not be deleted through application or admin workflows. If legacy code exposes such deletion, it must refuse deletion once a billing ledger entry references the source and explain that a ledger correction is required instead.

- Do not place internal_note in member templates, member CSVs, notifications, or generic serialization.

# 12. Migration and rollout

1.  Create billing app, schema, constraints, services, permissions, and read-only admin.

2.  Deploy the schema and enable idempotent ledger dual-write during finalization while keeping member and treasurer ledger reads hidden; create ledgers lazily.

3.  Record the deployment watermark, then run a dry-run backfill report over finalized flights and existing miscellaneous charges before that watermark. New finalizations are already protected by dual-write.

4.  Select a ledger cutoff date and obtain each member’s opening balance as of the preceding day.

5.  Post OPENING_BALANCE entries at the cutoff, then backfill source charges on or after the cutoff with deterministic source keys.

6.  Reconcile every member against authoritative opening balances, source records, and the current My Flight Charges output; sample-only reconciliation is insufficient for cutover.

7.  Run an idempotent catch-up across the watermark and require zero unexplained gaps or semantic conflicts, then enable the treasurer UI.

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

- Treasurer CSV: member, membership status, entry ID, category, effect, amount, effective date, source/reference, creator, created timestamp, reversal state, and remittance state.

- Sanitize cells beginning with =, +, -, or @ before CSV output.

- Provide a management command that reports orphaned source records, duplicate source keys, reversed-without-replacement items, and remittance mismatches.

- Summary totals must show receivables, credits, guest cash/check awaiting remittance, and net separately; do not imply they are economically identical.

- For a selected member set, `balances_due` is the sum of positive all-history balances, `credit_balances` is the absolute value of negative all-history balances, and `net_ledger_balance = balances_due - credit_balances`. Outstanding guest cash/check is reported alongside these totals and is not added to net ledger balance because it is already represented by ledger debits.

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

- A duplicate source key with different semantics fails the surrounding transaction and does not return the unrelated existing entry.

- Split flight creates exactly one correct entry per billed member.

- Billing services post frozen allocation results supplied by the logsheet cost-allocation API; tests must fail if billing code reimplements cost calculation rules directly.

- `member_split_grace_period_hours` accepts valid nonnegative values, treats 0 as disabled when that policy is selected, and rejects missing/invalid configuration in billing-readiness checks.

- Reversal creates one opposite entry and a second reversal attempt fails safely.

- Cash remittance clears exactly one collection and duplicate remittance is prevented.

- Reversing a remittance reopens its collection; a collection with an active remittance cannot be reversed; reversing the reopened collection removes it from outstanding cash.

- Internal notes never appear in member-facing serialization.

- Direct ORM update/delete attempts against `LedgerEntry` and `FlightChargeSnapshot` are blocked by the database immutability safeguard.

- A posted source flight or miscellaneous charge cannot be deleted while referenced by a ledger entry.

## 15.2 View and permission tests

- A member can view and export only their own ledger.

- Changing a URL cannot expose another member’s ledger.

- A non-treasurer POST is rejected even if form fields are valid.

- Treasurer and superuser can view and post; configurable treasurer title changes do not break authorization.

- CSRF and POST-only protections apply to every mutation.

- Member page correctly renders due, settled, and credit states.

- A member payer defaults to Member Balance; a non-member payer cannot be completed without an explicit valid charge type.

- Guest cash received by a member creates Guest Cash Collected rather than an ordinary manual or flight charge.

- Guest check received by a member follows the same remittance workflow as guest cash, with payment method/reference preserved.

- Guest Zelle payment cannot mark a flight paid until a treasurer or authorized verifier records that it was sent directly to the treasurer/club account.

- Eligible billed members can change only the split selection during the configured grace period after day-end closure.

- Member split-change attempts after the grace-period deadline are rejected server-side.

- Treasurer and superuser can submit an audited shared-flight allocation correction using the existing split choices after the grace period.

## 15.3 Integration and migration tests

- Finalizing a logsheet posts all expected nonzero member allocations once.

- Flight posting creates a `FlightChargeSnapshot` whose component total equals the ledger entry amount and whose allocation version is reflected in the source key.

- A finalization failure rolls back both finalized state and ledger entries.

- Every existing finalization entry point delegates to the shared finalization service.

- Attempting to unfinalize a ledger-posted logsheet is rejected; an authorized correction produces an audit record plus balanced reversal/replacement entries.

- Flight correction produces reversal plus replacement without modifying original.

- A split-allocation correction uses the shared cost-allocation API, preserves deterministic rounding, and posts replacement ledger entries without recalculating costs inside billing.

- Opening balance plus post-cutoff activity matches the expected member balance.

- A filtered ledger shows the correct brought-forward and deterministic running balances, including after a backdated entry.

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

8.  A \$100 guest cash/check collection appears as outstanding remittance and a debit; remittance posts a linked \$100 credit and clears the outstanding state.

9.  Concurrent duplicate posting or remittance cannot alter the balance twice.

10. The migration can be dry-run, rerun safely, and reconciled to authoritative opening balances.

11. Closing a day locks operational logsheet fields while allowing eligible billed members to change only shared-flight split selection during the configured grace period.

12. A member can change a valid shared-flight split during the grace period; the change reverses and replaces ledger entries atomically without reopening the day.

13. After the grace period, a member cannot change a shared-flight split, total charge, or flight details.

14. A treasurer or superuser can change a valid shared-flight split after the grace period using the existing split choices; the change requires a reason and creates the same reversal/replacement audit trail.

15. Concurrent or stale allocation edits are rejected safely and cannot create duplicate or unbalanced ledger entries.

# 17. Implementation sequence

| **Phase**              | **Deliverables**                                    | **Exit condition**                            |
|------------------------|-----------------------------------------------------|-----------------------------------------------|
| 1\. Ledger core        | Models, constraints, services, admin, unit tests    | Manual service posting and balance tests pass |
| 2\. Flight integration | Finalization hook, snapshots, corrections, backfill | Finalized flights post idempotently           |
| 3\. Treasurer UI       | List/detail/forms/cash workflow/export              | Treasurer acceptance scenarios pass           |
| 4\. Member UI          | Expanded page, history, balance, CSV                | Members see only their own complete ledger    |
| 5\. Migration          | Cutoff, opening balances, import, reconciliation    | Totals signed off by treasurer                |
| 6\. Rollout            | Feature flag, monitoring, docs                      | Ledger is authoritative for My Flight Charges |

# 18. Decisions and implementation-readiness gate

Coding may begin only after each decision below is answered in this document and any resulting schema, service, permission, migration, and acceptance requirements are incorporated into the preceding sections. Moving a question to an issue tracker without specifying the MVP behavior does not satisfy this gate.

1.  What cutoff date and authoritative source will supply opening balances?

2.  Who besides the treasurer may record Guest Cash Collected, both during flight finalization and as a standalone correction: duty officers, board members, or treasurer only?

3.  Should the My Flight Charges navigation label remain unchanged or become “My Charges & Balance”?

4.  The authoritative miscellaneous-charge source is `logsheet.MemberCharge`; confirm whether any non-logsheet `MemberCharge` records should be migrated, because finalized logsheet charges are already protected from application/admin edits and deletes.

5.  For member cash/check handed to a board member, should the paying member receive an immediate `PAYMENT` credit only, or should the receiving board member also receive a remittance-tracked custody debit until the treasurer receives the funds?

6.  Should MVP introduce a durable per-flight settlement record for commercial/guest/non-member flights, or leave all non-member settlement outside the ledger feature?

7.  If non-member settlement is included, which charge types are enabled, who may select Waived/No Charge or Invoice/Receivable, and who receives a Guest Cash Collected debit when cash changes hands?

8.  What configurable member split-change grace period should MVP use by default, and should a value of 0 be allowed to disable member self-service split changes?

The configured `SiteConfiguration.club_timezone` defines day-end, grace-period deadlines, and month-end. Deployment must fail its billing-readiness check if this remains blank/UTC unintentionally.

Resolved decisions:

- MVP retains the existing two-member split choices (`even`, `tow`, `rental`, `full`) and designs the allocation API for later extension to arbitrary percentages or more payers.

- Ledger posting remains separate from cost calculation. Cost-allocation code computes billable components and allocation outputs; billing records frozen results and corrections.

- Eligible billed members may change only shared-flight split selection during the configured grace period; after the grace period, only treasurer and superuser may change posted shared-flight allocations.

## 18.1 Decision capture worksheet

Use this worksheet to record the answers before implementation starts. Once a row is answered, update the relevant requirements above instead of leaving the answer only in this table.

| **Decision** | **Answer to record** | **Why it matters** |
|--------------|----------------------|--------------------|
| Opening balance cutoff | Exact cutoff date and authoritative balance source | Determines migration shape and prevents false balances |
| Guest cash/check posting roles | Roles allowed during finalization and standalone correction | Drives permissions, forms, and audit tests |
| Member navigation label | Keep “My Flight Charges” or rename to “My Charges & Balance” | Drives menu/template copy and member training |
| Miscellaneous charge source | Confirm only `logsheet.MemberCharge`, or list other sources | Prevents missed historical charges |
| Logsheet payment methods | Confirm remaining member cash/check custody behavior | Prevents paid flights from leaving balances due or member-held funds from being lost outside remittance tracking |
| Non-member settlement | Include durable settlement records in MVP, or defer outside ledger | Determines whether new non-member schema is required |
| Enabled non-member charge types | Allowed charge types, waiver/invoice roles, and cash recipient rules | Drives validation and financial-completeness checks |
| Shared-flight split model | Resolved: keep existing two-member choices and make allocation API extensible | Determines form scope, data model changes, and correction workflow |
| Split grace period | Exact configured duration/default and whether 0 disables self-service | Drives member edit windows, stale-submit behavior, and permission tests |
| Allocation correction roles | Resolved: member self-service only during grace period; treasurer and superuser after grace | Drives permissions and after-closure audit requirements |

## 18.2 Ready-to-code checklist

- [ ] Section 18 decisions are answered with concrete MVP behavior.

- [ ] Each answer is incorporated into Sections 5-16, not left only in Section 18.

- [ ] The implementation sequence in Section 17 still matches the selected decisions.

- [ ] Acceptance criteria cover each selected payment, settlement, split, and correction path.

- [ ] Migration inputs are identified: cutoff date, opening balances, source systems, actor for committed imports, and reconciliation sign-off owner.

- [ ] The spec no longer contains unanswered policy phrases such as “club configuration decision” for MVP behavior.

## 18.3 Reviewer-recommended MVP defaults to confirm

These are recommendations, not approved requirements. Use them to speed up the club-policy conversation; once accepted or rejected, fold the chosen answer into the main sections and remove or update this table.

| **Decision** | **Recommended MVP default** | **Reason** |
|--------------|-----------------------------|------------|
| Member cash/check custody | Paying member gets a `PAYMENT` credit when funds are accepted; receiving board member also gets a remittance-tracked custody debit until treasurer receipt | Preserves the payer's correct balance and keeps member-held club funds visible |
| Non-member settlement | Defer full non-member receivables; include only the minimum settlement fields needed to close a logsheet and route cash received by a member into Guest Cash Collected | Keeps MVP focused on member balances while preventing unpaid/paid ambiguity at day-end |
| Non-member charge types | Enable Cash Collected, Check, Card/Electronic Payment, Waived/No Charge, and Charged to Sponsoring Member; defer Invoice/Receivable unless the club already tracks named outside receivables in Manage2Soar | Avoids introducing a parallel customer/accounts-receivable system in a member-ledger feature |
| Waived/No Charge role | Treasurer or superuser only for MVP | Waivers affect revenue and need a tighter audit trail than ordinary flight entry |
| Guest cash/check posting roles | Treasurer, superuser, and the day-end logsheet closer during finalization; treasurer/superuser only for standalone correction | Lets normal operations close cleanly while keeping after-the-fact cash/check changes controlled |
| Shared-flight splits | Accepted: retain existing two-member split choices for MVP, keep allocation logic separate from ledger posting, make the allocation API extensible, and allow eligible billed members to change split selection during a configurable grace period | Avoids a larger allocation redesign while preserving accountability |
| Allocation corrections | Accepted: treasurer and superuser only after the member grace period expires | After grace, corrections are accounting events and should be intentionally narrow |
| Navigation label | Keep the existing route and URL; rename visible member navigation to “My Charges & Balance” only if the club is ready to announce the broader feature | Avoids surprising members during rollout while leaving a clearer label available |

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
