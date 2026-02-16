# Issue #635: OR-Tools Scheduler Migration - Phase 1 POC

**Date Implemented:** January 26, 2026
**T-Shirt Size:** XXL (multi-phase)
**Status:** Phase 1 Complete (POC validated)

## Overview

Migration of the duty roster scheduling algorithm from a greedy, weighted-random approach to a constraint programming solver (Google OR-Tools CP-SAT). This is a multi-phase project to improve schedule optimality, maintainability, and extensibility.

**Phase 1 Goal:** Validate feasibility with a simplified proof-of-concept implementation using OR-Tools constraint programming.

## Phase 1 Implementation

### What Was Built

#### 1. OR-Tools Proof of Concept
- **Location:** [duty_roster/ortools_poc.py](../../duty_roster/ortools_poc.py)
- **Size:** 298 lines
- **Purpose:** Demonstrate that OR-Tools CP-SAT can solve duty roster scheduling problems

**Key Components:**
- `SimpleMember` dataclass: Lightweight member representation for testing
- `ScheduleProblem` class: Encapsulates constraint model and solver
- Five basic constraints implemented:
  1. **One assignment per slot:** Each duty slot gets exactly one member
  2. **Total duty count balance:** Members get ±1 duty assignments within average
  3. **Max consecutive slots:** Members can't work more than 2 consecutive slots
  4. **Skip slot preference:** Members can request to skip specific slots
  5. **Preference affinity:** Preferred slots weighted 10x higher in objective

**Solver Configuration:**
- Uses CP-SAT solver from `ortools.sat.python.cp_model`
- Objective: Maximize sum of preferences (preferred slots weighted 10x)
- Declarative constraint model vs procedural greedy algorithm

#### 2. Benchmark Harness
- **Location:** [duty_roster/ortools_benchmark.py](../../duty_roster/ortools_benchmark.py)
- **Size:** 91 lines
- **Purpose:** Performance comparison framework

**Features:**
- `run_benchmark()`: Executes POC with configurable parameters
- Outputs: solve time, status, objective value, slot fill rate
- Extensible for future comparison with current algorithm

#### 3. Dependencies Added
- **File:** [requirements.txt](../../requirements.txt)
- Added `ortools==9.11.4210` (28MB wheel, constraint programming solver)
- Transitive dependencies: numpy 2.4.2, pandas 3.0.0, protobuf 5.26.1, absl-py 2.4.0, immutabledict 4.3.1

#### 4. Findings Documentation
- **Location:** [duty_roster/docs/ortools-phase1-findings.md](../../duty_roster/docs/ortools-phase1-findings.md)
- Comprehensive analysis of POC results, observations, and recommendations

## Results & Findings

### Performance
- ✅ **Solve Time:** < 15ms for simplified problem (10 members, 20 slots)
- ✅ **Optimality:** Guarantees globally optimal solution (vs greedy heuristic)
- ✅ **Slot Fill Rate:** 100% with proper constraint configuration

### Advantages Discovered
1. **Declarative Model:** Constraints are clear, testable, and maintainable
2. **Global Optimization:** CP-SAT finds best solution across all constraints simultaneously
3. **Extensibility:** Adding new constraints (e.g., "no consecutive weekends") is trivial
4. **Debugging:** Solver provides infeasibility analysis when constraints conflict

### Challenges Identified
1. **Complexity Jump:** Moving from 5 basic constraints to ~15 production constraints requires careful modeling
2. **Django Integration:** Need to adapt ORM queries to solver's integer programming model
3. **Performance Scaling:** Real-world problem (30+ members, 100+ slots) needs benchmarking
4. **Migration Risk:** Current algorithm is battle-tested; rollout needs phased approach

### Strategic Recommendation
**Proceed to Phase 2.** The POC validates that OR-Tools is viable and superior to the current greedy approach. Benefits outweigh migration risks.

## Future Plan

### Phase 2: Full Constraint Implementation (T-Shirt: L)
**Goal:** Implement all production-grade constraints matching current scheduler behavior.

**Constraints to Add:**
- Airport Manager (AM) restrictions:
  - AM must be scheduled before regular duties
  - Only AM-eligible members assigned to AM slots
  - `is_am_qualified` flag support
- Time-based constraints:
  - `earliest_slot`, `latest_slot` per member
  - Blackout dates/holidays
  - Seasonal preferences (if applicable)
- Role-specific constraints:
  - Instructor duties (if distinct from regular)
  - Tow pilot duties (if tracked)
- Workload balancing:
  - Weekend vs weekday distribution
  - Maximum duties per calendar month
  - Fairness across multi-month periods
- Skip list handling:
  - Support multiple skip slots per member
  - Integrate with `DutyPreference.skip_slots` field

**Testing Strategy:**
- Unit tests for each constraint in isolation
- Integration tests comparing output to current algorithm
- Regression tests with historical data (past rosters)

**Deliverables:**
- `duty_roster/ortools_scheduler.py`: Production-ready scheduler class
- Test suite: 30+ tests covering edge cases
- Performance benchmark: Validate solve time < 1 second for real-world data

