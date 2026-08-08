# Billing App - Data Models Documentation

## Model Overview

The billing app uses four core models that work together to provide a complete financial ledger system with immutability guarantees.


```mermaid
erDiagram
    auth_user ||--|| Ledger : "has one"
    Ledger ||--o{ LedgerEntry : "entries"
    LedgerEntry ||--o| FlightChargeSnapshot : "flight_snapshot"
    LedgerEntry ||--o| BillingPeriodEvent : "events"
    AuthUser : "settings.AUTH_USER_MODEL"

    Ledger {
        uuid id PK
        int member_id FK "FK to auth_user"
        datetime created_at
    }

    LedgerEntry {
        int id PK
        int ledger_id FK "FK to Ledger"
        varchar kind
        varchar effect
        decimal amount
        date effective_date
        varchar member_description
        text internal_note
        int created_by FK "FK to auth_user"
        datetime created_at
        varchar source_key
        uuid correction_group
        int flight_id FK "FK to logsheet.Flight"
        int reverses FK "FK to LedgerEntry"
    }

    FlightChargeSnapshot {
        int id PK
        int ledger_entry_id FK "FK to LedgerEntry"
        int flight FK "FK to logsheet.Flight"
        int billed_member FK "FK to auth_user"
        decimal tow_amount
        decimal rental_amount
        decimal instruction_amount
        decimal total_amount
        varchar allocation_rule
        int allocation_version
        json allocation_snapshot
        datetime created_at
    }

    BillingPeriodEvent {
        int id PK
        int period FK "FK to BillingPeriod"
        varchar action
        text reason
        int actor FK "FK to auth_user"
        datetime created_at
    }

    BillingPeriod {
        int id PK
        int year
        smallint month
        bool is_closed
    }
```

## Detailed Model Specifications

### 1. Ledger Model (`billing/models.py`)

**Purpose**: Represents the immutable financial history for one member of the club. Each member gets exactly one ledger that persists for the lifetime of their membership.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (auto) | Primary key |
| `member` | OneToOneField → User | Link to Django auth user |
| `created_at` | DateTimeField | When ledger was created (auto_now_add) |

#### Properties

- **`balance`** (property): Returns the computed current balance for this member. Positive means money owed to the club, negative means overpayment/credit. Computed dynamically via `billing.services.get_balance(ledger)`.

#### Constraints

- Unique constraint on `member` field (OneToOne relationship enforced by Django ORM and database)
- Foreign key protection: `on_delete=models.PROTECT` prevents deletion if ledger exists

#### Usage Example

```python
from billing.models import Ledger
from billing.services import get_balance

# Get or create ledger for member
ledger, created = Ledger.objects.get_or_create(member=user)

# Compute balance (dynamic computation)
balance = get_balance(ledger)
print(f"Balance: ${balance:.2f}")  # "$123.45"

# Access via related name
user.billing_ledger.balance  # Returns current balance
```

#### Migration Notes

- Ledger creation must go through `billing.services.get_or_create_ledger()` to handle race conditions during concurrent access
- Once created, the ledger itself is immutable; only entries can be added

---

### 2. LedgerEntry Model (`billing/models.py`)

**Purpose**: Represents a single immutable financial transaction in a member's ledger. Entries cannot be modified or deleted after creation—corrections happen via reversal entries.

#### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID (auto) | PK | Primary key |
| `ledger` | ForeignKey → Ledger | PROTECT, related_name="entries" | Parent ledger |
| `kind` | CharField | max_length=32, Kind.choices | Entry type |
| `effect` | CharField | Effect.choices | Debit or credit |
| `amount` | DecimalField | max_digits=12, decimal_places=2 | Amount (always positive) |
| `effective_date` | DateField | | Transaction date |
| `member_description` | CharField | max_length=255 | Display name for entry |
| `internal_note` | TextField | blank=True | Internal audit notes |
| `created_by` | ForeignKey → User | PROTECT, related_name="created_billing_entries" | Who created it |
| `created_at` | DateTimeField | auto_now_add | Timestamp |
| `source_key` | CharField | max_length=160, blank/null, unique if set | Idempotency key |
| `correction_group` | UUIDField | blank/null, db_index=True | Links correction to originals |
| `flight` | ForeignKey → Flight | PROTECT, blank/null, related_name="billing_entries" | Linked flight (if applicable) |
| `reverses` | OneToOneField → self | PROTECT, blank/null, related_name="reversal" | Reversed entry reference |

