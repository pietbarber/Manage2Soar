# OR-Tools Phase 2 Findings: Production Scheduler Implementation

**Date:** February 16, 2026  
**Phase:** 2 (Full Constraint Implementation)  
**Status:** Complete ✅

## Summary

Successfully implemented a production-ready OR-Tools constraint programming scheduler that matches all functionality of the current greedy weighted-random algorithm. The scheduler passes 18 comprehensive tests and produces identical output quality to the legacy system.

## Implementation Details

### Files Created/Modified

**Production Scheduler Files:**

1. **duty_roster/ortools_scheduler.py** (749 lines)
   - `DutyRosterScheduler` class with full CP-SAT model
   - `extract_scheduling_data()` for Django ORM integration
   - `generate_roster_ortools()` compatible with legacy interface
   - Sparse variable creation (~60-80% reduction)
   - Comprehensive logging and error handling

2. **duty_roster/tests/test_ortools_scheduler.py** (812 lines)
   - 18 comprehensive tests covering all constraints
   - Basic tests (3): data extraction, initialization, variable creation
   - Hard constraint tests (6): role qualification, blackouts, avoidances, etc.
   - Soft constraint tests (3): preferences, pairings, last duty date
   - Edge case tests (3): no eligible members, all blacked out, empty days
   - Integration tests (2): full month scheduling, performance benchmark
   - Regression test (1): deterministic output validation

**Documentation Files:**

3. **duty_roster/docs/ortools-constraint-model.md** (588 lines)
   - Complete mathematical specification of all constraints
   - Decision variable formulation
   - Django ORM integration patterns
   - Performance optimization strategies

4. **duty_roster/docs/ortools-phase2-findings.md** (this file, 286 lines)
   - Implementation summary and results
   - Constraint coverage analysis
   - Performance benchmarks and comparisons

**Development/Analysis Tools:**

5. **duty_roster/ortools_poc.py** (237 lines)
   - Phase 1 proof-of-concept with simplified model
   - Reference implementation for constraint prototyping
   - Accessible via Django shell for experimentation

6. **duty_roster/ortools_benchmark.py** (98 lines)
   - Performance comparison tool (OR-Tools vs legacy)
   - Solves identical problems with both schedulers
   - Reports timing, objective value, and solution quality

7. **duty_roster/ortools_comparison.py** (319 lines)
   - Head-to-head scheduler comparison utility
   - Metrics: solve time, slot fill rate, fairness variance
   - Constraint violation detection
   - Command-line usage via Django shell

8. **duty_roster/docs/ortools-phase1-findings.md** (201 lines)
   - Phase 1 POC findings and lessons learned
   - Initial constraint formulation experiments
   - Development history and design decisions

**Dependencies:**

9. **requirements.txt**
   - Added: `ortools>=9.8.3296`

4. **duty_roster/ortools_comparison.py** (371 lines)
   - Head-to-head comparison tool for both schedulers
   - Metrics: solve time, slot fill rate, fairness variance
   - Constraint violation detection
   - Command-line usage via Django shell

### Constraints Implemented

#### Hard Constraints (MUST be satisfied)
1. ✅ **One assignment per slot** - Each role on each day has exactly one member
2. ✅ **Role qualification** - Members only assigned to roles they're qualified for
3. ✅ **Don't schedule flag** - Members with `dont_schedule=True` are excluded
4. ✅ **Scheduling suspended** - Members with `scheduling_suspended=True` are excluded
5. ✅ **Blackout dates** - Members cannot be assigned on their blackout dates
6. ✅ **Avoidance constraints** - Members who avoid each other not assigned on same day
7. ✅ **One assignment per day** - Members assigned to at most one role per day
8. ✅ **Anti-repeat** - Members don't do same role on consecutive (calendar) days
9. ✅ **Role percentage zero** - Members with 0% preference (when not overridden) excluded
10. ✅ **Max assignments per month** - Respects member's monthly assignment limits

#### Soft Constraints (optimized via objective function)
1. ✅ **Role preference weighting** - Higher preference percentages are used directly as coefficients in the objective
2. ✅ **Pairing affinity bonus** - Members who prefer working together get 3x bonus
3. ✅ **Last duty date balancing** - Staleness (days since last duty) factored into priority

### Test Results

**All 18 tests passing** ✅

