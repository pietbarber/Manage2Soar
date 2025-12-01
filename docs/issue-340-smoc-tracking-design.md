# Issue #340: SMOC (Sole Manipulator of Controls) Tracking Design

## Background

Per **14 CFR 61.57**, a pilot needs **3 takeoffs and 3 landings in the last 90 days as Sole Manipulator of Controls (SMOC)** to:
- Carry passengers
- Provide flight instruction (instructor carrying a student)

This is a relatively recent regulatory change and creates a real tracking burden for soaring clubs.

## The Core Problem

In a two-seat glider with dual controls, **who was SMOC?**

### Scenarios We Can Infer Automatically

| Scenario | Who is SMOC? | How We Know |
|----------|-------------|-------------|
| **Solo flight** | Pilot | No instructor, no passenger = sole occupant |
| **Intro ride** | Rated pilot | Passenger can't fly |
| **Passenger flight** (rated pilot + passenger) | Rated pilot | Passenger presumably not manipulating controls |

### The Hard Scenario: Dual Instruction Flights

This is where it gets tricky:

1. **Student flies, instructor observes** → Student is SMOC
2. **Instructor demos** → Instructor is SMOC
3. **Mixed** → Need to track per-takeoff/landing

**The 4-flights-per-session problem:** An instructor might demo the first flight's takeoff and landing, then let the student do flights 2-4. That demo isn't recorded per-flight in the instruction reports—only the final proficiency score is captured.

### Two Rated Pilots Flying Together

When two CFI-Gs fly together:
- Often one person does all the flying (takeoff AND landing)
- Sometimes they split: Alice takes off, Bob lands
- The person manipulating controls is usually the one paying for rental, or the aircraft owner

---

## Design Goals

### Must Avoid: "Crying Wolf"

> "Oh the system always says that. It never gets currency right."

If we have too many false positives, duty officers will dismiss all warnings. **Better to miss a warning than cry wolf.**

### Balance Required

- **Accuracy** – minimize false positives/negatives
- **Low friction** – duty officer can't enter SMOC data per flight
- **Flexibility** – handle edge cases without complex UI

---

## Proposed Approach: "Optimistic with Override"

**Default to giving credit, allow corrections if needed.**

