import calendar
import logging
import random
import time
from collections import defaultdict
from datetime import date

from duty_roster.models import (
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
)
from duty_roster.operational_calendar import get_operational_weekend
from members.constants.membership import DEFAULT_ROLES
from members.models import Member
from siteconfig.models import SiteConfiguration

logger = logging.getLogger("duty_roster.generator")


# Cache for operational season boundaries
_operational_season_cache = {}


def clear_operational_season_cache():
    """Clear the operational season cache. Useful for testing."""
    global _operational_season_cache
    _operational_season_cache.clear()


def get_operational_season_bounds(year: int):
    """
    Get operational season boundaries for a given year with caching.

    Returns:
        Tuple of (season_start, season_end) or (None, None) if no config
    """
    cache_key = year
    if cache_key in _operational_season_cache:
        return _operational_season_cache[cache_key]

    try:
        config = SiteConfiguration.objects.first()
        if not config:
            result = (None, None)
            _operational_season_cache[cache_key] = result
            return result

        # Determine start and end dates if configured
        season_start = None
        season_end = None
        if config.operations_start_period:
            start_sat, start_sun = get_operational_weekend(
                year, config.operations_start_period
            )
            season_start = min(start_sat, start_sun)
        if config.operations_end_period:
            end_sat, end_sun = get_operational_weekend(
                year, config.operations_end_period
            )
            season_end = max(end_sat, end_sun)

        result = (season_start, season_end)
        _operational_season_cache[cache_key] = result
        return result

    except Exception as e:
        logger.warning(f"Error calculating operational season bounds for {year}: {e}")
        result = (None, None)
        _operational_season_cache[cache_key] = result
        return result


def is_within_operational_season(check_date: date) -> bool:
    """
    Check if a given date falls within the club's operational season.

    Args:
        check_date: The date to check

    Returns:
        True if the date is within the operational season, False otherwise
    """
    try:
        season_start, season_end = get_operational_season_bounds(check_date.year)

        # If neither is set, all dates are operational
        if not season_start and not season_end:
            return True
        # If only start is set, restrict to dates on/after start
        elif season_start and not season_end:
            return check_date >= season_start
        # If only end is set, restrict to dates on/before end
        elif season_end and not season_start:
            return check_date <= season_end
        # If both are set, restrict to dates between start and end
        else:
            # This must be the case where both are set (only remaining possibility)
            assert season_start is not None and season_end is not None
            return season_start <= check_date <= season_end

    except Exception as e:
        logger.warning(f"Error checking operational season for {check_date}: {e}")
        # If there's any error parsing, default to allowing the date
        return True


def calculate_role_scarcity(members, prefs, blackouts, weekend_dates, role):
    """
    Calculate scarcity score for a role based on actual availability.

    Lower score = more constrained = higher priority to assign first.

    Args:
        members: List of active Member objects
        prefs: Dict of member_id -> DutyPreference
        blackouts: Set of (member_id, date) tuples
        weekend_dates: List of date objects for the month
        role: Role name (e.g., 'towpilot', 'instructor')

    Returns:
        Dict with:
            - 'total_members': Total members with this role flag
            - 'avg_available_per_day': Average members available per day
            - 'scarcity_score': avg_available_per_day (lower = more critical)
            - 'availability_by_day': List of counts for each day
    """
    if not weekend_dates:
        return {
            "total_members": 0,
            "avg_available_per_day": 0,
            "scarcity_score": float("inf"),
            "availability_by_day": [],
        }

    # Count total members with this role
    total_with_role = sum(1 for m in members if getattr(m, role, False))

    # Count available members for each day
    availability_by_day = []
    for day in weekend_dates:
        available_count = 0
        for m in members:
            # Check if member has the role flag
            if not getattr(m, role, False):
                continue

            # Check DutyPreference constraints
            p = prefs.get(m.id)
            if p:
                # Member has preferences - check them
                if p.dont_schedule or p.scheduling_suspended:
                    continue
            # If no preference, treat as available (don't skip)

            # Check if blacked out on this day
            if (m.id, day) in blackouts:
                continue

            # Check role-specific percentage (skip if 0)
            # Only check percentages if member has DutyPreference
            if p:
                percent_fields = {
                    "instructor": "instructor_percent",
                    "duty_officer": "duty_officer_percent",
                    "assistant_duty_officer": "ado_percent",
                    "towpilot": "towpilot_percent",
                }

                # Get all eligible role fields for this member
                eligible_role_fields = [
                    field for r, field in percent_fields.items() if getattr(m, r, False)
                ]

                # Determine if percentage is blocking
                if len(eligible_role_fields) == 1:
                    # Only eligible for one role - if percent is 0, treat as 100
                    field = eligible_role_fields[0]
                    pct = getattr(p, field, 0)
                    if pct == 0:
                        pct = 100
                else:
                    # Multiple roles - check if all are zero
                    all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
                    if role == "assistant_duty_officer":
                        pct = p.ado_percent if not all_zero else 100
                    else:
                        pct = getattr(p, f"{role}_percent", 0) if not all_zero else 100

                if pct == 0:
                    continue  # Skip if percentage explicitly set to 0

            # Count member as available (either has good percentage or no preference)
            available_count += 1

        availability_by_day.append(available_count)

    avg_available = (
        sum(availability_by_day) / len(availability_by_day)
        if availability_by_day
        else 0
    )

    # Scarcity score: average available members per day
    # Lower score = fewer available = more constrained = should assign first
    scarcity_score = avg_available if len(weekend_dates) > 0 else float("inf")

    logger.debug(
        f"Role '{role}' scarcity: {total_with_role} total members, "
        f"{avg_available:.1f} avg available/day, "
        f"score={scarcity_score:.2f}"
    )

    return {
        "total_members": total_with_role,
        "avg_available_per_day": avg_available,
        "scarcity_score": scarcity_score,
        "availability_by_day": availability_by_day,
    }