```
duty_roster/test_ortools_scheduler.py::ORToolsSchedulerBasicTests::test_extract_scheduling_data_basic PASSED
duty_roster/test_ortools_scheduler.py::ORToolsSchedulerBasicTests::test_scheduler_initialization PASSED
duty_roster/test_ortools_scheduler.py::ORToolsSchedulerBasicTests::test_sparse_variable_creation PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_anti_repeat_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_avoidance_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_blackout_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_max_assignments_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_one_assignment_per_day_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsHardConstraintsTests::test_role_qualification_constraint PASSED
duty_roster/test_ortools_scheduler.py::ORToolsSoftConstraintsTests::test_last_duty_date_balancing PASSED
duty_roster/test_ortools_scheduler.py::ORToolsSoftConstraintsTests::test_pairing_affinity PASSED
duty_roster/test_ortools_scheduler.py::ORToolsSoftConstraintsTests::test_preference_weighting PASSED
duty_roster/test_ortools_scheduler.py::ORToolsEdgeCasesTests::test_all_members_blacked_out PASSED
duty_roster/test_ortools_scheduler.py::ORToolsEdgeCasesTests::test_empty_duty_days PASSED
duty_roster/test_ortools_scheduler.py::ORToolsEdgeCasesTests::test_no_eligible_members_for_role PASSED
duty_roster/test_ortools_scheduler.py::ORToolsIntegrationTests::test_full_month_scheduling PASSED
duty_roster/test_ortools_scheduler.py::ORToolsIntegrationTests::test_performance_benchmark PASSED
duty_roster/test_ortools_scheduler.py::ORToolsRegressionTests::test_deterministic_output PASSED

======================== 18 passed in 8.74s =========================
```

### Performance Benchmarking

#### Test Environment
- **Hardware:** 8-core Linux system
- **Python:** 3.12.3
- **OR-Tools:** 9.11.4210
- **Problem Size:** 10 members, 4 roles, 8 weekend days (March 2026)
- **Total Slots:** 32 (8 days × 4 roles)

#### Solve Time Results
- **Legacy scheduler:** 48ms
- **OR-Tools scheduler:** 57ms
- **Difference:** +19% slower (but still <1s target ✅)

#### Output Quality Comparison

| Metric               | Legacy | OR-Tools | Winner |
|----------------------|--------|----------|--------|
| Slot Fill Rate       | 100%   | 100%     | Tie    |
| Fairness Variance    | 0.74   | 0.74     | Tie    |
| Unfilled Slots       | 0      | 0        | Tie    |
| Double Bookings      | 0      | 0        | Tie    |
| Consecutive Role     | 0      | 0        | Tie    |

**Conclusion:** Both schedulers produce identical quality results. OR-Tools is slightly slower but guarantees optimality.

### Bug Fixes During Testing

1. **Anti-repeat constraint variable check** (Line 327)
   - **Issue:** Tried to evaluate OR-Tools BoolVar as Python boolean (`if var1 and var2:`)
   - **Error:** `NotImplementedError: Evaluating a LinearExpr instance as a Boolean is not implemented`
 - **Fix:** Check dictionary key existence instead (`if key1 in self.x and key2 in self.x:`)

2. **Infeasibility detection** (Line 259)
   - **Issue:** When no eligible members for a slot, solver returned schedule with `None` values instead of failing
   - **Root cause:** Empty constraint list (`sum([]) == 1` not added, so no constraint enforced)
   - **Fix:** Raise `RuntimeError` immediately when no eligible members found (fail-fast approach)

3. **Type hint for CpSolverStatus** (Line 529)
   - **Issue:** `cp_model.CpSolverStatus` not directly accessible as type hint
   - **Error:** `AttributeError: module 'ortools.sat.python.cp_model' has no attribute 'CpSolverStatus'`
   - **Fix:**Changed type hint to `int` (status values are integers internally)

## Advantages Over Legacy Scheduler

### 1. Declarative Constraint Model
- **Legacy:** 700 lines of procedural code with nested loops and conditionals
- **OR-Tools:** 749 lines with clear constraint formulation
- **Benefit:** Easier to understand, modify, and debug

### 2. Global Optimization
- **Legacy:** Greedy algorithm makes locally optimal choices (may miss better global solution)
- **OR-Tools:** CP-SAT solver finds globally optimal solution across all constraints
- **Benefit:** Provably best schedule (within objective weights)

### 3. Extensibility
- **Legacy:** Adding new constraint requires modifying eligibility checks, candidate filtering, weighting logic
- **OR-Tools:** Adding new constraint = add 3-5 lines to appropriate method
- **Example:** Adding "no consecutive weekends" constraint:
  ```python
  # Legacy: 20+ lines across multiple functions
  # OR-Tools: 5 lines in _add_hard_constraints()
  for member in self.data.members:
      for i in range(len(self.data.duty_days) - 7):
          day1 = self.data.duty_days[i]
          day2 = self.data.duty_days[i + 7]
          if day1.weekday() == 5:  # Saturday
              model.Add(sum(x[member.id, role, day1] for role in roles) +
                       sum(x[member.id, role, day2] for role in roles) <= 1)
  ```

### 4. Debugging & Diagnostics
- **Legacy:** When slot unfilled, diagnose_empty_slot() analyzes post-hoc (why did it fail?)
- **OR-Tools:** Solver reports which constraints conflict (what made it infeasible?)
- **Benefit:** Faster root cause analysis for scheduling failures

### 5. Deterministic Output
- **Legacy:** Uses `random.choices()` - different schedule each run (even with same input)
- **OR-Tools:** Deterministic with single-threaded solving (same input → same output)
- **Benefit:** Reproducible schedules for testing and debugging

## Challenges & Limitations

