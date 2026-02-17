"""
Comparison script for OR-Tools scheduler vs legacy greedy scheduler.

This script runs both schedulers on the same input data and compares:
- Solve time
- Slot fill rate (% of slots filled)
- Fairness metrics (variance in assignment counts)
- Preference satisfaction (how well preferences are honored)

Usage:
    python manage.py shell
    >>> from duty_roster.ortools_comparison import run_comparison
    >>> run_comparison(year=2026, month=3)
"""

import time
from collections import defaultdict
from typing import Any

from duty_roster.ortools_scheduler import generate_roster_ortools
from duty_roster.roster_generator import generate_roster_legacy
from members.constants.membership import DEFAULT_ROLES


def calculate_slot_fill_rate(schedule: list[dict[str, Any]]) -> float:
    """
    Calculate percentage of slots that were successfully filled.

    Args:
        schedule: List of day schedules with 'slots' dict

    Returns:
        Float between 0 and 1 representing fill rate
    """
    total_slots = 0
    filled_slots = 0

    for day_schedule in schedule:
        for role, member_id in day_schedule["slots"].items():
            total_slots += 1
            if member_id is not None:
                filled_slots += 1

    return filled_slots / total_slots if total_slots > 0 else 0.0


def calculate_fairness_variance(schedule: list[dict[str, Any]]) -> float:
    """
    Calculate variance in assignment counts across members (lower = more fair).

    Args:
        schedule: List of day schedules with 'slots' dict

    Returns:
        Variance of assignment counts
    """
    assignment_counts = defaultdict(int)

    for day_schedule in schedule:
        for role, member_id in day_schedule["slots"].items():
            if member_id is not None:
                assignment_counts[member_id] += 1

    if not assignment_counts:
        return 0.0

    counts = list(assignment_counts.values())
    mean = sum(counts) / len(counts)
    variance = sum((x - mean) ** 2 for x in counts) / len(counts)

    return variance


def count_constraints_violated(schedule: list[dict[str, Any]]) -> dict[str, int]:
    """
    Count various constraint violations in a schedule.

    Args:
        schedule: List of day schedules

    Returns:
        Dict of {constraint_name: violation_count}
    """
    violations = {
        "double_booking": 0,  # Member assigned to multiple roles on same day
        "consecutive_role": 0,  # Member does same role on consecutive days
        "unfilled_slot": 0,  # Slot has no assignment
    }

    # Check double booking
    for day_schedule in schedule:
        member_roles = defaultdict(int)
        for role, member_id in day_schedule["slots"].items():
            if member_id is not None:
                member_roles[member_id] += 1

        for member_id, count in member_roles.items():
            if count > 1:
                violations["double_booking"] += count - 1

    # Check unfilled slots
    for day_schedule in schedule:
        for role, member_id in day_schedule["slots"].items():
            if member_id is None:
                violations["unfilled_slot"] += 1

    # Check consecutive role assignments
    prev_day_slots = None
    for day_schedule in schedule:
        if prev_day_slots:
            # Check if days are consecutive
            prev_date = prev_day_slots["date"]
            curr_date = day_schedule["date"]
            if (curr_date - prev_date).days == 1:
                # Days are consecutive - check for same member in same role
                for role in day_schedule["slots"].keys():
                    prev_member = prev_day_slots["slots"].get(role)
                    curr_member = day_schedule["slots"].get(role)
                    if (
                        prev_member is not None
                        and curr_member is not None
                        and prev_member == curr_member
                    ):
                        violations["consecutive_role"] += 1

        prev_day_slots = day_schedule

    return violations