If we're going to be wrong, it's better to be wrong by *over-crediting* (member thinks they're current but is actually borderline) than *under-crediting* (system crying wolf).

---

## Data Model

### New Model: `SMOCCredit`

```python
class SMOCCredit(models.Model):
    """
    Tracks Sole Manipulator of Controls credits for 61.57 currency.
    Auto-generated from flights, can be manually adjusted.
    """
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='smoc_credits')
    date = models.DateField()
    takeoffs = models.PositiveSmallIntegerField(default=0)
    landings = models.PositiveSmallIntegerField(default=0)

    # Source tracking
    SOURCE_CHOICES = [
        ('auto_solo', 'Auto: Solo flight'),
        ('auto_pic_pax', 'Auto: PIC with passenger'),
        ('auto_dual_student', 'Auto: Dual instruction (as student)'),
        ('manual_instructor', 'Manual: Instructor claimed'),
        ('manual_external', 'Manual: External flight'),
        ('manual_override', 'Manual: Override'),
    ]
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)

    # Links (optional - for audit trail)
    flight = models.ForeignKey('logsheet.Flight', null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
```

### Why a Separate Table (vs. fields on Flight)?

1. **External flights** – Members can log flights done at other clubs
2. **Easy corrections** – Members/admins can add/edit SMOC credits without touching flight records
3. **Audit trail** – Clear source tracking for each credit
4. **Pattern tows** – 5 pattern tows = 5 T/Os + 5 landings (separate entries if needed)

---

## Auto-Generation Rules

When a flight is saved, generate SMOC credits:

| Flight Type | Pilot Gets | Instructor Gets | Rationale |
|-------------|-----------|-----------------|-----------|
| **solo** | 1 T/O + 1 landing | N/A | Sole occupant |
| **dual** | 1 T/O + 1 landing | **0** | Conservative: assume student flying |
| **intro** | 1 T/O + 1 landing | N/A | Passenger can't fly |
| **demo** | 1 T/O + 1 landing | N/A | Pilot demoing aircraft |
| **checkout** | 1 T/O + 1 landing | 0 | Assume checkee is flying |
| **proficiency** | 1 T/O + 1 landing | N/A | Rated pilot practicing |
| **passenger** | 1 T/O + 1 landing | N/A | Passenger not flying |

**Note:** For `dual` flights, we default to giving the **student** credit. Instructors can manually claim SMOC if they demoed.

---

## Handling Edge Cases

### Instructor Demos

**Option A: Post-flight correction**
- After logging, instructor can claim: "I was SMOC for this flight"
- Creates `SMOCCredit` with `source='manual_instructor'`

**Option B: Optional checkbox during flight entry**
- If `flight_type == 'dual'` and instructor is set, show optional "Instructor was SMOC" checkbox
- Only appears when relevant, doesn't burden normal data entry

### Two Rated Pilots

When two rated pilots fly together (e.g., checkout, proficiency):
- Default: Logged pilot gets full credit
- Optional: "Who was flying?" selector if both are rated
  - Pilot / Other / Split (Alice T/O, Bob landing)

### External Flights

Simple member self-service form:
```
"Log External Currency"
- Date: [date picker]
- Takeoffs: [number]
- Landings: [number]  
- Notes: [text] (e.g., "Flying N12345 at Blairstown")
```

Creates `SMOCCredit` with `source='manual_external'`.

---

## Warning Thresholds

### Be Conservative

Instead of warning when < 3, warn only when **0 or 1**:

```python
def should_warn_smoc_currency(member):
    """
    Only warn when we're CONFIDENT the member is non-current.
    Better to miss a warning than cry wolf.
    """
    count = get_smoc_count_90_days(member)
    # Only warn if 0 or 1 - they're definitely not current
    # At 2, they might have done something we don't know about
    return count <= 1
```

### Make Threshold Configurable

Start with a high threshold (warn at 0-1 only), adjust based on feedback:

```python
# In siteconfig
smoc_warning_threshold = 1  # Warn only if <= this many
```

---

## Progressive Implementation Plan

### Phase 1: Read-Only Analytics (Low Risk)

- Add `SMOCCredit` model
- Create management command to backfill from existing flights
- Add "SMOC Currency" display to member profile (info only, **no warnings**)
- Let members see their own currency status
- **Goal:** Validate the algorithm before using it for warnings

### Phase 2: Member Self-Service

- Add "Log External Flight" form
- Members can correct their own records
- Instructors can claim SMOC for flights they demoed
- **Goal:** Members tune their own data

### Phase 3: Duty Officer Warnings (After Validation)

- Only after Phase 1 & 2 have been running and validated
- Start with very conservative thresholds (warn at 0-1 only)
- Make warnings dismissible with "I verified this pilot"
- **Goal:** Useful warnings that don't cry wolf

---

## Open Questions for Discussion

### 1. Where should `SMOCCredit` live?

- **Option A:** `members` app (it's about member currency)
- **Option B:** `logsheet` app (it's derived from flights)
- **Option C:** New `currency` app (if we'll track other items like flight reviews)

### 2. Should instructors get auto-credit for anything?

Current proposal: Instructors get **0** auto-credit for dual flights (must manually claim).

Alternative: Give instructors credit for the **first** dual flight of each instruction session (assuming demo)?

### 3. How do we handle pattern tows?

5 pattern tows = 5 T/Os + 5 landings. Should we:
- Auto-detect based on short flight duration + same-day repeats?
- Let pilot specify "this was a pattern tow" (counts as 1 T/O + 1 landing)?
- Just count flights (1 flight = 1 T/O + 1 landing, regardless of patterns)?

### 4. What about flight reviews?

The biennial flight review is a separate currency requirement. Should we track that in the same system, or is that already handled elsewhere?

### 5. Tolerance for false positives vs. false negatives?

- **False positive:** System says member is current, but they're not → Safety risk
- **False negative:** System says member is NOT current, but they are → Annoying, erodes trust

Which error is more acceptable? Current proposal favors avoiding false negatives (crying wolf).

---

## Feedback Requested

Please comment on:

1. Does the auto-credit logic make sense for your typical flying patterns?
2. How often do instructors demo takeoffs/landings? Is "assume student is SMOC" a good default?
3. Would you use the "Log External Flight" feature?
4. What warning threshold feels right? Warn at 0? 1? 2?
5. Any edge cases we're missing?

---

*This document relates to [Issue #340](https://github.com/pietbarber/Manage2Soar/issues/340): Warning when unqualified members fly*
