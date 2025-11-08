# --- IMPORTS ---
from collections import defaultdict
from datetime import date, timedelta
from itertools import chain
from typing import Any, Dict, List, TypedDict

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, DurationField, F, Max, Q, Sum
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce, ExtractWeekDay, ExtractYear

from logsheet.models import Flight


def instructor_schedule_vs_actual(
    start_date: date, end_date: date, *, finalized_only=True, top_n=20, min_total=1
) -> Dict[str, Any]:
    """
    For each instructor:
      - blue: unique days scheduled as duty instructor (from submitted Logsheets)
      - burnt orange: unique days with at least one instructional flight (Flight.instructor) when NOT scheduled as duty instructor
    Returns sorted Y axis (most total days at top), and two lists per instructor: scheduled_days, unscheduled_days
    """
    from logsheet.models import Logsheet

    # 1. Get all scheduled instructor days (from submitted logsheets)
    logsheet_qs = Logsheet.objects.filter(
        log_date__gte=start_date, log_date__lte=end_date
    )
    if finalized_only:
        logsheet_qs = logsheet_qs.filter(finalized=True)
    scheduled_days = defaultdict(set)
    for ls in logsheet_qs:
        if ls.duty_instructor_id:
            scheduled_days[ls.duty_instructor_id].add(ls.log_date)
        if ls.surge_instructor_id:
            scheduled_days[ls.surge_instructor_id].add(ls.log_date)

    # 2. Get all actual instructor days (from flights)
    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)
    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, instructor__isnull=False
    )
    # Map: instructor_id -> set of days they instructed
    actual_days = defaultdict(set)
    for row in qs.values("instructor_id", "ops_date").distinct():
        if row["instructor_id"]:
            actual_days[row["instructor_id"]].add(row["ops_date"])

    # Find instructors who also towed during the period
    tow_qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        tow_qs = tow_qs.filter(FINALIZED_ONLY)
    tow_qs = tow_qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, tow_pilot__isnull=False
    )
    tow_counts = defaultdict(int)
    for row in tow_qs.values("tow_pilot_id").annotate(n=Count("id")):
        if row["tow_pilot_id"]:
            tow_counts[row["tow_pilot_id"]] += row["n"]

    # 3. For each instructor, count scheduled and unscheduled days
    all_ids = set(scheduled_days.keys()) | set(actual_days.keys())
    data = []
    italicize = []
    name_map = _display_name_map(list(all_ids))
    for pid in all_ids:
        sched = scheduled_days.get(pid, set())
        actual = actual_days.get(pid, set())
        unsched = actual - sched
        name = name_map.get(pid, str(pid))
        data.append((pid, name, len(sched), len(unsched)))
        italicize.append(tow_counts.get(pid, 0) > 0)

    # Sort by total (scheduled+unscheduled) desc, then name
    data = sorted(
        zip(data, italicize), key=lambda t: (-(t[0][2] + t[0][3]), t[0][1].lower())
    )[:top_n]
    names = [t[0][1] for t in data]
    scheduled = [t[0][2] for t in data]
    unscheduled = [t[0][3] for t in data]
    italicize = [t[1] for t in data]

    return {
        "names": names,
        "scheduled": scheduled,  # blue
        "unscheduled": unscheduled,  # burnt orange
        "labels": ["Scheduled", "Unscheduled"],
        "italicize": italicize,
    }


def tow_pilot_schedule_vs_actual(
    start_date: date, end_date: date, *, finalized_only=True, top_n=20, min_total=1
) -> Dict[str, Any]:
    """
    For each tow pilot:
      - blue: unique days scheduled as duty tow pilot (from submitted Logsheets, not DutyAssignment)
      - burnt orange: unique days with at least one tow (Flight) when NOT scheduled as duty tow pilot
    Returns sorted Y axis (most total days at top), and two lists per pilot: scheduled_days, unscheduled_days
    """
    # 1. Get all scheduled tow pilot days (from submitted logsheets)
    from logsheet.models import Logsheet

    logsheet_qs = Logsheet.objects.filter(
        log_date__gte=start_date, log_date__lte=end_date
    )
    if finalized_only:
        logsheet_qs = logsheet_qs.filter(finalized=True)
    scheduled_days = defaultdict(set)
    for ls in logsheet_qs:
        if ls.tow_pilot_id:
            scheduled_days[ls.tow_pilot_id].add(ls.log_date)
        if ls.surge_tow_pilot_id:
            scheduled_days[ls.surge_tow_pilot_id].add(ls.log_date)

    # 2. Get all actual tow pilot days (from flights)
    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)
    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, tow_pilot__isnull=False
    )
    # Map: tow_pilot_id -> set of days they towed
    actual_days = defaultdict(set)
    for row in qs.values("tow_pilot_id", "ops_date").distinct():
        if row["tow_pilot_id"]:
            actual_days[row["tow_pilot_id"]].add(row["ops_date"])

    # Find tow pilots who also instructed during the period
    inst_qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        inst_qs = inst_qs.filter(FINALIZED_ONLY)
    inst_qs = inst_qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, instructor__isnull=False
    )
    inst_counts = defaultdict(int)
    for row in inst_qs.values("instructor_id").annotate(n=Count("id")):
        if row["instructor_id"]:
            inst_counts[row["instructor_id"]] += row["n"]

    # 3. For each tow pilot, count scheduled and unscheduled days
    all_ids = set(scheduled_days.keys()) | set(actual_days.keys())
    data = []
    italicize = []
    name_map = _display_name_map(list(all_ids))
    for pid in all_ids:
        sched = scheduled_days.get(pid, set())
        actual = actual_days.get(pid, set())
        unsched = actual - sched
        name = name_map.get(pid, str(pid))
        data.append((pid, name, len(sched), len(unsched)))
        italicize.append(inst_counts.get(pid, 0) > 0)

    # Sort by total (scheduled+unscheduled) desc, then name
    data = sorted(
        zip(data, italicize), key=lambda t: (-(t[0][2] + t[0][3]), t[0][1].lower())
    )[:top_n]
    names = [t[0][1] for t in data]
    scheduled = [t[0][2] for t in data]
    unscheduled = [t[0][3] for t in data]
    italicize = [t[1] for t in data]

    return {
        "names": names,
        "scheduled": scheduled,  # blue
        "unscheduled": unscheduled,  # burnt orange
        "labels": ["Scheduled", "Unscheduled"],
        "italicize": italicize,
    }