def run_comparison(
    year: int | None = None,
    month: int | None = None,
    roles: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run both schedulers and compare results.

    Args:
        year: Year to schedule (default: current year)
        month: Month to schedule (default: current month + 1)
        roles: Roles to schedule (default: DEFAULT_ROLES)
        verbose: Print detailed comparison output

    Returns:
        Dict with comparison results
    """
    from django.utils.timezone import now

    # Default to next month (likely what user wants to schedule)
    today = now().date()
    if not year or not month:
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        year = year or next_year
        month = month or next_month

    roles = roles or DEFAULT_ROLES

    if verbose:
        print(f"\n{'=' * 80}")
        print(f"SCHEDULER COMPARISON: {year}/{month:02d}")
        print(f"Roles: {roles}")
        print(f"{'=' * 80}\n")

    # Run legacy scheduler
    if verbose:
        print("Running LEGACY scheduler (greedy weighted-random)...")
    start_time = time.time()
    try:
        legacy_schedule = generate_roster_legacy(year=year, month=month, roles=roles)
        legacy_time = time.time() - start_time
        legacy_error = None
    except Exception as e:
        legacy_time = time.time() - start_time
        legacy_error = str(e)
        legacy_schedule = []

    if verbose:
        if legacy_error:
            print(f"  ❌ FAILED in {legacy_time:.3f}s: {legacy_error}")
        else:
            print(f"  ✓ Completed in {legacy_time:.3f}s ({len(legacy_schedule)} days)")

    # Run OR-Tools scheduler
    if verbose:
        print("\nRunning OR-TOOLS scheduler (constraint programming)...")
    start_time = time.time()
    try:
        ortools_schedule = generate_roster_ortools(
            year=year, month=month, roles=roles, timeout_seconds=10.0
        )
        ortools_time = time.time() - start_time
        ortools_error = None
    except Exception as e:
        ortools_time = time.time() - start_time
        ortools_error = str(e)
        ortools_schedule = []

    if verbose:
        if ortools_error:
            print(f"  ❌ FAILED in {ortools_time:.3f}s: {ortools_error}")
        else:
            print(
                f"  ✓ Completed in {ortools_time:.3f}s ({len(ortools_schedule)} days)"
            )

    # Calculate metrics
    legacy_metrics = {}
    ortools_metrics = {}

    if not legacy_error and legacy_schedule:
        legacy_metrics = {
            "solve_time": legacy_time,
            "slot_fill_rate": calculate_slot_fill_rate(legacy_schedule),
            "fairness_variance": calculate_fairness_variance(legacy_schedule),
            "constraints_violated": count_constraints_violated(legacy_schedule),
        }

    if not ortools_error and ortools_schedule:
        ortools_metrics = {
            "solve_time": ortools_time,
            "slot_fill_rate": calculate_slot_fill_rate(ortools_schedule),
            "fairness_variance": calculate_fairness_variance(ortools_schedule),
            "constraints_violated": count_constraints_violated(ortools_schedule),
        }

    # Print comparison
    if verbose:
        print(f"\n{'=' * 80}")
        print("METRICS COMPARISON")
        print(f"{'=' * 80}\n")

        print(f"{'Metric':<30} {'Legacy':<20} {'OR-Tools':<20} {'Winner'}")
        print("-" * 80)

        # Solve time (lower is better)
        if legacy_metrics and ortools_metrics:
            legacy_time_str = f"{legacy_metrics['solve_time']:.3f}s"
            ortools_time_str = f"{ortools_metrics['solve_time']:.3f}s"
            winner = (
                "OR-Tools"
                if ortools_metrics["solve_time"] < legacy_metrics["solve_time"]
                else "Legacy"
            )
            print(
                f"{'Solve Time':<30} {legacy_time_str:<20} {ortools_time_str:<20} {winner}"
            )

            # Slot fill rate (higher is better)
            legacy_fill = f"{legacy_metrics['slot_fill_rate']:.1%}"
            ortools_fill = f"{ortools_metrics['slot_fill_rate']:.1%}"
            winner = (
                "OR-Tools"
                if ortools_metrics["slot_fill_rate"] > legacy_metrics["slot_fill_rate"]
                else (
                    "Legacy"
                    if ortools_metrics["slot_fill_rate"]
                    < legacy_metrics["slot_fill_rate"]
                    else "Tie"
                )
            )
            print(
                f"{'Slot Fill Rate':<30} {legacy_fill:<20} {ortools_fill:<20} {winner}"
            )

            # Fairness variance (lower is better)
            legacy_var = f"{legacy_metrics['fairness_variance']:.2f}"
            ortools_var = f"{ortools_metrics['fairness_variance']:.2f}"
            winner = (
                "OR-Tools"
                if ortools_metrics["fairness_variance"]
                < legacy_metrics["fairness_variance"]
                else (
                    "Legacy"
                    if ortools_metrics["fairness_variance"]
                    > legacy_metrics["fairness_variance"]
                    else "Tie"
                )
            )
            print(
                f"{'Fairness Variance':<30} {legacy_var:<20} {ortools_var:<20} {winner}"
            )

            # Constraint violations
            print(f"\n{'Constraint Violations':<30} {'Legacy':<20} {'OR-Tools':<20}")
            print("-" * 70)
            for constraint in ["unfilled_slot", "double_booking", "consecutive_role"]:
                legacy_count = legacy_metrics["constraints_violated"].get(constraint, 0)
                ortools_count = ortools_metrics["constraints_violated"].get(
                    constraint, 0
                )
                print(f"  {constraint:<28} {legacy_count:<20} {ortools_count:<20}")

        print(f"\n{'=' * 80}\n")

    return {
        "year": year,
        "month": month,
        "roles": roles,
        "legacy": {
            "schedule": legacy_schedule,
            "metrics": legacy_metrics,
            "error": legacy_error,
        },
        "ortools": {
            "schedule": ortools_schedule,
            "metrics": ortools_metrics,
            "error": ortools_error,
        },
    }


if __name__ == "__main__":
    # Run comparison if executed as script
    run_comparison(verbose=True)