def diagnose_empty_slot(
    role,
    day,
    members,
    prefs,
    blackouts,
    avoidances,
    assignments,
    assigned_today,
    last_assigned=None,
):
    """
    Diagnose why a role slot couldn't be filled on a specific day.

    Args:
        last_assigned: Optional dict of role -> member_id for previous day's assignments

    Returns dict with:
        - total_members_with_role: Total members who have the role flag
        - reasons: Dict of reason -> list of member names
        - summary: Human-readable summary string
    """
    DEFAULT_MAX_ASSIGNMENTS = 8

    reasons = {
        "no_preference": [],  # Note: These are now ELIGIBLE, just informational
        "dont_schedule": [],
        "scheduling_suspended": [],
        "blacked_out": [],
        "avoids_someone": [],
        "already_assigned_today": [],
        "percent_zero": [],
        "max_assignments_reached": [],
        "no_role_flag": [],
        "assigned_yesterday": [],  # Anti-repeat constraint
    }

    total_with_role = 0

    for m in members:
        # Check if member has the role flag
        has_role = getattr(m, role, False)
        if not has_role:
            continue

        total_with_role += 1

        # Check preference exists
        p = prefs.get(m.id)
        if not p:
            # Note: Members without preferences are now treated as eligible!
            # This is just for informational purposes in diagnostics
            reasons["no_preference"].append(
                f"{m.full_display_name} (treated as eligible with defaults)"
            )
            # Continue checking other constraints with defaults
            if (m.id, day) in blackouts:
                reasons["blacked_out"].append(m.full_display_name)
                continue
            avoids_someone = False
            for o in assigned_today:
                if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                    reasons["avoids_someone"].append(
                        f"{m.full_display_name} (avoids {o.full_display_name})"
                    )
                    avoids_someone = True
                    break
            if avoids_someone:
                continue
            if m in assigned_today:
                reasons["already_assigned_today"].append(m.full_display_name)
                continue
            # Check anti-repeat constraint
            if last_assigned and last_assigned.get(role) == m.id:
                reasons["assigned_yesterday"].append(
                    f"{m.full_display_name} (did this role yesterday)"
                )
                continue
            if assignments[m.id] >= DEFAULT_MAX_ASSIGNMENTS:
                reasons["max_assignments_reached"].append(
                    f"{m.full_display_name} ({assignments[m.id]}/{DEFAULT_MAX_ASSIGNMENTS})"
                )
                continue
            # If we get here, member with no preference is actually eligible!
            continue

        # Member has preferences - check them
        # Check don't schedule flag
        if p.dont_schedule:
            reasons["dont_schedule"].append(m.full_display_name)
            continue

        # Check scheduling suspended
        if p.scheduling_suspended:
            reasons["scheduling_suspended"].append(m.full_display_name)
            continue

        # Check blackout
        if (m.id, day) in blackouts:
            reasons["blacked_out"].append(m.full_display_name)
            continue

        # Check avoidances
        avoids_someone = False
        for o in assigned_today:
            if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                reasons["avoids_someone"].append(
                    f"{m.full_display_name} (avoids {o.full_display_name})"
                )
                avoids_someone = True
                break
        if avoids_someone:
            continue

        # Check already assigned today
        if m in assigned_today:
            reasons["already_assigned_today"].append(m.full_display_name)
            continue

        # Check anti-repeat constraint
        if last_assigned and last_assigned.get(role) == m.id:
            reasons["assigned_yesterday"].append(
                f"{m.full_display_name} (did this role yesterday)"
            )
            continue

        # Check percentage
        percent_fields = [
            ("instructor", "instructor_percent"),
            ("duty_officer", "duty_officer_percent"),
            ("assistant_duty_officer", "ado_percent"),
            ("towpilot", "towpilot_percent"),
        ]
        eligible_role_fields = [
            field for r, field in percent_fields if getattr(m, r, False)
        ]

        if len(eligible_role_fields) == 1:
            field = eligible_role_fields[0]
            pct = getattr(p, field, 0)
            if pct == 0:
                pct = 100  # Single role, treat 0 as 100
        else:
            all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
            if role == "assistant_duty_officer":
                pct = p.ado_percent if not all_zero else 100
            else:
                pct = getattr(p, f"{role}_percent", 0) if not all_zero else 100

        if pct == 0:
            reasons["percent_zero"].append(m.full_display_name)
            continue

        # Check max assignments
        if assignments[m.id] >= getattr(p, "max_assignments_per_month", 0):
            max_val = getattr(p, "max_assignments_per_month", 0)
            reasons["max_assignments_reached"].append(
                f"{m.full_display_name} ({assignments[m.id]}/{max_val})"
            )
            continue

    # Build human-readable summary
    # Note: "no_preference" is not included in summary because members without
    # preferences are treated as eligible (with default constraints). It's an
    # informational category, not a blocking reason.
    summary_parts = []
    if reasons["blacked_out"]:
        summary_parts.append(f"{len(reasons['blacked_out'])} blacked out")
    if reasons["already_assigned_today"]:
        summary_parts.append(
            f"{len(reasons['already_assigned_today'])} already assigned"
        )
    if reasons["assigned_yesterday"]:
        summary_parts.append(f"{len(reasons['assigned_yesterday'])} did role yesterday")
    if reasons["max_assignments_reached"]:
        summary_parts.append(
            f"{len(reasons['max_assignments_reached'])} at max assignments"
        )
    if reasons["scheduling_suspended"]:
        summary_parts.append(f"{len(reasons['scheduling_suspended'])} suspended")
    if reasons["dont_schedule"]:
        summary_parts.append(f"{len(reasons['dont_schedule'])} opted out")
    if reasons["percent_zero"]:
        summary_parts.append(f"{len(reasons['percent_zero'])} with 0% preference")
    if reasons["avoids_someone"]:
        summary_parts.append(f"{len(reasons['avoids_someone'])} avoiding co-workers")

    if not summary_parts:
        summary = f"No eligible members found for {role}"
    else:
        summary = f"No {role} available: " + ", ".join(summary_parts)

    return {
        "total_members_with_role": total_with_role,
        "reasons": reasons,
        "summary": summary,
    }