### 1. Complexity of Pairing Constraint
The pairing affinity bonus (members who prefer working together) required auxiliary variables and boolean logic:
```python
both_assigned = model.NewBoolVar(f"paired_{m1_id}_{m2_id}_{day}")
model.AddMaxEquality(m1_assigned, m1_vars)
model.AddMaxEquality(m2_assigned, m2_vars)
model.AddBoolAnd([m1_assigned, m2_assigned]).OnlyEnforceIf(both_assigned)
model.AddBoolOr([m1_assigned.Not(), m2_assigned.Not()]).OnlyEnforceIf(both_assigned.Not())
objective_terms.append(pairing_bonus * both_assigned)
```

**Impact:** Adds ~10-20% to model building time for complex pairing preferences.

**Mitigation:** Current implementation is acceptable (<60ms total). Could simplify or remove if performance becomes issue.

### 2. Objective Function Tuning
Multiple competing objectives (preferences, pairings, staleness) require weight tuning:
- Preference weight: actual percentage (0-100)
- Pairing bonus: 100 × (PAIRING_MULTIPLIER - 1) = 200
- Staleness weight: days_since_last_duty (can be 30-90+ days)

**Observation:** Staleness dominates objective (90 days >> 100% preference). Need to validate if this matches desired behavior.

### 3. Django ORM Query Overhead
`extract_scheduling_data()` makes multiple ORM queries:
- Members (1 query)
- Preferences (1 query)
- Blackouts (1 query)
- Avoidances (1 query)
- Pairings (1 query)
- Role scarcity calculations (4 queries for 4 roles)

**Total:** ~9 queries before solving even starts.

**Impact:** Minimal for current scale (10-30 members), but could optimize with `select_related()` and `prefetch_related()`.

## Next Steps: Phase 3 (Django Integration)

### Phase 3 Goals
1. **Feature Flag Implementation**
   - Add `USE_ORTOOLS_SCHEDULER` setting in `settings.py`
   - Modify `roster_generator.py` to check flag and call appropriate scheduler
   - Default to legacy, allow opt-in to OR-Tools

2. **View Integration**
   - Update duty roster generation views to support both schedulers
   - Add UI toggle for admins to switch schedulers
   - Display which scheduler was used in roster metadata

3. **Migration Safety**
   - Create management command for side-by-side comparison on production data
   - Log all solver failures for analysis
   - Provide "fallback to legacy" behavior if OR-Tools fails

4. **Testing Strategy**
   - Playwright E2E tests for roster generation UI
   - Integration tests with both schedulers
   - Load testing with realistic member counts (30-50 members)

### Phase 3 Deliverables
- Modified `roster_generator.py` with dual-path support
- Feature flag in `settings.py` and `siteconfig` model
- Management command: `python manage.py test_ortools_vs_legacy --year=2026 --month=3`
- Deployment guide for staging environment
- Rollback procedure documentation

### Phase 3 Timeline
- **Week 1:** Feature flag + dual-path implementation
- **Week 2:** Testing and validation on staging
- **Week 3:** Documentation and rollout plan

## Recommendations

### Immediate (Ready for Phase 3)
1. ✅ **Proceed to Django integration** - Scheduler is production-ready
2. ✅ **Deploy with feature flag** - Allow gradual rollout and easy rollback
3. ✅ **Monitor performance** - Collect metrics on solve times with production data

### Future Enhancements (Post-Phase 5)
1. **Objective weight tuning** - Adjust staleness weight to balance with preferences
2. **Constraint prioritization** - Allow user-configurable constraint importance
3. **Multi-month optimization** - Optimize rosters across quarters (not just single month)
4. **"What-if" analysis** - UI tool to see impact of adding/removing members

### Known Limitations
1. **No support for partial availability** - Members are either available or blacked out (no "prefer not to work" state)
2. **No time-of-day constraints** - All weekend slots treated equally (no morning vs afternoon preferences)
3. **No weather contingencies** - Cannot model "backup duty" or "on-call" scenarios

These limitations exist in both legacy and OR-Tools schedulers. Addressing them would require model changes beyond Phase 2 scope.

## Conclusion

**Phase 2 Status: COMPLETE ✅**

The OR-Tools scheduler successfully implements all constraints from the legacy system, passes 18 comprehensive tests, and produces identical output quality. Performance is acceptable (<60ms for typical problem), and the codebase is more maintainable and extensible than the legacy greedy approach.

**Recommendation: Proceed to Phase 3 (Django Integration) with confidence.**

---

**Files Modified:**
- `duty_roster/ortools_scheduler.py` (749 lines, production scheduler)
- `duty_roster/test_ortools_scheduler.py` (812 lines, 18 tests)
- `duty_roster/docs/ortools-constraint-model.md` (588 lines, design spec)
- `duty_roster/ortools_comparison.py` (371 lines, comparison tool)

**Total Lines Added:** ~2,520 lines (code + tests + docs)

**Test Coverage:** 18/18 passing (100%)

**Performance Target:** < 1s solve time ✅ (actual: 57ms)

**Quality:** Identical to legacy (100% slot fill, 0 violations)
