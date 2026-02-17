# OR-Tools Production Constraint Model Design

**Date:** February 16, 2026  
**Phase:** 2 (Full Constraint Implementation)  
**Status:** Design Document

## Overview

This document defines the complete constraint programming model for migrating the duty roster scheduler from greedy/weighted-random to Google OR-Tools CP-SAT solver.

## Constraint Programming Fundamentals

### Decision Variables

**Primary Decision Variable: `x[member, role, day]`**
- Type: BoolVar (0 or 1)
- Meaning: `x[m, r, d] = 1` if member `m` is assigned to role `r` on day `d`, else 0

**Auxiliary Variables:**
- `total_assignments[member]`: IntVar counting total assignments for member (for balancing)
- `role_percentages[member, role]`: Constant representing preference percentage (for objective)

### Index Sets (from Django ORM)

- `M` = Set of eligible members (active members with at least one role flag)
- `R` = Set of roles to schedule (e.g., `['instructor', 'towpilot', 'duty_officer', 'assistant_duty_officer']`)
- `D` = Set of duty days (weekend dates within operational season, excluding user-removed dates)

## Hard Constraints (MUST be satisfied)

### 1. One Assignment Per Slot
**Description:** Each role on each day must have exactly one member assigned.

**CP-SAT Formulation:**
```python
for role in R:
    for day in D:
        model.Add(sum(x[m, role, day] for m in M) == 1)
```

**Rationale:** Every duty slot must be filled (100% slot fill rate requirement).

---

### 2. Role Qualification
**Description:** Members can only be assigned to roles they are qualified for.

**CP-SAT Formulation:**
```python
for m in M:
    for role in R:
        for day in D:
            if not getattr(member_obj[m], role):  # role flag is False
                model.Add(x[m, role, day] == 0)
```

**Django ORM Integration:**
- Check `Member.instructor`, `Member.towpilot`, `Member.duty_officer`, `Member.assistant_duty_officer` flags
- Pre-filter members per role to avoid creating unnecessary variables

---

### 3. Don't Schedule Flag
**Description:** Members with `dont_schedule=True` cannot be assigned.

**CP-SAT Formulation:**
```python
for m in M:
    pref = prefs.get(m)
    if pref and pref.dont_schedule:
        for role in R:
            for day in D:
                model.Add(x[m, role, day] == 0)
```

**Django ORM:** Query `DutyPreference.dont_schedule`

---

### 4. Scheduling Suspended Flag
**Description:** Members with `scheduling_suspended=True` cannot be assigned.

**CP-SAT Formulation:**
```python
for m in M:
    pref = prefs.get(m)
    if pref and pref.scheduling_suspended:
        for role in R:
            for day in D:
                model.Add(x[m, role, day] == 0)
```

**Django ORM:** Query `DutyPreference.scheduling_suspended`

---

### 5. Blackout Dates
**Description:** Members cannot be assigned on dates they have marked as unavailable.

**CP-SAT Formulation:**
```python
for (m, date) in blackouts:  # Set of (member_id, date) tuples
    if date in D:
        for role in R:
            model.Add(x[m, role, date] == 0)
```

**Django ORM:** Query `MemberBlackout.objects.filter(date__in=weekend_dates)`

---

### 6. Avoidance Constraints
**Description:** Pairs of members who avoid each other cannot be assigned on the same day.

**CP-SAT Formulation:**
```python
for (m1, m2) in avoidances:  # Set of (member_id, avoid_with_id) tuples
    for day in D:
        # At most one of m1 or m2 can be assigned on this day (any role)
        model.Add(
            sum(x[m1, role, day] for role in R) +
            sum(x[m2, role, day] for role in R) <= 1
        )
```

**Django ORM:** Query `DutyAvoidance.objects.all()`

**Note:** Avoidance is bidirectional; if (A, B) exists, treat (B, A) as implicit.

---

### 7. One Assignment Per Day
**Description:** Members can be assigned to at most one role per day.

**CP-SAT Formulation:**
```python
for m in M:
    for day in D:
        model.Add(sum(x[m, role, day] for role in R) <= 1)
```

**Rationale:** Prevents double-booking (member assigned as both instructor and towpilot on same day).

---

### 8. Anti-Repeat Constraint
**Description:** Members cannot do the same role on consecutive days.