def _generate_roster_legacy(year=None, month=None, roles=None, exclude_dates=None):
    """
    Generate a duty roster for a given month using legacy weighted-random algorithm.

    DEPRECATED: This is the legacy greedy weighted-random scheduler. New code should
    use generate_roster() which routes to either this or OR-Tools based on feature flag.

    Args:
        year: Year to generate roster for (default: current year)
        month: Month to generate roster for (default: current month)
        roles: List of roles to schedule (default: DEFAULT_ROLES from constants)
        exclude_dates: Optional set/list of datetime.date objects to skip
            (e.g. dates the user has already removed from the proposed roster).

    Returns:
        List of dicts, each with:
            - 'date': a datetime.date for the duty day
            - 'slots': mapping of role name to assigned Member.id (or None if unfilled)
            - 'diagnostics': per-date scheduling diagnostics/metadata
    """
    from django.utils.timezone import now

    today = now().date()
    year = year or today.year
    month = month or today.month

    # Use provided roles or fall back to DEFAULT_ROLES
    roles_to_schedule = roles if roles is not None else DEFAULT_ROLES

    cal = calendar.Calendar()
    all_weekend_dates = [
        d
        for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() in (5, 6)
    ]

    # Filter weekend dates to only include those within operational season
    weekend_dates = [d for d in all_weekend_dates if is_within_operational_season(d)]

    # Log what dates were filtered out for debugging
    filtered_out = [d for d in all_weekend_dates if d not in weekend_dates]
    if filtered_out:
        logger.info(
            f"Filtered out {len(filtered_out)} weekend dates outside operational season: {filtered_out}"
        )

    # Exclude dates the user has already removed from the proposed roster
    if exclude_dates:
        exclude_set = set(exclude_dates)
        before_count = len(weekend_dates)
        weekend_dates = [d for d in weekend_dates if d not in exclude_set]
        excluded_count = before_count - len(weekend_dates)
        if excluded_count:
            logger.info(
                f"Excluded {excluded_count} user-removed dates from roster generation: "
                f"{sorted(exclude_set)}"
            )
    members = list(Member.objects.filter(is_active=True))
    prefs = {
        p.member_id: p for p in DutyPreference.objects.select_related("member").all()
    }
    avoidances = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
    pairings = defaultdict(set)
    for p in DutyPairing.objects.all():
        pairings[p.member_id].add(p.pair_with_id)
    blackouts = {
        (b.member_id, b.date)
        for b in MemberBlackout.objects.filter(date__year=year, date__month=month)
    }
    assignments = defaultdict(int)

    def last_key(m):
        p = prefs.get(m.id)
        d = getattr(p, "last_duty_date", None)
        return d or date(1900, 1, 1)

    def eligible(role, m, day, assigned):
        # Default values for members without DutyPreference
        DEFAULT_MAX_ASSIGNMENTS = 8

        p = prefs.get(m.id)
        if not p:
            # Member has no preference set - treat as eligible with defaults
            logger.debug(
                f"{m.full_display_name}: No DutyPreference found, using defaults (schedulable, 100% available)."
            )
            # Still check basic constraints even without preference
            if (m.id, day) in blackouts:
                logger.debug(f"{m.full_display_name}: Blacked out on {day}.")
                return False
            for o in assigned:
                if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                    logger.debug(
                        f"{m.full_display_name}: Avoids {o.full_display_name}."
                    )
                    return False
            if m in assigned:
                logger.debug(f"{m.full_display_name}: Already assigned today.")
                return False
            flag = getattr(m, role, False)
            if not flag:
                logger.debug(
                    f"{m.full_display_name}: Not eligible for role {role} (flag is False)."
                )
                return False
            if assignments[m.id] >= DEFAULT_MAX_ASSIGNMENTS:
                logger.debug(
                    f"{m.full_display_name}: Max assignments per month reached (using default {DEFAULT_MAX_ASSIGNMENTS})."
                )
                return False
            logger.debug(
                f"{m.full_display_name}: Eligible for {role} on {day} (no pref, treating as 100%)."
            )
            return True

        # Member has preferences - check them
        if p.dont_schedule:
            logger.debug(f"{m.full_display_name}: 'Don't schedule' is set.")
            return False
        if p.scheduling_suspended:
            logger.debug(f"{m.full_display_name}: Scheduling suspended.")
            return False
        if (m.id, day) in blackouts:
            logger.debug(f"{m.full_display_name}: Blacked out on {day}.")
            return False
        for o in assigned:
            if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                logger.debug(f"{m.full_display_name}: Avoids {o.full_display_name}.")
                return False
        if m in assigned:
            logger.debug(f"{m.full_display_name}: Already assigned today.")
            return False
        flag = getattr(m, role, False)
        percent_fields = [
            ("instructor", "instructor_percent"),
            ("duty_officer", "duty_officer_percent"),
            ("assistant_duty_officer", "ado_percent"),
            ("towpilot", "towpilot_percent"),
        ]
        eligible_role_fields = [
            field for r, field in percent_fields if getattr(m, r, False)
        ]
        if len(eligible_role_fields) == 1:
            field = eligible_role_fields[0]
            pct = getattr(p, field, 0)
            if pct == 0:
                logger.debug(
                    f"{m.full_display_name}: Only eligible for {role}, percent is 0, treating as 100%."
                )
                pct = 100
        else:
            all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
            if role == "assistant_duty_officer":
                pct = p.ado_percent if not all_zero else 100
            else:
                pct = getattr(p, f"{role}_percent", 0) if not all_zero else 100
            if all_zero:
                logger.debug(
                    f"{m.full_display_name}: All eligible role percents are zero, treating {role} as 100%."
                )
        if not flag:
            logger.debug(
                f"{m.full_display_name}: Not eligible for role {role} (flag is False)."
            )
            return False
        if pct == 0:
            logger.debug(f"{m.full_display_name}: {role} percent is 0.")
            return False
        if assignments[m.id] >= getattr(p, "max_assignments_per_month", 0):
            logger.debug(f"{m.full_display_name}: Max assignments per month reached.")
            return False
        logger.debug(
            f"{m.full_display_name}: Eligible for {role} on {day} (pct={pct})."
        )
        return True

    def choose(cands, role, assigned):
        weights = []
        for m in cands:
            p = prefs.get(m.id)
            percent_fields = [
                ("instructor", "instructor_percent"),
                ("duty_officer", "duty_officer_percent"),
                ("assistant_duty_officer", "ado_percent"),
                ("towpilot", "towpilot_percent"),
            ]
            eligible_role_fields = [
                field for r, field in percent_fields if getattr(m, r, False)
            ]
            if not p:
                # Member has no preference - treat as 100% available
                base = 100
            elif len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                base = getattr(p, field, 0)
                if base == 0:
                    base = 100
            else:
                all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
                if role == "assistant_duty_officer":
                    base = getattr(p, "ado_percent", 0) if not all_zero else 100
                else:
                    base = getattr(p, f"{role}_percent", 0) if not all_zero else 100
            w = base
            for o in assigned:
                if o.id in pairings.get(m.id, set()) or m.id in pairings.get(
                    o.id, set()
                ):
                    w *= 3
                    break
            logger.debug(
                f"Candidate: {m.full_display_name}, base weight: {base}, final weight: {w}"
            )
            weights.append(w)
        if not weights or sum(weights) == 0:
            logger.debug(f"No candidates with nonzero weights for role {role}.")
            return None
        chosen = random.choices(cands, weights=weights, k=1)[0]
        logger.debug(
            f"Chose {chosen.full_display_name} for role {role} from {[m.full_display_name for m in cands]}"
        )
        return chosen

    # Calculate role scarcity and prioritize most constrained roles first
    role_scarcity = {}
    for role in roles_to_schedule:
        scarcity_data = calculate_role_scarcity(
            members, prefs, blackouts, weekend_dates, role
        )
        role_scarcity[role] = scarcity_data

    # Sort roles by scarcity score (lowest = most constrained = highest priority)
    prioritized_roles = sorted(
        roles_to_schedule, key=lambda r: role_scarcity[r]["scarcity_score"]
    )

    logger.debug(
        f"Role assignment priority order (most constrained first): {prioritized_roles}"
    )
    for role in prioritized_roles:
        data = role_scarcity[role]
        logger.debug(
            f"  {role}: {data['total_members']} members, "
            f"{data['avg_available_per_day']:.1f} avg available/day, "
            f"score={data['scarcity_score']:.2f}"
        )

    schedule = []
    last_assigned = {role: None for role in roles_to_schedule}
    for day in weekend_dates:
        assigned_today = set()
        slots = {}
        diagnostics = {}
        for role in prioritized_roles:
            cands = [
                m
                for m in members
                if eligible(role, m, day, assigned_today)
                and m.id != last_assigned.get(role)
            ]
            cands.sort(key=last_key)
            sel = choose(cands, role, assigned_today)
            if sel:
                assigned_today.add(sel)
                assignments[sel.id] += 1
                slots[role] = sel.id
                diagnostics[role] = None  # No diagnostic needed for filled slots
            else:
                slots[role] = None
                # Generate diagnostic for empty slot
                diagnostics[role] = diagnose_empty_slot(
                    role,
                    day,
                    members,
                    prefs,
                    blackouts,
                    avoidances,
                    assignments,
                    assigned_today,
                    last_assigned,
                )
        schedule.append({"date": day, "slots": slots, "diagnostics": diagnostics})
        last_assigned = slots.copy()
    return schedule


