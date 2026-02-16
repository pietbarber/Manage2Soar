"""Proof of Concept: Google OR-Tools for Duty Roster Scheduling

This POC demonstrates using Google OR-Tools CP-SAT solver for duty roster
generation instead of the current greedy algorithm. It tests basic constraint
formulation and solution quality with a simplified scheduling problem.

Phase 1 Goals:
- Verify OR-Tools can handle the scheduling problem
- Test constraint formulation patterns
- Benchmark performance vs current algorithm
- Identify potential challenges

Usage:
    python manage.py shell
    >>> from duty_roster.ortools_poc import run_poc
    >>> run_poc()
"""

import time
from datetime import date, timedelta
from typing import Dict, List, Set, Tuple

from ortools.sat.python import cp_model


class SimpleMember:
    """Simplified member model for POC."""

    def __init__(self, id: int, name: str, roles: List[str], max_assignments: int = 8):
        self.id = id
        self.name = name
        self.roles = set(roles)  # Set of role names this member can perform
        self.max_assignments = max_assignments
        self.preference_pct = 100  # Default 100% willingness


class ScheduleProblem:
    """Defines a duty roster scheduling problem for OR-Tools."""

    def __init__(
        self,
        members: List[SimpleMember],
        dates: List[date],
        roles: List[str],
        blackouts: Set[Tuple[int, date]],
    ):
        self.members = members
        self.dates = dates
        self.roles = roles
        self.blackouts = blackouts  # Set of (member_id, date) tuples

        # Create solver model
        self.model = cp_model.CpModel()

        # Decision variables: assignment[m, r, d] = 1 if member m assigned to role r on date d
        self.assignments = {}
        for m in members:
            for r in roles:
                for d in dates:
                    var_name = f"assign_m{m.id}_r{r}_d{d.isoformat()}"
                    self.assignments[(m.id, r, d)] = self.model.NewBoolVar(var_name)

    def add_constraints(self):
        """Add all constraints to the model."""

        # CONSTRAINT 1: Exactly one member per role per date
        # (or zero if no one is eligible - we'll handle this with soft constraint)
        for r in self.roles:
            for d in self.dates:
                eligible_vars = [
                    self.assignments[(m.id, r, d)]
                    for m in self.members
                    if r in m.roles and (m.id, d) not in self.blackouts
                ]
                if eligible_vars:
                    # Exactly 1 member assigned to this role on this date
                    self.model.Add(sum(eligible_vars) == 1)

        # CONSTRAINT 2: Role eligibility (member can only be assigned to roles they have)
        for m in self.members:
            for r in self.roles:
                if r not in m.roles:
                    # Member doesn't have this role - force all assignments to 0
                    for d in self.dates:
                        self.model.Add(self.assignments[(m.id, r, d)] == 0)

        # CONSTRAINT 3: Blackout dates (member cannot be assigned when blacked out)
        for m_id, d in self.blackouts:
            for r in self.roles:
                # Force assignment to 0 for blacked out (member, date) pairs
                self.model.Add(self.assignments[(m_id, r, d)] == 0)

        # CONSTRAINT 4: One role per member per day (no double-booking)
        for m in self.members:
            for d in self.dates:
                # Sum of all role assignments for this member on this date <= 1
                day_assignments = [self.assignments[(m.id, r, d)] for r in self.roles]
                self.model.Add(sum(day_assignments) <= 1)

        # CONSTRAINT 5: Max assignments per member (monthly limit)
        for m in self.members:
            total_assignments = [
                self.assignments[(m.id, r, d)] for r in self.roles for d in self.dates
            ]
            self.model.Add(sum(total_assignments) <= m.max_assignments)

    def set_objective(self):
        """Define objective function to maximize schedule quality."""

        objective_terms = []

        # Goal 1: Maximize total assignments (prefer filling all slots)
        for m in self.members:
            for r in self.roles:
                for d in self.dates:
                    # Weight by member's preference percentage (0-100)
                    weight = m.preference_pct
                    objective_terms.append(self.assignments[(m.id, r, d)] * weight)

        # Goal 2: Balance assignments evenly across members
        # (Penalty for deviation from average) - Not implemented in POC for simplicity
        # Would add variance minimization terms here

        # Maximize the weighted sum
        self.model.Maximize(sum(objective_terms))

    def solve(self, time_limit_seconds: int = 10) -> Tuple[str, Dict]:
        """Solve the scheduling problem.

        Args:
            time_limit_seconds: Maximum time to spend solving

        Returns:
            Tuple of (status_string, solution_dict)
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.log_search_progress = False

        start_time = time.time()
        status = solver.Solve(self.model)
        solve_time = time.time() - start_time

        status_names = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }

        status_str = status_names.get(status, "UNKNOWN")  # type: ignore[arg-type]

        solution = {
            "status": status_str,
            "solve_time": solve_time,
            "objective_value": (
                solver.ObjectiveValue()
                if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]
                else None
            ),
            "assignments": {},
        }

        # Extract solution if feasible
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            for (m_id, r, d), var in self.assignments.items():
                if solver.Value(var) == 1:
                    if d not in solution["assignments"]:
                        solution["assignments"][d] = {}
                    solution["assignments"][d][r] = m_id

        return status_str, solution


def create_sample_problem():
    """Create a sample scheduling problem for testing.

    Scenario: 4 weekend days in a month, 3 roles, 5 members with varying capabilities.
    """
    # Sample members
    members = [
        SimpleMember(
            1, "Alice", ["duty_officer", "instructor", "towpilot"], max_assignments=6
        ),
        SimpleMember(2, "Bob", ["duty_officer", "towpilot"], max_assignments=4),
        SimpleMember(
            3, "Carol", ["instructor", "assistant_duty_officer"], max_assignments=5
        ),
        SimpleMember(
            4, "Dave", ["duty_officer", "assistant_duty_officer"], max_assignments=3
        ),
        SimpleMember(
            5, "Eve", ["towpilot", "assistant_duty_officer"], max_assignments=8
        ),
    ]

    # 4 weekend dates (2 Saturdays, 2 Sundays)
    base_date = date(2026, 3, 7)  # First Saturday in March 2026
    dates = [
        base_date,  # Sat Mar 7
        base_date + timedelta(days=1),  # Sun Mar 8
        base_date + timedelta(days=7),  # Sat Mar 14
        base_date + timedelta(days=8),  # Sun Mar 15
    ]

    # 3 roles to schedule
    roles = ["duty_officer", "assistant_duty_officer", "towpilot"]

    # Blackouts: Carol unavailable on Mar 8, Dave unavailable on Mar 14-15
    blackouts = {
        (3, dates[1]),  # Carol on Mar 8
        (4, dates[2]),  # Dave on Mar 14
        (4, dates[3]),  # Dave on Mar 15
    }

    return members, dates, roles, blackouts


def run_poc():
    """Run proof of concept test."""
    print("=" * 70)
    print("OR-Tools Duty Roster Scheduling - Proof of Concept")
    print("=" * 70)
    print()

    # Create sample problem
    members, dates, roles, blackouts = create_sample_problem()

    print("Problem Setup:")
    print(f"  Members: {len(members)}")
    for m in members:
        print(f"    - {m.name}: {', '.join(sorted(m.roles))}")
    print(f"  Dates: {len(dates)} ({dates[0]} to {dates[-1]})")
    print(f"  Roles: {', '.join(roles)}")
    print(f"  Blackouts: {len(blackouts)}")
    for m_id, d in sorted(blackouts):
        member = next(m for m in members if m.id == m_id)
        print(f"    - {member.name} unavailable on {d}")
    print()

    # Build and solve problem
    print("Building constraint model...")
    problem = ScheduleProblem(members, dates, roles, blackouts)
    problem.add_constraints()
    problem.set_objective()

    print("Solving...")
    status, solution = problem.solve()

    print()
    print("=" * 70)
    print(f"Solution Status: {status}")
    print(f"Solve Time: {solution['solve_time']:.3f} seconds")
    if solution["objective_value"] is not None:
        print(f"Objective Value: {solution['objective_value']:.0f}")
    print("=" * 70)
    print()

    if status in ["OPTIMAL", "FEASIBLE"]:
        print("Schedule:")
        print()
        for d in sorted(solution["assignments"].keys()):
            print(f"{d.strftime('%A, %B %d, %Y')}:")
            for r, m_id in sorted(solution["assignments"][d].items()):
                member = next(m for m in members if m.id == m_id)
                print(f"  {r:25s} -> {member.name}")
            print()

        # Count assignments per member
        member_counts = {m.id: 0 for m in members}
        for d_assignments in solution["assignments"].values():
            for m_id in d_assignments.values():
                member_counts[m_id] += 1

        print("Assignment Counts:")
        for m in members:
            count = member_counts[m.id]
            max_count = m.max_assignments
            print(f"  {m.name:10s}: {count}/{max_count} assignments")
        print()

    elif status == "INFEASIBLE":
        print(
            "❌ Problem is INFEASIBLE - no solution exists that satisfies all constraints."
        )
        print("   This could mean:")
        print("   - Not enough eligible members for all roles")
        print("   - Blackouts make some dates impossible to fill")
        print("   - Conflicting constraints")
        print()

    return status, solution


if __name__ == "__main__":
    run_poc()