**CP-SAT Formulation:**
```python
for m in M:
    for role in R:
        for i in range(len(D) - 1):
            day1 = D[i]
            day2 = D[i + 1]
            # Only apply if day2 immediately follows day1 (not separated by weekdays)
            if (day2 - day1).days == 1:  # Consecutive days
                model.Add(x[m, role, day1] + x[m, role, day2] <= 1)
```

**Rationale:** Prevents burnout; ensures fair distribution of back-to-back duties.

**Edge Case:** Saturday→Sunday are consecutive, but Sunday→(next)Saturday are not.

---

### 9. Role Percentage Zero
**Description:** Members with 0% preference for a role (when not overridden by single-role logic) cannot be assigned to that role.

**CP-SAT Formulation:**
```python
for m in M:
    pref = prefs.get(m)
    if not pref:
        continue  # No preference = treat as 100% for all roles

    # Determine eligible roles for member
    eligible_roles = [r for r in R if getattr(member_obj[m], r)]

    if len(eligible_roles) == 1:
        # Single role: treat 0% as 100% (override logic)
        continue

    # Multiple roles: check if all are zero
    all_zero = all(get_percent(pref, role) == 0 for role in eligible_roles)
    if all_zero:
        # All zero: treat all as 100% (override logic)
        continue

    # Not all zero: enforce 0% as hard constraint
    for role in eligible_roles:
        if get_percent(pref, role) == 0:
            for day in D:
                model.Add(x[m, role, day] == 0)
```

**Helper Function:**
```python
def get_percent(pref, role):
    field_map = {
        'instructor': 'instructor_percent',
        'towpilot': 'towpilot_percent',
        'duty_officer': 'duty_officer_percent',
        'assistant_duty_officer': 'ado_percent'
    }
    return getattr(pref, field_map[role], 0)
```

**Rationale:** Honors member's explicit opt-out of specific roles (when they have other options).

---

### 10. Max Assignments Per Month
**Description:** Members cannot exceed their maximum monthly assignment limit.

**CP-SAT Formulation:**
```python
DEFAULT_MAX = 8  # For members without DutyPreference

for m in M:
    pref = prefs.get(m)
    max_assignments = pref.max_assignments_per_month if pref else DEFAULT_MAX

    # Sum all assignments for member m across all roles and days
    model.Add(
        sum(x[m, role, day] for role in R for day in D) <= max_assignments
    )
```

**Django ORM:** Query `DutyPreference.max_assignments_per_month` (default: 0, but treated as 8 in current logic)

**Edge Case:** Current code uses `getattr(p, "max_assignments_per_month", 0)` which would disqualify if 0. Verify intent vs implementation.

---

### 11. Operational Season Filtering
**Description:** Only schedule on weekend dates within the club's operational season.

**CP-SAT Formulation:** (Implemented in preprocessing, not as constraint)
```python
# Date set D is pre-filtered by is_within_operational_season()
weekend_dates = [
    d for d in all_weekend_dates
    if is_within_operational_season(d)
]
```

**Django ORM:** Query `SiteConfiguration.operations_start_period` and `operations_end_period`

**Note:** This is a data filtering step, not a solver constraint.

---

## Soft Constraints (Optimize via Objective Function)

### 12. Role Preference Weighting
**Description:** Prefer assigning members to roles they prefer (higher percentage = higher weight).

**Objective Contribution:**
```python
objective_terms = []
for m in M:
    for role in R:
        for day in D:
            weight = calculate_weight(m, role)  # Based on preference percentage
            objective_terms.append(weight * x[m, role, day])

model.Maximize(sum(objective_terms))
```

**Weight Calculation:**
```python
def calculate_weight(member, role):
    pref = prefs.get(member.id)
    if not pref:
        return 100  # Default weight for members without preferences

    eligible_roles = [r for r in R if getattr(member, r)]

    if len(eligible_roles) == 1:
        # Single role: use percent, or 100 if 0
        percent = get_percent(pref, role)
        return 100 if percent == 0 else percent

    # Multiple roles: check if all are zero
    all_zero = all(get_percent(pref, r) == 0 for r in eligible_roles)
    if all_zero:
        return 100  # Treat all as 100

    # Return actual percent (0-100)
    return get_percent(pref, role)
```

**Rationale:** Maximizes member satisfaction by honoring preferences.

---

### 13. Pairing Affinity Bonus
**Description:** Members who prefer to work together should be scheduled on the same days (3x weight multiplier).