FINALIZED_ONLY = Q(logsheet__finalized=True)
LANDED_ONLY = Q(landing_time__isnull=False) & Q(launch_time__isnull=False)
__all__ = ["cumulative_flights_by_year"]


def combined_duty_days_vs_actual(
    start_date: date, end_date: date, *, finalized_only=True, top_n=20, min_total=1
) -> Dict[str, Any]:
    """
    For each member:
      - Count unique days they did any duty (tow or instruct), not double-counting days when both.
      - Flag dual-role members (did both at least once in period).
    Returns sorted Y axis (most total days at top), and list per member: total duty days.
    """
    from logsheet.models import Logsheet

    # 1. Get all scheduled tow pilot and instructor days (from submitted logsheets)
    logsheet_qs = Logsheet.objects.filter(
        log_date__gte=start_date, log_date__lte=end_date
    )
    if finalized_only:
        logsheet_qs = logsheet_qs.filter(finalized=True)
    scheduled_by_member = defaultdict(set)
    for ls in logsheet_qs:
        for pid in [
            ls.tow_pilot_id,
            ls.surge_tow_pilot_id,
            ls.duty_instructor_id,
            ls.surge_instructor_id,
        ]:
            if pid:
                scheduled_by_member[pid].add(ls.log_date)

    # 2. Get all actual tow pilot and instructor days (from flights)
    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)
    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date
    )
    actual_by_member = defaultdict(set)
    for row in qs.values("tow_pilot_id", "instructor_id", "ops_date").distinct():
        for pid in [row["tow_pilot_id"], row["instructor_id"]]:
            if pid:
                actual_by_member[pid].add(row["ops_date"])

    # 3. For each member, count tow pilot and instructor days (no double-counting per day)
    all_ids = set(scheduled_by_member.keys()) | set(actual_by_member.keys())
    tow_days = defaultdict(set)
    inst_days = defaultdict(set)
    for row in qs.values("tow_pilot_id", "instructor_id", "ops_date").distinct():
        if row["tow_pilot_id"]:
            tow_days[row["tow_pilot_id"]].add(row["ops_date"])
        if row["instructor_id"]:
            inst_days[row["instructor_id"]].add(row["ops_date"])

    # Also include scheduled days from logsheets
    for ls in logsheet_qs:
        if ls.tow_pilot_id:
            tow_days[ls.tow_pilot_id].add(ls.log_date)
        if ls.surge_tow_pilot_id:
            tow_days[ls.surge_tow_pilot_id].add(ls.log_date)
        if ls.duty_instructor_id:
            inst_days[ls.duty_instructor_id].add(ls.log_date)
        if ls.surge_instructor_id:
            inst_days[ls.surge_instructor_id].add(ls.log_date)

    # For each member, count unique tow and instructor days
    name_map = _display_name_map(list(all_ids))
    data = []
    dual_role_flags = []
    for pid in all_ids:
        name = name_map.get(pid, str(pid))
        tow = tow_days.get(pid, set())
        inst = inst_days.get(pid, set())
        # Days where member did both roles
        both = tow & inst
        tow_only = tow - both
        inst_only = inst - both
        tow_count = len(tow_only)
        inst_count = len(inst_only)
        both_count = len(both)
        total = tow_count + inst_count + both_count
        # Only include members who have both tow and instructor days
        if (tow_count > 0 and inst_count > 0) or both_count > 0:
            if total >= min_total:
                data.append((pid, name, tow_count, inst_count, both_count))
                dual_role_flags.append(True)

    # Sort by total duty days desc, then name
    data = sorted(
        zip(data, dual_role_flags),
        key=lambda t: (-(t[0][2] + t[0][3] + t[0][4]), t[0][1].lower()),
    )[:top_n]
    names = [t[0][1] for t in data]
    tow_days_list = [t[0][2] for t in data]
    inst_days_list = [t[0][3] for t in data]
    both_days_list = [t[0][4] for t in data]
    dual_role = [t[1] for t in data]

    return {
        "names": names,
        "tow_days": tow_days_list,  # blue
        "inst_days": inst_days_list,  # burnt orange
        "both_days": both_days_list,  # days did both roles
        "labels": ["Tow Pilot Days", "Instructor Days", "Both Roles"],
        "dual_role": dual_role,
    }