def generate_roster(year=None, month=None, roles=None, exclude_dates=None):
    """
    Generate duty roster using configured scheduler (OR-Tools or legacy).

    This is the main entry point for duty roster generation. It checks the
    SiteConfiguration feature flag to determine which scheduler to use:
    - If use_ortools_scheduler=True: Use OR-Tools constraint programming solver
    - If use_ortools_scheduler=False: Use legacy weighted-random algorithm

    If OR-Tools scheduler is enabled but fails, automatically falls back to legacy
    algorithm and logs the error for investigation.

    Args:
        year: Year to generate roster for (default: current year)
        month: Month to generate roster for (default: current month)
        roles: List of roles to schedule (default: DEFAULT_ROLES from constants)
        exclude_dates: Optional set/list of datetime.date objects to skip
            (e.g. dates the user has already removed from the proposed roster).

    Returns:
        List of dicts, each with:
            - 'date': a datetime.date for the duty day
            - 'slots': mapping of role name to assigned Member ID (or None if unfilled)
            - 'diagnostics': per-date scheduling diagnostics/metadata
    """
    # Normalize parameters to avoid None values in telemetry/logging
    from django.utils.timezone import now

    today = now().date()
    year = year or today.year
    month = month or today.month
    roles = roles if roles is not None else DEFAULT_ROLES
    exclude_dates = exclude_dates or set()

    # Check feature flag
    try:
        config = SiteConfiguration.objects.first()
        use_ortools = config.use_ortools_scheduler if config else False
    except Exception as e:
        logger.warning(
            f"Failed to read SiteConfiguration, defaulting to legacy scheduler: {e}",
            exc_info=True,
        )
        use_ortools = False

    if use_ortools:
        try:
            logger.info(
                "Using OR-Tools constraint programming scheduler",
                extra={"year": year, "month": month, "roles": roles},
            )
            start_time = time.perf_counter()

            from duty_roster.ortools_scheduler import generate_roster_ortools

            schedule = generate_roster_ortools(year, month, roles, exclude_dates)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"OR-Tools scheduler completed successfully",
                extra={
                    "solve_time_ms": round(elapsed_ms, 2),
                    "year": year,
                    "month": month,
                    "num_days": len(schedule),
                    "scheduler": "ortools",
                },
            )
            return schedule

        except Exception as e:
            logger.error(
                f"OR-Tools scheduler failed, falling back to legacy algorithm: {e}",
                extra={"year": year, "month": month, "error": str(e)},
                exc_info=True,
            )
            # Fall through to legacy scheduler

    # Use legacy scheduler
    logger.info(
        "Using legacy weighted-random scheduler",
        extra={"year": year, "month": month, "roles": roles, "scheduler": "legacy"},
    )
    start_time = time.perf_counter()

    schedule = _generate_roster_legacy(year, month, roles, exclude_dates)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"Legacy scheduler completed successfully",
        extra={
            "solve_time_ms": round(elapsed_ms, 2),
            "year": year,
            "month": month,
            "num_days": len(schedule),
            "scheduler": "legacy",
        },
    )
    return schedule


def generate_roster_legacy(year=None, month=None, roles=None, exclude_dates=None):
    """
    Generate duty roster using legacy weighted-random algorithm.

    This is a public wrapper for the legacy scheduler, intended for:
    - Comparison scripts that need to explicitly test legacy algorithm
    - Diagnostic/debugging tools
    - Migration/testing scenarios

    For normal roster generation, use generate_roster() which respects the
    feature flag and provides automatic fallback.

    Args:
        year: Year to generate roster for (default: current year)
        month: Month to generate roster for (default: current month)
        roles: List of roles to schedule (default: DEFAULT_ROLES from constants)
        exclude_dates: Optional set/list of datetime.date objects to skip

    Returns:
        List of dicts, each with 'date', 'slots', and 'diagnostics'
    """
    return _generate_roster_legacy(year, month, roles, exclude_dates)