**Objective Contribution:**
```python
PAIRING_MULTIPLIER = 3

for day in D:
    for (m1, m2) in pairings:  # Set of (member_id, pair_with_id)
        # If both m1 and m2 are assigned on day (any roles), add bonus
        for role1 in R:
            for role2 in R:
                # Create auxiliary variable: both_assigned[m1, m2, day]
                both_assigned = model.NewBoolVar(f'both_{m1}_{m2}_{day}')

                # both_assigned = 1 iff (m1 assigned AND m2 assigned on day)
                model.AddMultiplicationEquality(
                    both_assigned,
                    [x[m1, role1, day], x[m2, role2, day]]
                )

                # Add bonus to objective
                base_weight = (calculate_weight(m1, role1) + calculate_weight(m2, role2)) / 2
                bonus = base_weight * (PAIRING_MULTIPLIER - 1) * both_assigned
                objective_terms.append(bonus)
```

**Alternative (Simpler):** Count co-occurrence and add to objective directly:
```python
for day in D:
    for (m1, m2) in pairings:
        # Indicator: at least one of m1 and at least one of m2 assigned on day
        m1_assigned = sum(x[m1, role, day] for role in R)
        m2_assigned = sum(x[m2, role, day] for role in R)

        # Approximate: reward if both > 0 (requires indicator constraint)
        both = model.NewBoolVar(f'paired_{m1}_{m2}_{day}')
        model.AddMinEquality(both, [m1_assigned, m2_assigned])  # both = 1 if both >= 1

        objective_terms.append(PAIRING_BONUS * both)
```

**Django ORM:** Query `DutyPairing.objects.all()`

**Complexity Note:** This is the most complex soft constraint; may need simplification for performance.

---

### 14. Last Duty Date Balancing
**Description:** Prefer assigning members who haven't worked recently (fairness over time).

**Objective Contribution:**
```python
# Assign staleness score based on last_duty_date
for m in M:
    pref = prefs.get(m.id)
    last_duty = pref.last_duty_date if pref else date(1900, 1, 1)
    days_since = (earliest_duty_day - last_duty).days

    # Higher staleness = higher priority
    staleness_weight = days_since  # Linear scaling

    for role in R:
        for day in D:
            objective_terms.append(staleness_weight * x[m, role, day])
```

**Rationale:** Ensures fair distribution over multiple months, not just within-month balance.

**Django ORM:** Query `DutyPreference.last_duty_date`

---

### 15. Balanced Assignment Distribution
**Description:** Minimize variance in total assignments across members (fairness within month).

**Objective Contribution (Alternative Formulation):**
```python
# Calculate average assignments per member
total_slots = len(D) * len(R)
avg_assignments = total_slots / len(M)

# Minimize deviation from average
for m in M:
    total_m = sum(x[m, role, day] for role in R for day in D)
    deviation = model.NewIntVar(-total_slots, total_slots, f'dev_{m}')
    model.Add(deviation == total_m - int(avg_assignments))

    # Minimize absolute deviation (requires auxiliary variable)
    abs_dev = model.NewIntVar(0, total_slots, f'abs_dev_{m}')
    model.AddAbsEquality(abs_dev, deviation)

    objective_terms.append(-abs_dev)  # Negative because we minimize deviation
```

**Note:** This competes with preference weighting; may need tuning or removal if infeasible.

---

## Role Scarcity Prioritization

**Description:** Schedule most constrained roles first to avoid infeasibility.

**CP-SAT Implementation:** Not a constraint; instead, order constraint addition by scarcity.

**Approach:**
1. Calculate scarcity score for each role (as in current scheduler)
2. Add hard constraints for most scarce roles first
3. Solver will attempt to satisfy in order of addition (heuristic guidance)

**Code:**
```python
def add_constraints_by_priority(model, roles, scarcity_scores):
    prioritized_roles = sorted(roles, key=lambda r: scarcity_scores[r])

    for role in prioritized_roles:
        # Add "one assignment per slot" constraint for this role
        for day in D:
            model.Add(sum(x[m, role, day] for m in M) == 1)
```

**Note:** CP-SAT doesn't strictly honor constraint order, but can inform branching heuristics.

---

## Decision Variable Creation Strategy

### Sparse Variable Creation
**Problem:** Creating `x[m, r, d]` for all combinations is wasteful if many are always 0.

**Solution:** Only create variables for valid (member, role, day) tuples.