def cumulative_flights_by_year(
    start_year=None, end_year=None, max_years=15, finalized_only=True
):
    today = date.today()
    if end_year is None:
        end_year = today.year
    if start_year is None:
        start_year = max(2000, end_year - max_years + 1)

    # Base queryset: landed flights within year range
    qs = Flight.objects.filter(LANDED_ONLY)

    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    # ✅ Alias the related field and its year using the correct field name
    qs = qs.annotate(ops_date=F("logsheet__log_date"))
    qs = qs.annotate(ops_year=ExtractYear("ops_date"))
    qs = qs.filter(ops_year__gte=start_year, ops_year__lte=end_year)

    # Per (year, day-of-year) counts using SQLite-compatible approach
    # Group by date and year, then calculate day of year in Python
    per_day_raw = (
        qs.values("ops_year", "ops_date")
        .annotate(n=Count("id"))
        .order_by("ops_year", "ops_date")
    )

    # Convert to the format expected by the rest of the function
    per_day = []
    for row in per_day_raw:
        year = row["ops_year"]
        date_obj = row["ops_date"]
        # Python built-in day of year calculation
        day_of_year = date_obj.timetuple().tm_yday
        per_day.append({"y": year, "d": day_of_year, "n": row["n"]})

    # Totals per year
    totals_qs = qs.values("ops_year").annotate(n=Count("id"))
    totals = {row["ops_year"]: row["n"] for row in totals_qs}

    # Ops days per year
    ops_days = {}
    for row in per_day:
        ops_days[row["y"]] = ops_days.get(row["y"], 0) + 1

    # Instructional flights per year
    instr_qs = (
        qs.filter(instructor__isnull=False).values("ops_year").annotate(n=Count("id"))
    )
    instr_counts = {row["ops_year"]: row["n"] for row in instr_qs}

    # Build cumulative arrays (1..365)
    labels = list(range(1, 366))
    data = {y: [0] * 365 for y in range(start_year, end_year + 1)}
    tmp = {}

    for row in per_day:
        y, d, n = row["y"], row["d"], row["n"]
        if 1 <= d <= 365:
            tmp.setdefault(y, {})
            tmp[y][d] = tmp[y].get(d, 0) + n

    for y in range(start_year, end_year + 1):
        running = 0
        arr = data[y]
        daymap = tmp.get(y, {})
        for d in range(1, 366):
            running += daymap.get(d, 0)
            arr[d - 1] = running

    years = [y for y in range(start_year, end_year + 1) if totals.get(y, 0) > 0]
    return {
        "labels": labels,
        "years": years,
        "data": data,
        "totals": totals,
        "ops_days": ops_days,
        "instr_counts": instr_counts,
    }


def flights_by_year_by_aircraft(
    start_year: int, end_year: int, *, finalized_only=True, top_n=10
):
    # Pivot data for a stacked bar:
    #  {
    #    "years": [2015, ...],
    #    "categories": ["N341KS","N321K","GROB 103","Private","Other",...],
    #    "matrix": {category: [counts aligned to years]},
    #    "totals_by_cat": {category: total across all years},
    #  }
    # Buckets non-club ships (glider.club_owned == False) into "Private".
    # Low-volume ships beyond top_n are grouped under "Other".

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = qs.annotate(
        ops_date=F("logsheet__log_date"),
        ops_year=ExtractYear("ops_date"),
    ).filter(
        ops_year__gte=start_year,
        ops_year__lte=end_year,
    )

    rows = (
        qs.values(
            "ops_year",
            "glider_id",
            "glider__club_owned",
            "glider__competition_number",
            "glider__n_number",
            "glider__model",
            "glider__make",
        )
        .annotate(n=Count("id"))
        .order_by("ops_year")
    )

    def label_from_row(r):
        # Prefer competition number or N-number; fall back to model/make
        ident = (
            (r.get("glider__competition_number") or "").strip().upper()
            or (r.get("glider__n_number") or "").strip().upper()
            or " ".join(
                [p for p in [r.get("glider__make"), r.get("glider__model")] if p]
            )
            or "Unknown"
        )
        # Bucket to Private if not club-owned
        is_club = r.get("glider__club_owned")
        if is_club is False:
            return "Private"
        return ident

    # Build pivot {year: {category: count}} and totals per category
    year_set, cat_counts, pivot = set(), {}, {}
    for r in rows:
        y = r["ops_year"]
        year_set.add(y)
        cat = label_from_row(r)
        pivot.setdefault(y, {}).setdefault(cat, 0)
        pivot[y][cat] += r["n"]
        cat_counts[cat] = cat_counts.get(cat, 0) + r["n"]

    years = sorted(year_set)
    if not years:
        return {"years": [], "categories": [], "matrix": {}, "totals_by_cat": {}}

    # Top-N categories by total (excluding "Private" which we append explicitly if present)
    have_private = "Private" in cat_counts
    sorted_cats = sorted(
        [c for c in cat_counts if c != "Private"], key=lambda c: (-cat_counts[c], c)
    )
    head = sorted_cats[:top_n]
    others = sorted_cats[top_n:]

    categories = head[:]
    if have_private:
        categories.append("Private")
    if others:
        categories.append("Other")

    # Matrix aligned to years
    matrix = {c: [0] * len(years) for c in categories}
    for i, y in enumerate(years):
        year_row = pivot.get(y, {})
        for c in head:
            matrix[c][i] = int(year_row.get(c, 0))
        if have_private:
            matrix["Private"][i] = int(year_row.get("Private", 0))
        if others:
            other_sum = sum(
                int(v) for k, v in year_row.items() if k not in set(head) | {"Private"}
            )
            matrix["Other"][i] = other_sum

    totals_by_cat = {c: sum(vals) for c, vals in matrix.items()}
    return {
        "years": years,
        "categories": categories,
        "matrix": matrix,
        "totals_by_cat": totals_by_cat,
    }


