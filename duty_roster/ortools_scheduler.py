"""
Production OR-Tools scheduler for duty roster generation.

This module implements a constraint programming approach to duty roster scheduling
using Google OR-Tools CP-SAT solver. It replaces the greedy weighted-random algorithm
with a declarative constraint model that searches for optimal solutions and, when proven
within configured limits, returns an optimal schedule; otherwise it returns the best
feasible schedule found (or infeasibility/unknown).

Phase 2 Implementation: Full production constraints matching legacy scheduler behavior.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from ortools.sat.python import cp_model

from duty_roster.models import (
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
)
from members.models import Member

logger = logging.getLogger("duty_roster.ortools_scheduler")


# Constants
DEFAULT_MAX_ASSIGNMENTS = 8  # For members without DutyPreference
PAIRING_MULTIPLIER = 3  # Weight multiplier for preferred pairings


@dataclass
class SchedulingData:
    """
    Container for all data needed by the OR-Tools scheduler.

    Extracted from Django ORM and preprocessed for efficient constraint creation.
    """

    members: list[Member]
    duty_days: list[date]
    roles: list[str]
    preferences: dict[int, DutyPreference]
    blackouts: set[tuple[int, date]]
    avoidances: set[tuple[int, int]]
    pairings: set[tuple[int, int]]
    role_scarcity: dict[str, dict[str, Any]]
    earliest_duty_day: date


class DutyRosterScheduler:
    """
    OR-Tools constraint programming scheduler for duty roster generation.

    This class encapsulates the constraint model, solver configuration, and
    result extraction logic for optimal duty roster scheduling.

    Usage:
        data = extract_scheduling_data(year=2026, month=3, roles=DEFAULT_ROLES)
        scheduler = DutyRosterScheduler(data)
        schedule = scheduler.solve()
    """

    def __init__(self, data: SchedulingData):
        """
        Initialize scheduler with preprocessed data.

        Args:
            data: SchedulingData object with all necessary scheduling information
        """
        self.data = data
        self.model = cp_model.CpModel()
        self.x = {}  # Decision variables: x[member_id, role, day] = BoolVar
        self.solver = cp_model.CpSolver()

        # Configure solver parameters
        self.solver.parameters.max_time_in_seconds = 10.0
        self.solver.parameters.num_search_workers = 4
        self.solver.parameters.log_search_progress = False  # Set to True for debugging

    def _create_decision_variables(self):
        """
        Create decision variables x[member_id, role, day] for valid assignments.

        Uses sparse variable creation: only creates variables for (member, role, day)
        tuples that are potentially valid (i.e., not blocked by hard constraints).

        This reduces the variable count by ~60-80% compared to naive full creation.
        """
        logger.info("Creating decision variables (sparse creation)...")
        valid_tuples = set()

        for member in self.data.members:
            pref = self.data.preferences.get(member.id)

            # Skip globally blocked members
            if pref and (pref.dont_schedule or pref.scheduling_suspended):
                logger.debug(
                    f"Skipping {member.full_display_name}: dont_schedule or suspended"
                )
                continue

            for role in self.data.roles:
                # Check role qualification
                if not getattr(member, role, False):
                    continue  # Member not qualified for this role

                # Check role percentage (hard constraint if 0% and not overridden)
                if not self._is_role_allowed(member, role, pref):
                    logger.debug(
                        f"Skipping {member.full_display_name} for {role}: 0% preference"
                    )
                    continue

                for day in self.data.duty_days:
                    # Check blackout
                    if (member.id, day) in self.data.blackouts:
                        continue  # Member blacked out on this day

                    # Tuple is valid - create variable
                    valid_tuples.add((member.id, role, day))

        # Create BoolVars for all valid tuples in a deterministic order
        for member_id, role, day in sorted(
            valid_tuples, key=lambda t: (t[0], t[1], t[2])
        ):
            var_name = f"x_{member_id}_{role}_{day}"
            self.x[member_id, role, day] = self.model.NewBoolVar(var_name)

        logger.info(
            f"Created {len(self.x)} decision variables from {len(valid_tuples)} valid tuples"
        )

    def _is_role_allowed(
        self, member: Member, role: str, pref: DutyPreference | None
    ) -> bool:
        """
        Check if member can be assigned to role based on percentage preferences.

        Implements the complex 0% override logic:
        - If member has only one eligible role and percent is 0, treat as 100% (allowed)
        - If member has multiple roles and all are 0%, treat all as 100% (allowed)
        - Otherwise, 0% means not allowed (hard constraint)

        Args:
            member: Member object
            role: Role name (e.g., 'instructor')
            pref: DutyPreference object or None

        Returns:
            True if member can be assigned to role, False if blocked by 0% preference
        """
        if not pref:
            return True  # No preference = treat as 100% for all roles

        # Get percent for this role
        percent = self._get_role_percent(pref, role)

        # Determine eligible roles for member
        eligible_roles = [r for r in self.data.roles if getattr(member, r, False)]

        if len(eligible_roles) == 1:
            # Single role: treat 0% as 100% (override logic)
            return True

        # Multiple roles: check if all are zero
        all_zero = all(self._get_role_percent(pref, r) == 0 for r in eligible_roles)
        if all_zero:
            # All zero: treat all as 100% (override logic)
            return True

        # Not all zero: enforce 0% as hard constraint (not allowed)
        return percent > 0

    def _get_role_percent(self, pref: DutyPreference, role: str) -> int:
        """
        Get preference percentage for a role.

        Args:
            pref: DutyPreference object
            role: Role name

        Returns:
            Preference percentage (0-100)
        """
        field_map = {
            "instructor": "instructor_percent",
            "towpilot": "towpilot_percent",
            "duty_officer": "duty_officer_percent",
            "assistant_duty_officer": "ado_percent",
        }
        field_name = field_map.get(role, f"{role}_percent")
        return getattr(pref, field_name, 0)

    def _add_hard_constraints(self):
        """
        Add all hard constraints to the model.

        Hard constraints MUST be satisfied for a valid solution:
        1. One assignment per slot (100% slot fill)
        2. Role qualification (member has role flag)
        3. Don't schedule / suspended flags (handled in variable creation)
        4. Blackout dates (handled in variable creation)
        5. Avoidance constraints (can't work with certain members)
        6. One assignment per day (no double-booking)
        7. Anti-repeat constraint (no same role on consecutive days)
        8. Role percentage zero (handled in variable creation for most cases)
        9. Max assignments per month
        """
        logger.info("Adding hard constraints...")

        # Constraint 1: One assignment per slot
        self._add_one_assignment_per_slot()

        # Constraint 5: Avoidance constraints
        self._add_avoidance_constraints()

        # Constraint 6: One assignment per day
        self._add_one_assignment_per_day()

        # Constraint 7: Anti-repeat constraint
        self._add_anti_repeat_constraints()

        # Constraint 9: Max assignments per month
        self._add_max_assignments_constraints()

        logger.info("Hard constraints added successfully")

    def _add_one_assignment_per_slot(self):
        """
        Constraint: Each role on each day must have exactly one member assigned.

        Ensures 100% slot fill rate.
        """
        # Prioritize roles by scarcity (most constrained first)
        prioritized_roles = sorted(
            self.data.roles, key=lambda r: self.data.role_scarcity[r]["scarcity_score"]
        )

        logger.debug(f"Role priority order (by scarcity): {prioritized_roles}")

        for role in prioritized_roles:
            for day in self.data.duty_days:
                # Sum over all members: exactly one must be assigned
                members_for_slot = [
                    self.x[m.id, role, day]
                    for m in self.data.members
                    if (m.id, role, day) in self.x
                ]

                if members_for_slot:
                    self.model.Add(sum(members_for_slot) == 1)
                else:
                    # No eligible members for this slot - fail fast with clear diagnostics
                    message = f"No eligible members for {role} on {day} - schedule infeasible."
                    logger.error(message)
                    raise RuntimeError(message)

    def _add_avoidance_constraints(self):
        """
        Constraint: Members who avoid each other cannot be assigned on the same day.

        If (m1, m2) is in avoidances, then at most one of m1 or m2 can be assigned
        on any given day (across all roles).
        """
        for m1_id, m2_id in self.data.avoidances:
            for day in self.data.duty_days:
                # Collect all assignments for m1 on this day
                m1_assignments = [
                    self.x[m1_id, role, day]
                    for role in self.data.roles
                    if (m1_id, role, day) in self.x
                ]

                # Collect all assignments for m2 on this day
                m2_assignments = [
                    self.x[m2_id, role, day]
                    for role in self.data.roles
                    if (m2_id, role, day) in self.x
                ]

                # At most one of (m1 assigned, m2 assigned) can be true
                if m1_assignments and m2_assignments:
                    self.model.Add(sum(m1_assignments) + sum(m2_assignments) <= 1)

    def _add_one_assignment_per_day(self):
        """
        Constraint: Members can be assigned to at most one role per day.

        Prevents double-booking (e.g., member assigned as both instructor and towpilot).
        """
        for member in self.data.members:
            for day in self.data.duty_days:
                # Sum over all roles: at most one
                assignments_today = [
                    self.x[member.id, role, day]
                    for role in self.data.roles
                    if (member.id, role, day) in self.x
                ]

                if (
                    len(assignments_today) > 1
                ):  # Only constrain if multiple roles possible
                    self.model.Add(sum(assignments_today) <= 1)

    def _add_anti_repeat_constraints(self):
        """
        Constraint: Members cannot do the same role on consecutive days.

        Only applies to calendar-consecutive days (e.g., Saturday->Sunday),
        not across week gaps (e.g., Sunday->next Saturday).
        """
        for member in self.data.members:
            for role in self.data.roles:
                for i in range(len(self.data.duty_days) - 1):
                    day1 = self.data.duty_days[i]
                    day2 = self.data.duty_days[i + 1]

                    # Check if days are calendar-consecutive (not week-separated)
                    if (day2 - day1).days == 1:
                        # Check if both variables exist in our sparse set
                        key1 = (member.id, role, day1)
                        key2 = (member.id, role, day2)

                        if key1 in self.x and key2 in self.x:
                            # Constraint: can't do same role on both days
                            self.model.Add(self.x[key1] + self.x[key2] <= 1)

    def _add_max_assignments_constraints(self):
        """
        Constraint: Members cannot exceed their max assignments per month.

        Default is 8 for members without DutyPreference.
        """
        for member in self.data.members:
            pref = self.data.preferences.get(member.id)
            max_assignments = (
                pref.max_assignments_per_month if pref else DEFAULT_MAX_ASSIGNMENTS
            )

            # Handle edge case: if max_assignments is 0, treat as model default (2)
            # This matches legacy behavior and the DutyPreference model default
            if max_assignments == 0:
                max_assignments = 2

            # Sum all assignments for this member
            total_assignments = [
                self.x[member.id, role, day]
                for role in self.data.roles
                for day in self.data.duty_days
                if (member.id, role, day) in self.x
            ]

            if total_assignments:
                self.model.Add(sum(total_assignments) <= max_assignments)

    def _add_objective_function(self):
        """
        Add objective function to maximize member satisfaction and fairness.

        Soft constraints (preferences) are encoded as weighted terms in the objective:
        1. Role preference weighting (higher % = higher weight)
        2. Pairing affinity bonus (members who prefer to work together)
        3. Last duty date balancing (prioritize members who haven't worked recently)

        The solver will maximize the sum of these weighted terms while respecting
        all hard constraints.
        """
        logger.info("Building objective function...")
        objective_terms = []

        # Soft constraint 1: Role preference weighting
        for member in self.data.members:
            for role in self.data.roles:
                for day in self.data.duty_days:
                    if (member.id, role, day) in self.x:
                        weight = self._calculate_preference_weight(member, role)
                        objective_terms.append(weight * self.x[member.id, role, day])

        # Soft constraint 2: Pairing affinity bonus
        # Cache member_assigned_on_day indicators to avoid creating duplicates for each pairing
        member_assigned_on_day = {}
        for day in self.data.duty_days:
            for member in self.data.members:
                member_vars = [
                    self.x[member.id, role, day]
                    for role in self.data.roles
                    if (member.id, role, day) in self.x
                ]
                if member_vars:
                    assigned_var = self.model.NewBoolVar(f"assigned_{member.id}_{day}")
                    self.model.AddMaxEquality(assigned_var, member_vars)
                    member_assigned_on_day[member.id, day] = assigned_var

        # Apply pairing bonuses using cached indicators
        for day in self.data.duty_days:
            for m1_id, m2_id in self.data.pairings:
                # Check if both members have cached assignment indicators for this day
                if (m1_id, day) in member_assigned_on_day and (
                    m2_id,
                    day,
                ) in member_assigned_on_day:
                    m1_assigned = member_assigned_on_day[m1_id, day]
                    m2_assigned = member_assigned_on_day[m2_id, day]

                    # Create indicator: both_assigned = 1 iff both assigned
                    both_assigned = self.model.NewBoolVar(
                        f"paired_{m1_id}_{m2_id}_{day}"
                    )

                    # both_assigned = m1_assigned AND m2_assigned
                    self.model.AddBoolAnd([m1_assigned, m2_assigned]).OnlyEnforceIf(
                        both_assigned
                    )
                    self.model.AddBoolOr(
                        [m1_assigned.Not(), m2_assigned.Not()]
                    ).OnlyEnforceIf(both_assigned.Not())

                    # Add bonus to objective
                    pairing_bonus = 100 * (
                        PAIRING_MULTIPLIER - 1
                    )  # Base weight * multiplier
                    objective_terms.append(pairing_bonus * both_assigned)

        # Soft constraint 3: Last duty date balancing
        for member in self.data.members:
            pref = self.data.preferences.get(member.id)
            last_duty = (
                pref.last_duty_date
                if (pref and pref.last_duty_date)
                else date(1900, 1, 1)
            )
            days_since = (self.data.earliest_duty_day - last_duty).days

            # Cap staleness to prevent dominating objective (max 365 days = 1 year)
            # This prevents very large weights (45k+) for members who have never worked
            staleness_weight = min(max(0, days_since), 365)

            for role in self.data.roles:
                for day in self.data.duty_days:
                    if (member.id, role, day) in self.x:
                        objective_terms.append(
                            staleness_weight * self.x[member.id, role, day]
                        )

        # Set objective: maximize total weighted satisfaction
        self.model.Maximize(sum(objective_terms))
        logger.info(f"Objective function built with {len(objective_terms)} terms")

    def _calculate_preference_weight(self, member: Member, role: str) -> int:
        """
        Calculate preference weight for assigning member to role.

        Implements the same percentage override logic as _is_role_allowed:
        - No preference: 100
        - Single role with 0%: 100
        - All roles 0%: 100
        - Otherwise: actual percentage (0-100)

        Args:
            member: Member object
            role: Role name

        Returns:
            Weight value (0-100, typically)
        """
        pref = self.data.preferences.get(member.id)
        if not pref:
            return 100  # Default weight for members without preferences

        percent = self._get_role_percent(pref, role)

        # Determine eligible roles for member
        eligible_roles = [r for r in self.data.roles if getattr(member, r, False)]

        if len(eligible_roles) == 1:
            # Single role: use 100 if percent is 0
            return 100 if percent == 0 else percent

        # Multiple roles: check if all are zero
        all_zero = all(self._get_role_percent(pref, r) == 0 for r in eligible_roles)
        if all_zero:
            return 100  # Treat all as 100

        # Return actual percent
        return percent

    def solve(self, timeout_seconds: float = 10.0) -> dict[str, Any]:
        """
        Build constraint model and solve for optimal duty roster.

        Returns:
            Dict with:
                - 'status': Solver status (OPTIMAL, FEASIBLE, INFEASIBLE, UNKNOWN)
                - 'schedule': List of dicts with {'date': ..., 'slots': {role: member_id}}
                - 'solve_time': Solver runtime in seconds
                - 'objective_value': Final objective value (if solution found)
                - 'diagnostics': Additional solver diagnostics
        """
        logger.info("Starting OR-Tools duty roster scheduler...")

        # Configure solver timeout
        self.solver.parameters.max_time_in_seconds = timeout_seconds

        # Step 1: Create decision variables
        self._create_decision_variables()

        # Step 2: Add hard constraints
        self._add_hard_constraints()

        # Step 3: Add objective function (soft constraints)
        self._add_objective_function()

        # Step 4: Solve
        logger.info("Invoking CP-SAT solver...")
        status = self.solver.Solve(self.model)

        # Step 5: Extract results
        result = self._extract_results(status)

        logger.info(
            f"Solver finished: status={result['status']}, "
            f"time={result['solve_time']:.3f}s, "
            f"objective={result.get('objective_value', 'N/A')}"
        )

        return result

    def _extract_results(self, status) -> dict[str, Any]:
        """
        Extract schedule from solver solution.

        Args:
            status: CpSolverStatus enum value

        Returns:
            Dict with status, schedule, solve_time, objective_value, diagnostics
        """
        status_names = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }

        result = {
            "status": status_names.get(status, "UNKNOWN"),  # type: ignore[arg-type]
            "solve_time": self.solver.WallTime(),
            "schedule": [],
            "diagnostics": {
                "num_conflicts": self.solver.NumConflicts(),
                "num_branches": self.solver.NumBranches(),
            },
        }

        # Only extract schedule if solution found
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            result["objective_value"] = self.solver.ObjectiveValue()
            result["schedule"] = self._build_schedule_from_solution()
        else:
            result["objective_value"] = None
            logger.error(f"Solver failed with status: {result['status']}")

        return result

    def _build_schedule_from_solution(self) -> list[dict[str, Any]]:
        """
        Build schedule list from solver solution.

        Returns:
            List of dicts with {'date': date, 'slots': {role: member_id}, 'diagnostics': {role: None}}
            where diagnostics contains all roles set to None, matching legacy format.
        """
        schedule = []

        for day in self.data.duty_days:
            slots = {}
            for role in self.data.roles:
                # Find which member is assigned to this role on this day
                assigned_member = None
                for member in self.data.members:
                    if (member.id, role, day) in self.x:
                        if self.solver.Value(self.x[member.id, role, day]) == 1:
                            assigned_member = member.id
                            break

                slots[role] = assigned_member

            # Build diagnostics dict with all roles set to None (matching legacy format)
            diagnostics = {role: None for role in self.data.roles}
            schedule.append({"date": day, "slots": slots, "diagnostics": diagnostics})

        return schedule


def extract_scheduling_data(
    year: int | None = None,
    month: int | None = None,
    roles: list[str] | None = None,
    exclude_dates: list[date] | set[date] | None = None,
) -> SchedulingData:
    """
    Extract all necessary data from Django ORM for OR-Tools scheduler.

    Args:
        year: Year to schedule (default: current year)
        month: Month to schedule (default: current month)
        roles: List of roles to schedule (default: DEFAULT_ROLES)
        exclude_dates: Dates to exclude from scheduling (e.g., user-removed dates)

    Returns:
        SchedulingData object with all preprocessed scheduling information
    """
    import calendar

    from django.utils.timezone import now

    from members.constants.membership import DEFAULT_ROLES

    # Default to current year/month
    today = now().date()
    year = year or today.year
    month = month or today.month
    roles = roles or DEFAULT_ROLES

    # Get all weekend dates in month
    cal = calendar.Calendar()
    all_weekend_dates = [
        d
        for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() in (5, 6)
    ]

    # Filter by operational season
    from duty_roster.roster_generator import is_within_operational_season

    duty_days = [d for d in all_weekend_dates if is_within_operational_season(d)]

    # Exclude user-removed dates
    if exclude_dates:
        exclude_set = set(exclude_dates)
        duty_days = [d for d in duty_days if d not in exclude_set]

    # Query Django ORM
    members = list(Member.objects.filter(is_active=True))
    preferences = {
        p.member_id: p for p in DutyPreference.objects.select_related("member").all()
    }
    blackouts = {
        (b.member_id, b.date)
        for b in MemberBlackout.objects.filter(date__year=year, date__month=month)
    }
    avoidances = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
    pairings_qs = DutyPairing.objects.all()
    pairings = set()
    for p in pairings_qs:
        member_id = p.member_id
        pair_with_id = p.pair_with_id
        # Treat pairings as undirected: canonicalize each pair so (A,B) and (B,A)
        # are represented once as (min_id, max_id), matching legacy behavior.
        if member_id is None or pair_with_id is None:
            continue
        if member_id == pair_with_id:
            continue
        a, b = sorted((member_id, pair_with_id))
        pairings.add((a, b))

    # Calculate role scarcity
    from duty_roster.roster_generator import calculate_role_scarcity

    role_scarcity = {}
    for role in roles:
        scarcity_data = calculate_role_scarcity(
            members, preferences, blackouts, duty_days, role
        )
        role_scarcity[role] = scarcity_data

    # Determine earliest duty day for staleness calculation
    earliest_duty_day = min(duty_days) if duty_days else today

    return SchedulingData(
        members=members,
        duty_days=duty_days,
        roles=roles,
        preferences=preferences,
        blackouts=blackouts,
        avoidances=avoidances,
        pairings=pairings,
        role_scarcity=role_scarcity,
        earliest_duty_day=earliest_duty_day,
    )


def generate_roster_ortools(
    year: int | None = None,
    month: int | None = None,
    roles: list[str] | None = None,
    exclude_dates: list[date] | set[date] | None = None,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """
    Generate duty roster using OR-Tools constraint programming solver.

    This is the main entry point for Phase 2 OR-Tools scheduler, compatible with
    the legacy generate_roster() interface.

    Args:
        year: Year to schedule (default: current year)
        month: Month to schedule (default: current month)
        roles: List of roles to schedule (default: DEFAULT_ROLES)
        exclude_dates: Dates to exclude from scheduling
        timeout_seconds: Solver timeout (default: 10 seconds)

    Returns:
        List of dicts with:
            - 'date': datetime.date for duty day
            - 'slots': {role: member_id} mapping
            - 'diagnostics': Per-slot diagnostic info (None if filled, dict if empty)

    Raises:
        RuntimeError: If solver fails to find solution
    """
    # Extract data from Django ORM
    data = extract_scheduling_data(year, month, roles, exclude_dates)

    # Create scheduler and solve
    scheduler = DutyRosterScheduler(data)
    result = scheduler.solve(timeout_seconds=timeout_seconds)

    # Check solver status
    if result["status"] not in ("OPTIMAL", "FEASIBLE"):
        logger.error(
            f"OR-Tools scheduler failed: status={result['status']}, "
            f"diagnostics={result['diagnostics']}"
        )
        raise RuntimeError(
            f"OR-Tools solver failed with status: {result['status']}. "
            "Falling back to legacy algorithm may be required."
        )

    return result["schedule"]