#### Kind Choices

| Value | Display | Description | Valid Effect |
|-------|---------|-------------|--------------|
| `flight_charge` | Flight charge | Automated flight allocation | DEBIT only |
| `misc_charge` | Miscellaneous charge | Ad-hoc charges | DEBIT only |
| `manual_charge` | Manual charge | Treasurer-posted charge | DEBIT only |
| `payment` | Payment | Money received from member | CREDIT only |
| `credit` | Credit | Applied credit/cancellation | CREDIT only |
| `opening_balance` | Opening balance | Initial balance for new members | Either |
| `reversal` | Reversal | Correction of previous entry | Must have reverses reference |

#### Effect Choices

| Value | Display | Description |
|-------|---------|-------------|
| `debit` | Debit | Amount owed (increases balance) |
| `credit` | Credit | Amount paid (decreases balance) |

#### Properties

- **`signed_amount`** (property): Returns `-amount` for credits, `+amount` for debits. Used in balance calculations.

- **`get_kind_display()`**: Django auto-generated method returns display name for kind

#### Database Constraints

1. **Amount must be positive**:
   ```sql
   CHECK (amount > 0)
   CONSTRAINT billing_entry_amount_positive
   ```

2. **Unique source key** (when set):
   ```sql
   UNIQUE (source_key) WHERE source_key IS NOT NULL
   CONSTRAINT billing_entry_source_key_unique
   ```

3. **Kind/Effect validity**:
   ```sql
   CHECK (kind/effect combinations are valid)
   CONSTRAINT billing_entry_kind_effect_valid
   ```

4. **Reversal must reference original**:
   ```sql
   CHECK (reverses IS NOT NULL IF kind='reversal')
   CONSTRAINT billing_reversal_has_original
   ```

5. **Flight charge must link to flight**:
   ```sql
   CHECK (flight IS NOT NULL IF kind='flight_charge')
   CONSTRAINT billing_flight_charge_has_flight
   ```

#### Indexes

- `billing_entry_statement_idx` on `(ledger, effective_date, created_at, id)` — Optimizes balance queries and statement generation
- `billing_entry_kind_idx` on `(kind)` — Optimizes filtering by entry type

#### Methods

```python
# In LedgerEntry model class:

def clean(self):
    """Validates kind/effect combinations and required relationships."""
    # Must be posted through billing services only
    if self.kind == 'reversal' and not getattr(self, '_service_created', False):
        raise ValidationError("Reversals must be created through billing services.")

    # Original entry check for reversals
    if self.kind == 'reversal':
        original = self.reverses
        if original.ledger_id != self.ledger_id:
            raise ValidationError("Must use same ledger as original")
        if original.amount != self.amount:
            raise ValidationError("Must match original amount")
        if original.effect == self.effect:
            raise ValidationError("Must have opposite effect")

def save(self, *args, **kwargs):
    """Post entries are immutable once created."""
    if self.pk:
        raise ValidationError("Posted billing entries cannot be edited.")
    self.full_clean()
    return super().save(*args, **kwargs)

def delete(self, *args, **kwargs):
    """Entries cannot be deleted."""
    raise ValidationError("Posted billing entries cannot be deleted.")
```

#### Immutability Enforcement

| Operation | Behavior | How |
|-----------|----------|-----|
| `Entry.objects.get(pk=x).save()` | Raises ValidationError | `save()` checks `self.pk` |
| `entry.delete()` | Raises ValidationError | `delete()` always raises |
| Direct SQL UPDATE/DELETE | Blocks via database triggers | Migration 0002 installs triggers |

#### Example Usage

```python
from billing.services import post_charge, get_balance
from billing.models import LedgerEntry

# Post a charge (through service layer only)
entry = post_charge(
    member=member,
    actor=admin,
    amount=150.00,
    effective_date=today,
    description="Monthly membership fee",
    kind=LedgerEntry.Kind.MANUAL_CHARGE,
)

# Query entries
entries = LedgerEntry.objects.filter(
    ledger=ledger,
    kind=LedgerEntry.Kind.FLIGHT_CHARGE,
    created_at__gte=start_date,
).order_by('-effective_date')

# Check reversal status
if entry.reverses is None:
    print("Entry is not reversed")
else:
    print(f"Reversed by {entry.reverses}")
```