class GliderUtilization(TypedDict):
    names: List[str]  # labels in display order
    flights: List[int]  # flights per name
    hours: List[float]  # total hours per name
    avg_minutes: List[int]  # avg minutes per flight per name
    start: str
    end: str


def glider_utilization(
    start_date: date,
    end_date: date,
    *,
    finalized_only: bool = True,
    top_n: int = 12,
    fleet: str = "all",  # "all" | "club" | "private"
    # True → non-club into "Private"; False → list individually
    bucket_private: bool = True,
    include_unknown: bool = True,  # include flights with null glider as "Unknown"
) -> GliderUtilization:
    # Flights / total hours / avg minutes per glider in a date range.

    # - fleet="all": club ships shown individually; non-club can be bucketed as "Private".
    # - fleet="club": include only glider.club_owned=True.
    # - fleet="private": include only glider.club_owned=False (and include_unknown controls nulls).

    # - When bucket_private=False, private ships are listed individually (no "Private" bucket).
    # - Ships beyond top_n (by flights) grouped as "Other".

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    # Date filtering + duration choice
    qs = (
        qs.annotate(
            ops_date=F("logsheet__log_date"),
            dur_diff=ExpressionWrapper(
                F("landing_time") - F("launch_time"), output_field=DurationField()
            ),
        )
        .annotate(
            dur=Coalesce(F("duration"), F("dur_diff")),
        )
        .filter(
            ops_date__gte=start_date,
            ops_date__lte=end_date,
        )
    )

    # Fleet filter
    if fleet == "club":
        qs = qs.filter(glider__club_owned=True)
    elif fleet == "private":
        qs = qs.filter(glider__club_owned=False)
        if not include_unknown:
            qs = qs.filter(glider__isnull=False)

    rows = (
        qs.values(
            "glider_id",
            "glider__club_owned",
            "glider__competition_number",
            "glider__n_number",
            "glider__make",
            "glider__model",
        )
        .annotate(
            flights=Count("id"),
            total_dur=Sum("dur"),
            avg_dur=Avg("dur"),
        )
        .order_by()
    )

    def label_from_row(r: Dict[str, Any]) -> str:
        # Unknown (null glider)
        if r["glider_id"] is None:
            return "Unknown"
        # Non-club → either bucket or identify individually
        if r.get("glider__club_owned") is False and bucket_private:
            return "Private"
        # Build an identifier (comp # → N-number → Make/Model)
        ident = (r.get("glider__competition_number") or "").strip().upper()
        if not ident:
            ident = (r.get("glider__n_number") or "").strip().upper()
        if not ident:
            make = (r.get("glider__make") or "").strip()
            model = (r.get("glider__model") or "").strip()
            ident = " ".join(p for p in (make, model) if p) or "Unknown"
        return ident

    # Aggregate into a label→metrics map
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        lab = label_from_row(r)
        if lab == "Unknown" and not include_unknown:
            continue
        a = agg.setdefault(lab, {"flights": 0, "seconds": 0.0})
        a["flights"] += int(r["flights"] or 0)
        if r["total_dur"] is not None:
            a["seconds"] += float(r["total_dur"].total_seconds())

    if not agg:
        return {
            "names": [],
            "flights": [],
            "hours": [],
            "avg_minutes": [],
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        }

    # Split special buckets and rank others by flights
    special = set()
    if bucket_private:
        special.add("Private")
    if include_unknown:
        special.add("Unknown")

    specials_present = [k for k in special if k in agg]
    normal = [k for k in agg.keys() if k not in special]
    normal.sort(key=lambda k: (-agg[k]["flights"], k))

    head = normal[:top_n]
    tail = normal[top_n:]

    names: List[str] = head[:]
    # Keep specials at the end in a consistent order
    for s in ("Private", "Unknown"):
        if s in specials_present:
            names.append(s)
    if tail:
        names.append("Other")

    def calc_series_for(name: str) -> Dict[str, float]:
        if name != "Other":
            d = agg.get(name, {"flights": 0, "seconds": 0.0})
            flights = int(d["flights"])
            hours = d["seconds"] / 3600.0
            avg_min = int(round((d["seconds"] / 60.0 / flights), 0)) if flights else 0
            return {"flights": flights, "hours": hours, "avg_min": avg_min}
        # "Other" sums the tail
        flights = sum(int(agg[k]["flights"]) for k in tail)
        seconds = sum(float(agg[k]["seconds"]) for k in tail)
        hours = seconds / 3600.0
        avg_min = int(round((seconds / 60.0 / flights), 0)) if flights else 0
        return {"flights": flights, "hours": hours, "avg_min": avg_min}

    flights = []
    hours = []
    avg_minutes = []
    for n in names:
        s = calc_series_for(n)
        flights.append(s["flights"])
        hours.append(round(s["hours"], 1))
        avg_minutes.append(int(s["avg_min"]))

    return {
        "names": names,
        "flights": flights,
        "hours": hours,
        "avg_minutes": avg_minutes,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }


def _display_name_map(ids: List[int]) -> Dict[int, str]:
    """
    Return {user_id: display_name} using:
    - user.full_display_name if present
    - else get_full_name()
    - else username
    """
    User = get_user_model()
    users = User.objects.filter(id__in=ids)

    out: Dict[int, str] = {}
    for u in users:
        uid = int(getattr(u, "pk"))  # use pk instead of id (Pylance-safe)

        disp = getattr(u, "full_display_name", None)
        if not disp:
            full = (getattr(u, "get_full_name", lambda: "")() or "").strip()
            disp = full if full else getattr(u, "get_username", lambda: "")()

        out[uid] = str(disp)
    return out


# 1) Flying days by member (any role)
def flying_days_by_member(
    start_date: date,
    end_date: date,
    *,
    finalized_only: bool = True,
    min_days: int = 2,
) -> Dict[str, Any]:
    """
    Count distinct ops days per member where they flew as pilot OR instructor OR tow pilot.
    Returns { "names": [...], "days": [...], "ops_days_total": int }
    """
    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date
    )

    # Pull distinct (member_id, ops_date) pairs per role
    pilot_pairs = (
        qs.filter(pilot__isnull=False).values_list("pilot_id", "ops_date").distinct()
    )
    instr_pairs = (
        qs.filter(instructor__isnull=False)
        .values_list("instructor_id", "ops_date")
        .distinct()
    )
    tow_pairs = (
        qs.filter(tow_pilot__isnull=False)
        .values_list("tow_pilot_id", "ops_date")
        .distinct()
    )

    # Union in Python and count distinct days per member
    days_by_member: Dict[int, set] = defaultdict(set)
    for mid, d in chain(pilot_pairs, instr_pairs, tow_pairs):
        if mid is not None and d is not None:
            days_by_member[int(mid)].add(d)

    # Filter by threshold and sort desc by days, then by username
    ids = [m for m, s in days_by_member.items() if len(s) >= min_days]
    if not ids:
        return {
            "names": [],
            "days": [],
            "ops_days_total": int(qs.values("ops_date").distinct().count()),
        }

    # Map IDs -> usernames once
    User = get_user_model()
    # uses full_display_name → full_name → username
    name_map = _display_name_map(ids)

    rows: List[tuple] = []
    for m in ids:
        nm = name_map.get(m)
        if nm:
            rows.append((nm, len(days_by_member[m])))

    # sort by days desc, then name asc
    rows.sort(key=lambda t: (-t[1], t[0]))

    names = [t[0] for t in rows]
    days = [int(t[1]) for t in rows]

    ops_days_total = int(qs.values("ops_date").distinct().count())
    return {"names": names, "days": days, "ops_days_total": ops_days_total}