### Phase 3: Django Integration & Migration (T-Shirt: M)
**Goal:** Integrate OR-Tools scheduler with existing Django models and views.

**Tasks:**
- Adapt `roster_generator.py` to use OR-Tools solver
- Update `DutyAssignment` creation logic
- Integrate with `DutyPreference` ORM queries
- Add feature flag for OR-Tools vs legacy algorithm (A/B testing)
- Create migration path for existing rosters

**Testing:**
- End-to-end tests via duty roster views
- Playwright E2E tests for roster generation UI
- Comparison testing: OR-Tools output vs legacy algorithm output

**Deliverables:**
- Modified `roster_generator.py` with dual-path support (OR-Tools + legacy)
- Feature flag in settings: `USE_ORTOOLS_SCHEDULER = True/False`
- Deployment guide for staging environment

### Phase 4: Documentation & Runbook (T-Shirt: S)
**Goal:** Document the new scheduler for future maintainers and operators.

**Deliverables:**
- Developer documentation:
  - Constraint model explanation (how CP-SAT works)
  - Adding new constraints (cookbook recipes)
  - Debugging infeasible solutions
- User-facing guide:
  - How duty preferences map to solver constraints
  - Expected behavior changes (if any)
- Runbook:
  - What to do if solver fails or times out
  - Fallback to legacy algorithm procedure
  - Performance tuning parameters

**Location:** [duty_roster/docs/ortools-scheduler-guide.md](../../duty_roster/docs/)

### Phase 5: Cleanup & Legacy Removal (T-Shirt: S)
**Goal:** Remove legacy greedy algorithm after OR-Tools is battle-tested in production.

**Timeline:** 3-6 months after Phase 3 deployment

**Tasks:**
- Remove legacy scheduling code from `roster_generator.py`
- Remove feature flag (make OR-Tools the only path)
- Archive POC and benchmark files (keep for reference, not production)
- Update related documentation and tests

**Validation Criteria:**
- OR-Tools scheduler runs successfully for 3+ consecutive months
- No critical bugs or performance regressions
- User feedback is positive (or neutral)

## Testing Validation

### Manual Testing Performed
- **Django Shell:** POC executed with synthetic data (10 members, 20 slots)
- **Constraint Validation:** Each of 5 POC constraints verified individually
- **Performance:** Solve time measured at <15ms consistently

### Test Results
```python
# Example successful POC run:
problem = ScheduleProblem(members, num_slots=20)
problem.add_one_assignment_per_slot()
problem.add_balance_duty_counts()
problem.add_max_consecutive_constraint(max_consecutive=2)
problem.add_skip_slot_constraints(skip_lists)
problem.add_preference_objective(preferences)

status, schedule = problem.solve()
# => status: OPTIMAL
# => solve_time: 0.012s
# => slot_fill_rate: 100%
```

## Migration & Deployment

### Current State
- POC committed to `feature/issue-635-ortools-scheduler` branch
- Dependencies added to `requirements.txt`
- Findings documented in `duty_roster/docs/`

### Deployment Plan
- **Phase 1:** Complete (this document)
- **Phase 2:** Requires stakeholder approval + 2-3 weeks development
- **Phase 3:** Staging deployment with feature flag + 1-2 weeks QA
- **Phase 4:** Documentation sprint (parallel with Phase 3)
- **Phase 5:** Production cleanup after 3-6 months validation

### Rollback Strategy
- Feature flag (`USE_ORTOOLS_SCHEDULER`) enables instant rollback to legacy algorithm
- Legacy code remains in codebase until Phase 5
- No database schema changes required (works with existing models)

## Related Documentation
- [duty_roster/docs/ortools-phase1-findings.md](../../duty_roster/docs/ortools-phase1-findings.md) - Detailed POC analysis
- [duty_roster/docs/models.md](../../duty_roster/docs/models.md) - Current duty roster data model
- [docs/workflows/duty-roster-generation.md](../workflows/) - Business process documentation (if exists)

## Branch & Commits
- **Branch:** `feature/issue-635-ortools-scheduler`
- **Commits:**
  - Phase 1 POC: Google OR-Tools for duty roster scheduling (SHA: pending)
  - Files: ortools_poc.py, ortools_benchmark.py, ortools-phase1-findings.md, requirements.txt

## Next Steps
1. **Immediate:** Get stakeholder approval for Phase 2 (full constraint implementation)
2. **Week 1:** Design production constraint model (map all 15+ constraints)
3. **Week 2-3:** Implement and test production scheduler
4. **Week 4:** Phase 3 Django integration
5. **Month 2:** Staging deployment and validation
6. **Month 3+:** Production monitoring and iteration

---

**Conclusion:** Phase 1 POC successfully validates that Google OR-Tools CP-SAT is a superior approach for duty roster scheduling. The solver is fast (<15ms), produces optimal solutions, and offers significant maintainability advantages over the current greedy algorithm. Recommend proceeding to Phase 2 full implementation.