---

### 3. BillingPeriod Model (`billing/models.py`)

**Purpose**: Tracks the open/closed state of one calendar billing month. When a period is closed, no new charges can be posted for that date range (enforced at application level; database enforcement would require additional migrations).

#### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | AutoField | PK | Primary key |
| `year` | PositiveIntegerField | | Billing year (e.g., 2026) |
| `month` | PositiveSmallIntegerField | | Billing month (1-12) |
| `is_closed` | BooleanField | False | Whether period is closed |

#### Constraints

```sql
-- Prevent duplicate periods
UNIQUE (year, month)
CONSTRAINT billing_period_unique_month

-- Ensure valid month
CHECK (month >= 1 AND month <= 12)
CONSTRAINT billing_period_month_valid
```

#### Ordering

Ordered by most recent first: `("-year", "-month")`

#### Methods

```python
def __str__(self):
    return f"{self.year}-{self.month:02d} ({'closed' if self.is_closed else 'open'})"
    # Examples: "2026-01 (open)", "2025-12 (closed)"
```

#### Usage Example

```python
from billing.models import BillingPeriod

# Check if January 2026 is closed
period = BillingPeriod.objects.get(year=2026, month=1)
if period.is_closed:
    # Post correction instead of new charge
    corrections = correct_flight_charges(...)
else:
    # Can post new charges
    posted = post_flight_charges(...)

# Get current open period
open_period = BillingPeriod.objects.filter(is_closed=False).first()

# Mark period as closed
period.is_closed = True
period.save()
```

#### Period Management Workflow

```
Month starts → is_closed=False → Open for new charges
                    ↓
              Manual/Auto close trigger
                    ↓
          is_closed=True → No new charges
                    ↓
              Correction workflow if needed
                    ↓
         Finalized for next month's statements
```

---

### 4. BillingPeriodEvent Model (`billing/models.py`)

**Purpose**: Audit trail recording when and why billing periods were closed or reopened. Every period state change creates an event record.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | AutoField | PK |
| `period` | ForeignKey → BillingPeriod | The period affected |
| `action` | CharField | "closed" or "reopened" |
| `reason` | TextField | Why the action was taken |
| `actor` | ForeignKey → User | Who took the action (nullable) |
| `created_at` | DateTimeField | When event occurred |

#### Action Choices

| Value | Display | Usage |
|-------|---------|-------|
| `closed` | Closed | Period finalized, no more changes |
| `reopened` | Reopened | Period reopened for corrections |

#### Example Usage

```python
from billing.models import BillingPeriodEvent

# Record a period close
event = BillingPeriodEvent.objects.create(
    period=period,
    action=BillingPeriodEvent.Action.CLOSED,
    reason="Monthly close - automated",
    actor=admin,
)

# Audit trail query
events = BillingPeriodEvent.objects.filter(
    period__year=2026,
    period__month=1,
).order_by('-created_at')

for event in events:
    print(f"{event.created_at}: {event.action} by {event.actor}")
    # "2026-02-01 03:00:00: closed by admin@club.org"
```

---

### 5. FlightChargeSnapshot Model (`billing/models.py`)

**Purpose**: Frozen allocation evidence for a posted flight charge. Captures exactly how the charge was calculated at posting time, preserving historical allocation rules and amounts even if they change later.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | AutoField | PK |
| `ledger_entry` | OneToOneField → LedgerEntry | The entry this snapshot describes |
| `flight` | ForeignKey → Flight | The flight being charged |
| `billed_member` | ForeignKey → User | Member being billed |
| `tow_amount` | DecimalField | Tow plane cost component |
| `rental_amount` | DecimalField | Glider rental cost component |
| `instruction_amount` | DecimalField | Instruction cost component |
| `total_amount` | DecimalField | Total charge (must equal sum of components) |
| `allocation_rule` | CharField | Rule used (e.g., "full", "pro_rata") |
| `allocation_version` | PositiveIntegerField | Version for tracking corrections |
| `allocation_snapshot` | JSONField | Full allocation state as JSON |
| `created_at` | DateTimeField | When snapshot was created |

#### Constraints

