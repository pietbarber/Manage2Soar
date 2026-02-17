"""
Management command to compare OR-Tools and legacy schedulers side-by-side.

This command runs both schedulers on the same input data and produces a detailed
comparison report including solve times, solution quality metrics, and differences.

Usage:
    python manage.py test_ortools_vs_legacy --year=2026 --month=3
    python manage.py test_ortools_vs_legacy --year=2026 --month=3 --json
    python manage.py test_ortools_vs_legacy --year=2026 --month=3 --roles=Instructor,Tow Pilot
"""

import json
import time
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from duty_roster.ortools_scheduler import generate_roster_ortools
from duty_roster.roster_generator import _generate_roster_legacy
from members.constants.membership import DEFAULT_ROLES
from members.models import Member


class Command(BaseCommand):
    help = "Compare OR-Tools and legacy schedulers side-by-side on same data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year to test (default: current year)",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=None,
            help="Month to test (1-12, default: current month)",
        )
        parser.add_argument(
            "--roles",
            type=str,
            default=None,
            help="Comma-separated list of roles to schedule (default: all DEFAULT_ROLES)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results as JSON instead of human-readable format",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed slot-by-slot comparison",
        )

    def handle(self, *args, **options):
        # Parse arguments
        year = options["year"] or timezone.now().year
        month = options["month"] or timezone.now().month

        if options["roles"]:
            roles = [r.strip() for r in options["roles"].split(",")]
        else:
            roles = DEFAULT_ROLES

        output_json = options["json"]
        verbose = options["verbose"]

        # Run comparison
        try:
            results = self.compare_schedulers(year, month, roles, verbose)

            if output_json:
                self.output_json(results)
            else:
                self.output_human_readable(results, verbose)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Comparison failed: {e}"))
            raise

    def compare_schedulers(self, year, month, roles, verbose=False):
        """Run both schedulers and collect comparison metrics."""
        self.stdout.write(f"Comparing schedulers for {year}-{month:02d}...")

        # Get member counts for context
        total_members = Member.objects.filter(is_active=True).count()

        # Count qualified members per role
        qualified_counts = {}
        for role in roles:
            if role == "Instructor":
                count = Member.objects.filter(is_active=True, instructor=True).count()
            elif role == "Tow Pilot":
                count = Member.objects.filter(is_active=True, towpilot=True).count()
            elif role == "Duty Officer":
                count = Member.objects.filter(is_active=True, duty_officer=True).count()
            elif role == "Assistant Duty Officer":
                count = Member.objects.filter(
                    is_active=True, assistant_duty_officer=True
                ).count()
            else:
                count = 0
            qualified_counts[role] = count

        # Run legacy scheduler
        self.stdout.write("  Running legacy scheduler...")
        legacy_start = time.perf_counter()
        try:
            legacy_schedule = _generate_roster_legacy(year, month, roles)
            legacy_time_ms = (time.perf_counter() - legacy_start) * 1000
            legacy_error = None
        except Exception as e:
            legacy_schedule = []
            legacy_time_ms = (time.perf_counter() - legacy_start) * 1000
            legacy_error = str(e)
            self.stdout.write(self.style.WARNING(f"    Legacy failed: {e}"))

        # Run OR-Tools scheduler
        self.stdout.write("  Running OR-Tools scheduler...")
        ortools_start = time.perf_counter()
        try:
            ortools_schedule = generate_roster_ortools(year, month, roles)
            ortools_time_ms = (time.perf_counter() - ortools_start) * 1000
            ortools_error = None
        except Exception as e:
            ortools_schedule = []
            ortools_time_ms = (time.perf_counter() - ortools_start) * 1000
            ortools_error = str(e)
            self.stdout.write(self.style.WARNING(f"    OR-Tools failed: {e}"))

        # Calculate metrics for both schedules
        legacy_metrics = self.calculate_metrics(legacy_schedule, roles)
        ortools_metrics = self.calculate_metrics(ortools_schedule, roles)

        # Compare assignments slot-by-slot
        differences = self.compare_assignments(legacy_schedule, ortools_schedule, roles)

        # Build results dict
        results = {
            "year": year,
            "month": month,
            "roles": roles,
            "context": {
                "total_members": total_members,
                "qualified_counts": qualified_counts,
                "num_weekend_days": (
                    len(legacy_schedule) if legacy_schedule else len(ortools_schedule)
                ),
                "total_slots": (
                    len(legacy_schedule) if legacy_schedule else len(ortools_schedule)
                )
                * len(roles),
            },
            "legacy": {
                "solve_time_ms": round(legacy_time_ms, 2),
                "error": legacy_error,
                "metrics": legacy_metrics,
            },
            "ortools": {
                "solve_time_ms": round(ortools_time_ms, 2),
                "error": ortools_error,
                "metrics": ortools_metrics,
            },
            "comparison": differences,
        }

        return results

    def calculate_metrics(self, schedule, roles):
        """Calculate quality metrics for a schedule."""
        if not schedule:
            return {
                "slot_fill_rate": 0.0,
                "filled_slots": 0,
                "total_slots": 0,
                "unfilled_slots": 0,
                "fairness_variance": 0.0,
                "assignments_per_member": {},
            }

        total_slots = len(schedule) * len(roles)
        filled_slots = 0
        assignments = defaultdict(int)

        for day_schedule in schedule:
            slots = day_schedule.get("slots", {})
            for role in roles:
                member_id = slots.get(role)
                if member_id is not None:
                    filled_slots += 1
                    assignments[member_id] += 1

        unfilled_slots = total_slots - filled_slots
        slot_fill_rate = (filled_slots / total_slots * 100) if total_slots > 0 else 0

        # Calculate fairness (variance in assignments per member)
        if assignments:
            assignment_counts = list(assignments.values())
            mean = sum(assignment_counts) / len(assignment_counts)
            variance = sum((x - mean) ** 2 for x in assignment_counts) / len(
                assignment_counts
            )
        else:
            variance = 0.0

        return {
            "slot_fill_rate": round(slot_fill_rate, 2),
            "filled_slots": filled_slots,
            "total_slots": total_slots,
            "unfilled_slots": unfilled_slots,
            "fairness_variance": round(variance, 4),
            "assignments_per_member": dict(assignments),
        }

    def compare_assignments(self, legacy_schedule, ortools_schedule, roles):
        """Compare assignments slot-by-slot between schedulers."""
        # Handle case where one scheduler failed
        if not legacy_schedule or not ortools_schedule:
            return {
                "total_slots": 0,
                "same_assignments": 0,
                "different_assignments": 0,
                "same_percentage": 0.0,
                "slot_differences": [],
            }

        total_slots = 0
        same_assignments = 0
        different_assignments = 0
        slot_differences = []

        # Compare each day
        for legacy_day, ortools_day in zip(legacy_schedule, ortools_schedule):
            day_date = legacy_day.get("date")
            legacy_slots = legacy_day.get("slots", {})
            ortools_slots = ortools_day.get("slots", {})

            for role in roles:
                total_slots += 1
                legacy_member = legacy_slots.get(role)
                ortools_member = ortools_slots.get(role)

                if legacy_member == ortools_member:
                    same_assignments += 1
                else:
                    different_assignments += 1
                    slot_differences.append(
                        {
                            "date": (
                                day_date.isoformat()
                                if isinstance(day_date, date)
                                else str(day_date)
                            ),
                            "role": role,
                            "legacy_member_id": legacy_member,
                            "ortools_member_id": ortools_member,
                        }
                    )

        same_percentage = (
            (same_assignments / total_slots * 100) if total_slots > 0 else 0
        )

        return {
            "total_slots": total_slots,
            "same_assignments": same_assignments,
            "different_assignments": different_assignments,
            "same_percentage": round(same_percentage, 2),
            "slot_differences": slot_differences,
        }

    def output_json(self, results):
        """Output results as JSON."""
        self.stdout.write(json.dumps(results, indent=2))

    def output_human_readable(self, results, verbose=False):
        """Output results in human-readable format."""
        ctx = results["context"]
        legacy = results["legacy"]
        ortools = results["ortools"]
        comp = results["comparison"]

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Scheduler Comparison Report"))
        self.stdout.write("=" * 70)

        self.stdout.write(f"\nMonth: {results['year']}-{results['month']:02d}")
        self.stdout.write(f"Roles: {', '.join(results['roles'])}")
        self.stdout.write(f"Members: {ctx['total_members']} active")
        for role, count in ctx["qualified_counts"].items():
            self.stdout.write(f"  {role}: {count} qualified")
        self.stdout.write(f"Weekend days: {ctx['num_weekend_days']}")
        self.stdout.write(
            f"Total slots: {ctx['total_slots']} ({ctx['num_weekend_days']} days × {len(results['roles'])} roles)"
        )

        # Legacy results
        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.HTTP_INFO("LEGACY SCHEDULER:"))
        if legacy["error"]:
            self.stdout.write(self.style.ERROR(f"  Status: FAILED"))
            self.stdout.write(self.style.ERROR(f"  Error: {legacy['error']}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Status: SUCCESS"))
        self.stdout.write(f"  Solve time: {legacy['solve_time_ms']:.2f}ms")
        if legacy["metrics"]["total_slots"] > 0:
            self.stdout.write(
                f"  Slot fill: {legacy['metrics']['slot_fill_rate']:.1f}% ({legacy['metrics']['filled_slots']}/{legacy['metrics']['total_slots']})"
            )
            self.stdout.write(
                f"  Fairness (variance): {legacy['metrics']['fairness_variance']:.4f}"
            )
            self.stdout.write(
                f"  Unfilled slots: {legacy['metrics']['unfilled_slots']}"
            )

        # OR-Tools results
        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.HTTP_INFO("OR-TOOLS SCHEDULER:"))
        if ortools["error"]:
            self.stdout.write(self.style.ERROR(f"  Status: FAILED"))
            self.stdout.write(self.style.ERROR(f"  Error: {ortools['error']}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Status: SUCCESS"))
        self.stdout.write(f"  Solve time: {ortools['solve_time_ms']:.2f}ms")
        if ortools["metrics"]["total_slots"] > 0:
            self.stdout.write(
                f"  Slot fill: {ortools['metrics']['slot_fill_rate']:.1f}% ({ortools['metrics']['filled_slots']}/{ortools['metrics']['total_slots']})"
            )
            self.stdout.write(
                f"  Fairness (variance): {ortools['metrics']['fairness_variance']:.4f}"
            )
            self.stdout.write(
                f"  Unfilled slots: {ortools['metrics']['unfilled_slots']}"
            )

        # Comparison
        if comp["total_slots"] > 0:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.HTTP_INFO("DIFFERENCES:"))
            self.stdout.write(
                f"  Same assignments: {comp['same_assignments']}/{comp['total_slots']} ({comp['same_percentage']:.1f}%)"
            )
            self.stdout.write(
                f"  Different members: {comp['different_assignments']} slots"
            )

            if verbose and comp["slot_differences"]:
                self.stdout.write("\n  Slot-by-slot differences:")
                for diff in comp["slot_differences"][:20]:  # Limit to first 20
                    self.stdout.write(
                        f"    {diff['date']} {diff['role']}: Legacy={diff['legacy_member_id']} vs OR-Tools={diff['ortools_member_id']}"
                    )
                if len(comp["slot_differences"]) > 20:
                    self.stdout.write(
                        f"    ... and {len(comp['slot_differences']) - 20} more (use --verbose to see all)"
                    )

        # Quality verdict
        self.stdout.write("\n" + "=" * 70)
        if legacy["error"] and ortools["error"]:
            self.stdout.write(self.style.ERROR("VERDICT: Both schedulers failed"))
        elif legacy["error"]:
            self.stdout.write(self.style.WARNING("VERDICT: Only OR-Tools succeeded"))
        elif ortools["error"]:
            self.stdout.write(self.style.WARNING("VERDICT: Only legacy succeeded"))
        else:
            # Both succeeded - compare quality
            legacy_rate = legacy["metrics"]["slot_fill_rate"]
            ortools_rate = ortools["metrics"]["slot_fill_rate"]

            if abs(legacy_rate - ortools_rate) < 1.0:
                self.stdout.write(
                    self.style.SUCCESS(
                        "VERDICT: Both schedulers produce identical quality"
                    )
                )
            elif ortools_rate > legacy_rate:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"VERDICT: OR-Tools is better ({ortools_rate:.1f}% vs {legacy_rate:.1f}% fill rate)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"VERDICT: Legacy is better ({legacy_rate:.1f}% vs {ortools_rate:.1f}% fill rate)"
                    )
                )

        self.stdout.write("=" * 70 + "\n")