**Implementation:**
```python
# Pre-compute valid tuples
valid_tuples = set()
for m in members:
    for role in roles:
        # Check if member is qualified for this role
        if not getattr(m, role):
            continue  # Skip unqualified members

        # Check if member is globally blocked
        pref = prefs.get(m.id)
        if pref and (pref.dont_schedule or pref.scheduling_suspended):
            continue  # Skip blocked members

        for day in duty_days:
            # Check if member is blacked out on this day
            if (m.id, day) in blackouts:
                continue  # Skip blacked-out days

            # Tuple is valid
            valid_tuples.add((m.id, role, day))

# Create variables only for valid tuples
x = {}
for (m_id, role, day) in valid_tuples:
    x[m_id, role, day] = model.NewBoolVar(f'x_{m_id}_{role}_{day}')
```

**Benefit:** Reduces variable count by ~60-80% (eliminates infeasible assignments upfront).

---

## Django ORM Integration Plan

### Data Extraction
```python
def extract_scheduling_data(year, month, roles, exclude_dates=None):
    """
    Extract all necessary data from Django ORM for OR-Tools solver.

    Returns dict with:
        - members: List of Member objects (active, with at least one role)
        - duty_days: List of date objects (weekends in operational season)
        - preferences: Dict of member_id -> DutyPreference
        - blackouts: Set of (member_id, date) tuples
        - avoidances: Set of (member_id, avoid_with_id) tuples
        - pairings: Set of (member_id, pair_with_id) tuples
        - role_scarcity: Dict of role -> scarcity score
    """
    # Implementation here...
    pass
```

### Result Application
```python
def apply_schedule_to_django(schedule_result, year, month):
    """
    Convert OR-Tools solver output to DutyAssignment objects.

    Args:
        schedule_result: List of dicts with {'date': ..., 'slots': {role: member_id}}
        year, month: Schedule period

    Returns:
        List of created DutyAssignment objects
    """
    assignments = []
    for day_schedule in schedule_result:
        date = day_schedule['date']
        for role, member_id in day_schedule['slots'].items():
            if member_id:  # Slot was filled
                assignment = DutyAssignment(
                    member_id=member_id,
                    role=role,
                    date=date,
                    # ... other fields
                )
                assignments.append(assignment)

    # Bulk create for performance
    DutyAssignment.objects.bulk_create(assignments)
    return assignments
```

---

## Performance Optimization

### Expected Complexity
- **Variables:** ~500-1000 (30 members × 4 roles × 8 days, with sparse filtering)
- **Constraints:** ~200-400 (hard constraints + auxiliary for soft constraints)
- **Solve Time Target:** < 1 second for typical month (validated in Phase 1: <15ms for simplified problem)

### Tuning Parameters
```python
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0  # Timeout at 10 seconds
solver.parameters.num_search_workers = 4       # Parallelize search
solver.parameters.log_search_progress = True   # Debug logging
```

### Fallback Strategy
If solver fails or times out:
1. Log error with diagnostic info (which constraints are conflicting)
2. Fall back to legacy greedy algorithm
3. Flag schedule as "suboptimal" in UI

---

## Testing Strategy

### Unit Tests (Per Constraint)
- Test each hard constraint in isolation
- Verify constraint logic with synthetic data
- Check edge cases (e.g., all members blacked out, single eligible member)

### Integration Tests
- Compare OR-Tools output to legacy algorithm output on same inputs
- Validate slot fill rate (must be 100% or explain why not)
- Check fairness metrics (variance in assignment counts)

### Regression Tests
- Use historical roster data (past 6-12 months)
- Verify OR-Tools produces acceptable rosters for known-good inputs

### Performance Tests
- Benchmark solve times for varying problem sizes:
  - Small: 10 members, 4 roles, 4 days
  - Medium: 20 members, 4 roles, 8 days
  - Large: 40 members, 4 roles, 12 days
- Ensure all cases solve in < 1 second

---

## Next Steps

1. ✅ Analyze current scheduler constraints (Task 1)
2. 🔄 Design production constraint model (Task 2 - this document)
3. ⏭️ Implement `ortools_scheduler.py` skeleton (Task 3)
4. ⏭️ Implement hard constraints (Tasks 4-7)
5. ⏭️ Build test suite (Task 8)
6. ⏭️ Performance benchmark (Task 9)

---

**Document Status:** Complete, ready for implementation (Task 3)