```sql
-- All amounts must be non-negative, total must be positive
CHECK (tow_amount >= 0 AND rental_amount >= 0
       AND instruction_amount >= 0 AND total_amount > 0)
CONSTRAINT billing_snapshot_amounts_valid

-- Components must equal total exactly
CHECK (tow_amount = total_amount - rental_amount - instruction_amount)
CONSTRAINT billing_snapshot_components_equal_total
```

#### Validation

```python
def clean(self):
    super().clean()

    # Total must match ledger entry amount
    if self.ledger_entry.total_amount != self.total_amount:
        raise ValidationError("Total must match entry")

    # Must link to a valid entry
    if not self.ledger_entry_id:
        raise ValidationError("Must identify a ledger entry")

    # Entry must be a flight charge
    if self.ledger_entry.kind != 'flight_charge':
        raise ValidationError("Requires flight charge entry")

    # Member must match
    if self.ledger_entry.member != self.billed_member:
        raise ValidationError("Member must match ledger")
```

#### Usage Example

```python
from billing.models import FlightChargeSnapshot
from decimal import Decimal

# Query snapshots for a flight
snapshots = FlightChargeSnapshot.objects.filter(
    flight=flight,
).order_by('-allocation_version')  # Latest first

for snapshot in snapshots:
    print(f"Version {snapshot.allocation_version}:")
    print(f"  Tow: ${snapshot.tow_amount}")
    print(f"  Rental: ${snapshot.rental_amount}")
    print(f"  Instruction: ${snapshot.instruction_amount}")
    print(f"  Total: ${snapshot.total_amount}")
    print(f"  Rule: {snapshot.allocation_rule}")

# Get latest version
latest = snapshots.first()
if latest:
    print(f"LATEST VERSION: {latest.allocation_version}")
```

#### Allocation Snapshot JSON Structure

The `allocation_snapshot` field stores the complete allocation state as JSON for historical reference:

```json
{
  "allocation_version": 2,
  "rate_tow": 3.50,
  "rate_rental": 80.00,
  "rate_instruction": 60.00,
  "split_type": "pro_rata",
  "split_percentages": {
    "member1": 0.5,
    "member2": 0.5
  },
  "effective_date": "2026-08-07"
}
```

---

## Balance Calculation Logic

The balance is computed as the sum of all signed amounts for a ledger:

```python
from billing.services import get_balance

def get_balance(ledger):
    """Compute current balance from all entries.

    Returns Decimal with 2 decimal places.
    Positive = money owed to club
    Negative = overpayment/credit
    """
    entries = ledger.entries.all()

    total = Decimal('0.00')
    for entry in entries:
        if entry.effect == 'debit':
            total += entry.amount  # Add charges
        else:
            total -= entry.amount  # Subtract payments

    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
```

## Correction Workflow Diagram

```
Flight Charge Posted (Version 1)
    ↓
LedgerEntry(created_by=admin, kind='flight_charge')
    ↓
FlightChargeSnapshot(allocation_version=1)

[Later: Correction Needed]
    ↓
correct_flight_charges() called
    ↓
Reversal Entry created (kind='reversal', reverses=original)
    ↓
Reversal FlightChargeSnapshot(allocation_version=2)
    ↓
New Charge Entry created with same amount but version 2
    ↓
correction_group links reversal + new entry together
```

## Model Relationships Summary

```mermaid
erDiagram
    User ||--|| Ledger : "billing_ledger (1:1)"
    User ||--o{ LedgerEntry : "created_billing_entries (1:N)"
    User ||--o{ BillingPeriodEvent : "billing_period_events (1:N)"

    Ledger ||--o{ LedgerEntry : "entries (1:N)"
    Ledger ||--|| BillingPeriod : "current (1:0..1)"
    Ledger .|-.|| FlightChargeSnapshot : "linked"

    LedgerEntry ||--o{ FlightChargeSnapshot : "flight_snapshot (1:0..1)"
    Flight }o--o{ LedgerEntry : "billing_entries (N:1)"

    BillingPeriod ||--o{ BillingPeriodEvent : "events (1:N)"
```

## Related Documentation

- [Architecture Overview](architecture.md) - System design and flow
- [API Reference](api.md) - Service layer functions
- [Development Guide](development.md) - Contributing to billing app