# 2) Flight duration distribution (CDF) for glider flights
def flight_duration_distribution(
    start_date: date, end_date: date, *, finalized_only=True, max_points=400
) -> Dict[str, Any]:
    """
    Survival curve of flight durations: percent of flights with duration >= x (in hours).
    Also returns the median (minutes) and shares over 1h/2h/3h.

    Returns
    -------
    {
      "points": [{"x": hours, "y": pct_ge}],   # survival points (for plotting)
      "x_hours": [...], "cdf_pct": [...],      # kept for backward compat
      "median_min": int,
      "pct_gt": {1: float, 2: float, 3: float},
    }
    """
    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = (
        qs.annotate(
            ops_date=F("logsheet__log_date"),
            dur_diff=ExpressionWrapper(
                F("landing_time") - F("launch_time"), output_field=DurationField()
            ),
        )
        .annotate(dur=Coalesce(F("duration"), F("dur_diff")))
        .filter(ops_date__gte=start_date, ops_date__lte=end_date)
        .values_list("dur", flat=True)
    )

    secs: list[float] = []
    for d in qs:
        if d is not None:
            s = float(d.total_seconds())
            if s > 0:
                secs.append(s)

    if not secs:
        return {
            "points": [],
            "x_hours": [],
            "cdf_pct": [],
            "median_min": 0,
            "pct_gt": {1: 0.0, 2: 0.0, 3: 0.0},
        }

    secs.sort()  # ascending
    n = len(secs)

    # Downsample by rank but compute SURVIVAL: pct of flights with duration >= x
    step = max(1, n // max_points)
    points: list[dict] = []
    for j in range(0, n, step):
        xh = secs[j] / 3600.0
        pct_ge = (n - j) / n * 100.0  # survival at x = secs[j]
        points.append({"x": round(xh, 3), "y": round(pct_ge, 2)})

    # Ensure last point reaches ~0% at the maximum duration
    if points[-1]["x"] < secs[-1] / 3600.0:
        points.append(
            {"x": round(secs[-1] / 3600.0, 3), "y": round(1.0 / n * 100.0, 2)}
        )

    # Median (same as before)
    mid = secs[n // 2] if n % 2 == 1 else 0.5 * (secs[n // 2 - 1] + secs[n // 2])
    median_min = int(round(mid / 60.0))

    import bisect

    def pct_over(hours: float) -> float:
        threshold = hours * 3600.0
        k = bisect.bisect_right(secs, threshold)
        return round((n - k) / n * 100.0, 1)

    pct_gt = {1: pct_over(1.0), 2: pct_over(2.0), 3: pct_over(3.0)}

    # For backward compat: build CDF arrays from survival points
    x_hours = [p["x"] for p in points]
    cdf_pct = [round(100.0 - p["y"], 2) for p in points]

    return {
        "points": points,
        "x_hours": x_hours,
        "cdf_pct": cdf_pct,
        "median_min": median_min,
        "pct_gt": pct_gt,
    }


# 3) Non-instruction glider flights by pilot
def pilot_glider_flights(
    start_date: date, end_date: date, *, finalized_only=True, min_flights=2
) -> Dict[str, Any]:
    # Count glider flights per pilot where no instructor is on the flight.
    # Returns { "names": [...], "counts": [...] }

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    rows = (
        qs.annotate(ops_date=F("logsheet__log_date"))
        .filter(
            ops_date__gte=start_date,
            ops_date__lte=end_date,
            pilot__isnull=False,
            instructor__isnull=True,
        )
        .values("pilot_id")
        .annotate(n=Count("id"))
        .order_by("-n", "pilot_id")
    )

    ids = [r["pilot_id"] for r in rows if r["n"] >= min_flights]
    name_map = _display_name_map(ids)

    names = [name_map[i] for i in ids if i in name_map]
    counts = [int(r["n"]) for r in rows if r["pilot_id"] in name_map]
    return {"names": names, "counts": counts}


# Mon..Sun (Django ExtractWeekDay: Sun=1..Sat=7)
WEEKDAYS_ORDER = [2, 3, 4, 5, 6, 7, 1]
WEEKDAYS_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _stack_by_weekday(rows, id_order):
    """
    rows: iterable of dicts with keys ("member_id", "wday", "n")
    id_order: list of member ids in desired display order
    returns: matrix { "Mon":[...], "Tue":[...], ... } aligned to id_order
    """
    # build quick lookup: counts[(member_id, wday)] -> n
    counts = {}
    for r in rows:
        counts[(r["member_id"], r["wday"])] = int(r["n"])

    matrix: Dict[str, List[int]] = {lbl: [] for lbl in WEEKDAYS_LABELS}
    for mid in id_order:
        for w_idx, lbl in zip(WEEKDAYS_ORDER, WEEKDAYS_LABELS):
            matrix[lbl].append(counts.get((mid, w_idx), 0))
    return matrix


def instructor_flights_by_member(
    start_date, end_date, *, finalized_only=True, top_n=20, min_total=1
) -> Dict[str, Any]:
    """
    Horizontal stacked bars by instructor, broken down by weekday.
    """
    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, instructor__isnull=False
    )

    # totals per instructor
    totals_qs = (
        qs.values("instructor_id")
        .annotate(n=Count("id"))
        .order_by("-n", "instructor_id")
    )
    totals_rows = list(totals_qs)
    ids_sorted = [r["instructor_id"] for r in totals_rows if r["n"] >= min_total][
        :top_n
    ]
    if not ids_sorted:
        return {
            "names": [],
            "labels": WEEKDAYS_LABELS,
            "matrix": {},
            "totals": [],
            "inst_total": 0,
            "all_total": 0,
        }

    # weekday breakdown for just those IDs
    wday_rows = (
        qs.filter(instructor_id__in=ids_sorted)
        .annotate(wday=ExtractWeekDay(F("ops_date")))
        .values("instructor_id", "wday")
        .annotate(n=Count("id"))
    )

    # map ids -> display names
    name_map = _display_name_map(ids_sorted)
    names = [name_map.get(i, str(i)) for i in ids_sorted]

    # matrix aligned to ids_sorted
    matrix = _stack_by_weekday(
        [
            {"member_id": r["instructor_id"], "wday": r["wday"], "n": r["n"]}
            for r in wday_rows
        ],
        ids_sorted,
    )
    totals = [
        int(next((t["n"] for t in totals_rows if t["instructor_id"] == i), 0))
        for i in ids_sorted
    ]

    # overall counts for caption
    inst_total = int(qs.count())
    all_total = int(
        Flight.objects.filter(LANDED_ONLY)
        .filter(FINALIZED_ONLY if finalized_only else Q())
        .annotate(ops_date=F("logsheet__log_date"))
        .filter(ops_date__gte=start_date, ops_date__lte=end_date)
        .count()
    )

    return {
        "names": names,
        "labels": WEEKDAYS_LABELS,
        "matrix": matrix,
        "totals": totals,
        "inst_total": inst_total,
        "all_total": all_total,
    }


def towpilot_flights_by_member(
    start_date, end_date, *, finalized_only=True, top_n=20, min_total=1
) -> Dict[str, Any]:
    """
    Horizontal stacked bars by tow pilot, broken down by weekday.
    """
    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = qs.annotate(ops_date=F("logsheet__log_date")).filter(
        ops_date__gte=start_date, ops_date__lte=end_date, tow_pilot__isnull=False
    )

    totals_qs = (
        qs.values("tow_pilot_id").annotate(n=Count("id")).order_by("-n", "tow_pilot_id")
    )
    totals_rows = list(totals_qs)
    ids_sorted = [r["tow_pilot_id"] for r in totals_rows if r["n"] >= min_total][:top_n]
    if not ids_sorted:
        return {
            "names": [],
            "labels": WEEKDAYS_LABELS,
            "matrix": {},
            "totals": [],
            "tow_total": 0,
        }

    wday_rows = (
        qs.filter(tow_pilot_id__in=ids_sorted)
        .annotate(wday=ExtractWeekDay(F("ops_date")))
        .values("tow_pilot_id", "wday")
        .annotate(n=Count("id"))
    )

    name_map = _display_name_map(ids_sorted)
    names = [name_map.get(i, str(i)) for i in ids_sorted]

    matrix = _stack_by_weekday(
        [
            {"member_id": r["tow_pilot_id"], "wday": r["wday"], "n": r["n"]}
            for r in wday_rows
        ],
        ids_sorted,
    )
    totals = [
        int(next((t["n"] for t in totals_rows if t["tow_pilot_id"] == i), 0))
        for i in ids_sorted
    ]

    tow_total = int(qs.count())
    return {
        "names": names,
        "labels": WEEKDAYS_LABELS,
        "matrix": matrix,
        "totals": totals,
        "tow_total": tow_total,
    }


def long_flights_by_pilot(
    start_date,
    end_date,
    *,
    threshold_hours: float = 3.0,
    finalized_only: bool = True,
    min_count: int = 1,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Count flights with duration >= threshold_hours, grouped by pilot.
    Returns names (full_display_name), counts, and the longest flight (minutes).
    """
    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    qs = qs.annotate(
        ops_date=F("logsheet__log_date"),
        dur_diff=ExpressionWrapper(
            F("landing_time") - F("launch_time"), output_field=DurationField()
        ),
        dur=Coalesce(F("duration"), F("dur_diff")),
    ).filter(
        ops_date__gte=start_date,
        ops_date__lte=end_date,
        pilot__isnull=False,
        dur__gte=timedelta(hours=threshold_hours),
    )

    # Counts by pilot + longest overall
    rows = list(
        qs.values("pilot_id")
        .annotate(n=Count("id"), longest=Max("dur"))
        .order_by("-n", "pilot_id")
    )
    ids_ordered = [r["pilot_id"] for r in rows if r["n"] >= min_count][:top_n]
    if not ids_ordered:
        return {
            "names": [],
            "counts": [],
            "threshold_hours": threshold_hours,
            "longest_min": 0,
        }

    name_map = _display_name_map(ids_ordered)
    names = [name_map.get(i, str(i)) for i in ids_ordered]
    counts = [
        int(next((r["n"] for r in rows if r["pilot_id"] == i), 0)) for i in ids_ordered
    ]

    longest_any = qs.aggregate(m=Max("dur"))["m"]
    longest_min = int(round(longest_any.total_seconds() / 60.0)) if longest_any else 0

    return {
        "names": names,
        "counts": counts,
        "threshold_hours": float(threshold_hours),
        "longest_min": longest_min,
    }


def duty_days_by_member(
    start_date,
    end_date,
    *,
    finalized_only: bool = True,
    min_total: int = 1,
    top_n: int = 30,
) -> Dict[str, Any]:
    """
    Distinct assignment days per member for DO and ADO within the date range.
    Returns stacked data: labels ["DO","ADO"], matrix {label:[...]} aligned to names.
    """
    from logsheet.models import Logsheet

    base = Logsheet.objects.all()
    if finalized_only:
        base = base.filter(finalized=True)

    base = base.filter(log_date__gte=start_date, log_date__lte=end_date)

    # Distinct days per role
    do_rows = list(
        base.filter(duty_officer__isnull=False)
        .values("duty_officer_id")
        .annotate(n=Count("log_date", distinct=True))
    )
    ado_rows = list(
        base.filter(assistant_duty_officer__isnull=False)
        .values("assistant_duty_officer_id")
        .annotate(n=Count("log_date", distinct=True))
    )

    do_map = {r["duty_officer_id"]: int(r["n"]) for r in do_rows}
    ado_map = {r["assistant_duty_officer_id"]: int(r["n"]) for r in ado_rows}

    member_ids = set(do_map.keys()) | set(ado_map.keys())
    if not member_ids:
        return {
            "names": [],
            "labels": ["DO", "ADO"],
            "matrix": {"DO": [], "ADO": []},
            "totals": [],
            "do_total": 0,
            "ado_total": 0,
            "ops_days_total": int(base.values("log_date").distinct().count()),
        }

    # Sort by (DO+ADO) desc, then display name asc
    name_map = _display_name_map(list(member_ids))
    rows = []
    for mid in member_ids:
        nm = name_map.get(mid)
        if not nm:
            continue
        total = do_map.get(mid, 0) + ado_map.get(mid, 0)
        if total >= min_total:
            rows.append((mid, nm, total))
    rows.sort(key=lambda t: (-t[2], t[1].lower()))
    rows = rows[:top_n]

    ids_sorted = [mid for (mid, _, _) in rows]
    names = [name_map[mid] for mid in ids_sorted]
    do_list = [do_map.get(mid, 0) for mid in ids_sorted]
    ado_list = [ado_map.get(mid, 0) for mid in ids_sorted]
    totals = [d + a for d, a in zip(do_list, ado_list)]

    do_total = sum(do_map.values())
    ado_total = sum(ado_map.values())
    ops_days_total = int(base.values("log_date").distinct().count())

    return {
        "names": names,
        "labels": ["DO", "ADO"],
        "matrix": {"DO": do_list, "ADO": ado_list},
        "totals": totals,
        "do_total": do_total,
        "ado_total": ado_total,
        "ops_days_total": ops_days_total,
    }


def time_of_day_operations(
    start_year: int,
    end_year: int,
    *,
    finalized_only: bool = True,
) -> Dict[str, Any]:
    """
    Returns earliest takeoff and latest landing times by Julian day of year.

    Returns a scatter plot data structure with:
    - takeoff_points: [{"x": julian_day, "y": time_decimal}] for earliest takeoffs
    - landing_points: [{"x": julian_day, "y": time_decimal}] for latest landings
    - mean_takeoff_times: [{"x": julian_day, "y": mean_time_decimal}] for averaging line
    - mean_landing_times: [{"x": julian_day, "y": mean_time_decimal}] for averaging line

    Where time_decimal represents time as decimal hours (e.g., 14.5 = 2:30 PM)
    """
    from collections import defaultdict

    from logsheet.models import Flight

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    # Filter by year range - using SQLite-compatible date functions
    qs = qs.annotate(
        ops_date=F("logsheet__log_date"), ops_year=ExtractYear("ops_date")
    ).filter(ops_year__gte=start_year, ops_year__lte=end_year)

    def time_to_decimal(time_obj):
        """Convert time object to decimal hours"""
        if time_obj is None:
            return None
        return time_obj.hour + time_obj.minute / 60.0 + time_obj.second / 3600.0

    # Get all flights with their dates and times
    flights_data = list(qs.values("ops_date", "launch_time", "landing_time"))

    # Group flights by Julian day and find min/max times
    daily_data = defaultdict(lambda: {"takeoffs": [], "landings": []})

    for flight in flights_data:
        date_obj = flight["ops_date"]
        julian_day = date_obj.timetuple().tm_yday

        if flight["launch_time"]:
            daily_data[julian_day]["takeoffs"].append(
                time_to_decimal(flight["launch_time"])
            )
        if flight["landing_time"]:
            daily_data[julian_day]["landings"].append(
                time_to_decimal(flight["landing_time"])
            )

    # Calculate extreme points and means
    takeoff_points = []
    landing_points = []
    earliest_takeoff_by_day = []
    latest_landing_by_day = []

    for julian_day in range(1, 366):  # 1-365
        day_data = daily_data[julian_day]
        if day_data["takeoffs"]:
            earliest_takeoff = min(day_data["takeoffs"])
            takeoff_points.append({"x": julian_day, "y": round(earliest_takeoff, 2)})
            earliest_takeoff_by_day.append((julian_day, earliest_takeoff))
        if day_data["landings"]:
            latest_landing = max(day_data["landings"])
            landing_points.append({"x": julian_day, "y": round(latest_landing, 2)})
            latest_landing_by_day.append((julian_day, latest_landing))

    # Compute moving average for smoothing (window=7 days)
    def moving_average(points, window=7):
        if not points:
            return []
        result = []
        n = len(points)
        for i in range(n):
            start = max(0, i - window // 2)
            end = min(n, i + window // 2 + 1)
            avg = sum(val for _, val in points[start:end]) / (end - start)
            result.append({"x": points[i][0], "y": round(avg, 2)})
        return result

    mean_earliest_takeoff = moving_average(earliest_takeoff_by_day)
    mean_latest_landing = moving_average(latest_landing_by_day)

    return {
        "takeoff_points": takeoff_points,
        "landing_points": landing_points,
        "mean_earliest_takeoff": mean_earliest_takeoff,
        "mean_latest_landing": mean_latest_landing,
        "total_flight_days": len(
            [day for day in daily_data.values() if day["takeoffs"] or day["landings"]]
        ),
    }
