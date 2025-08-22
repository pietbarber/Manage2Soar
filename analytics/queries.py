from collections import defaultdict
from datetime import date
from itertools import chain

from django.db.models.functions import Extract, ExtractYear
from logsheet.models import Flight
from typing import Dict, Any, TypedDict, List, Tuple
from django.db.models import Count, Q, F, Sum, Avg, DurationField
from django.db.models.functions import ExtractYear, Coalesce
from django.db.models.expressions import ExpressionWrapper
from logsheet.models import Flight
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model


FINALIZED_ONLY = Q(logsheet__finalized=True)
LANDED_ONLY = Q(landing_time__isnull=False) & Q(launch_time__isnull=False)
__all__ = ["cumulative_flights_by_year"]

def cumulative_flights_by_year(start_year=None, end_year=None, max_years=15, finalized_only=True):
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
    
    # Per (year, day-of-year) counts
    per_day = (
        qs.annotate(y=F("ops_year"), d=Extract("ops_date", "doy"))
          .values("y", "d")
          .annotate(n=Count("id"))
    )



    # Totals per year
    totals_qs = qs.values("ops_year").annotate(n=Count("id"))
    totals = {row["ops_year"]: row["n"] for row in totals_qs}

    # Ops days per year
    ops_days = {}
    for row in per_day:
        ops_days[row["y"]] = ops_days.get(row["y"], 0) + 1

    # Instructional flights per year
    instr_qs = (
        qs.filter(instructor__isnull=False)
          .values("ops_year")
          .annotate(n=Count("id"))
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


def flights_by_year_by_aircraft(start_year: int, end_year: int, *, finalized_only=True, top_n=10):
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
            or " ".join([p for p in [r.get("glider__make"), r.get("glider__model")] if p])
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
    sorted_cats = sorted([c for c in cat_counts if c != "Private"], key=lambda c: (-cat_counts[c], c))
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
            other_sum = sum(int(v) for k, v in year_row.items() if k not in set(head) | {"Private"})
            matrix["Other"][i] = other_sum

    totals_by_cat = {c: sum(vals) for c, vals in matrix.items()}
    return {"years": years, "categories": categories, "matrix": matrix, "totals_by_cat": totals_by_cat}
 
class GliderUtilization(TypedDict):
    names: List[str]          # labels in display order
    flights: List[int]        # flights per name
    hours: List[float]        # total hours per name
    avg_minutes: List[int]    # avg minutes per flight per name
    start: str
    end: str

def glider_utilization(
    start_date: date,
    end_date: date,
    *,
    finalized_only: bool = True,
    top_n: int = 12,
    fleet: str = "all",               # "all" | "club" | "private"
    bucket_private: bool = True,      # True → non-club into "Private"; False → list individually
    include_unknown: bool = True,     # include flights with null glider as "Unknown"
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
    qs = qs.annotate(
        ops_date=F("logsheet__log_date"),
        dur_diff=ExpressionWrapper(F("landing_time") - F("launch_time"), output_field=DurationField()),
    ).annotate(
        dur=Coalesce(F("duration"), F("dur_diff")),
    ).filter(
        ops_date__gte=start_date,
        ops_date__lte=end_date,
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
        return {"names": [], "flights": [], "hours": [], "avg_minutes": [], "start": start_date.isoformat(), "end": end_date.isoformat()}

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

def _username_map(ids: List[int]) -> Dict[int, str]:
    User = get_user_model()
    rows = User.objects.filter(id__in=ids).values("id", "username")
    return {r["id"]: r["username"] for r in rows}

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
    pilot_pairs = qs.filter(pilot__isnull=False).values_list("pilot_id", "ops_date").distinct()
    instr_pairs = qs.filter(instructor__isnull=False).values_list("instructor_id", "ops_date").distinct()
    tow_pairs   = qs.filter(tow_pilot__isnull=False).values_list("tow_pilot_id", "ops_date").distinct()

    # Union in Python and count distinct days per member
    days_by_member: Dict[int, set] = defaultdict(set)
    for mid, d in chain(pilot_pairs, instr_pairs, tow_pairs):
        if mid is not None and d is not None:
            days_by_member[int(mid)].add(d)

    # Filter by threshold and sort desc by days, then by username
    ids = [m for m, s in days_by_member.items() if len(s) >= min_days]
    if not ids:
        return {"names": [], "days": [], "ops_days_total": int(qs.values("ops_date").distinct().count())}

    # Map IDs -> usernames once
    User = get_user_model()
    name_map = {u["id"]: u["username"] for u in User.objects.filter(id__in=ids).values("id", "username")}

    rows: List[tuple] = []
    for m in ids:
        nm = name_map.get(m)
        if nm:
            rows.append((nm, len(days_by_member[m])))

    # sort by days desc, then name asc
    rows.sort(key=lambda t: (-t[1], t[0]))

    names = [t[0] for t in rows]
    days  = [int(t[1]) for t in rows]

    ops_days_total = int(qs.values("ops_date").distinct().count())
    return {"names": names, "days": days, "ops_days_total": ops_days_total}



# 2) Flight duration distribution (CDF) for glider flights
def flight_duration_distribution(start_date: date, end_date: date, *, finalized_only=True, max_points=400) -> Dict[str, Any]:
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

    qs = qs.annotate(
        ops_date=F("logsheet__log_date"),
        dur_diff=ExpressionWrapper(F("landing_time") - F("launch_time"), output_field=DurationField()),
    ).annotate(
        dur=Coalesce(F("duration"), F("dur_diff"))
    ).filter(
        ops_date__gte=start_date, ops_date__lte=end_date
    ).values_list("dur", flat=True)

    secs: list[float] = []
    for d in qs:
        if d is not None:
            s = float(d.total_seconds())
            if s > 0:
                secs.append(s)

    if not secs:
        return {"points": [], "x_hours": [], "cdf_pct": [], "median_min": 0, "pct_gt": {1: 0.0, 2: 0.0, 3: 0.0}}

    secs.sort()                      # ascending
    n = len(secs)

    # Downsample by rank but compute SURVIVAL: pct of flights with duration >= x
    step = max(1, n // max_points)
    points: list[dict] = []
    for j in range(0, n, step):
        xh = secs[j] / 3600.0
        pct_ge = (n - j) / n * 100.0          # survival at x = secs[j]
        points.append({"x": round(xh, 3), "y": round(pct_ge, 2)})

    # Ensure last point reaches ~0% at the maximum duration
    if points[-1]["x"] < secs[-1] / 3600.0:
        points.append({"x": round(secs[-1] / 3600.0, 3), "y": round(1.0 / n * 100.0, 2)})

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

    return {"points": points, "x_hours": x_hours, "cdf_pct": cdf_pct, "median_min": median_min, "pct_gt": pct_gt}




# 3) Non-instruction glider flights by pilot
def pilot_glider_flights(start_date: date, end_date: date, *, finalized_only=True, min_flights=2) -> Dict[str, Any]:
    # Count glider flights per pilot where no instructor is on the flight.
    # Returns { "names": [...], "counts": [...] }

    qs = Flight.objects.filter(LANDED_ONLY)
    if finalized_only:
        qs = qs.filter(FINALIZED_ONLY)

    rows = (qs.annotate(ops_date=F("logsheet__log_date"))
              .filter(ops_date__gte=start_date, ops_date__lte=end_date,
                      pilot__isnull=False, instructor__isnull=True)
              .values("pilot_id")
              .annotate(n=Count("id"))
              .order_by("-n", "pilot_id"))

    ids = [r["pilot_id"] for r in rows if r["n"] >= min_flights]
    name_map = _username_map(ids)

    names = [name_map[i] for i in ids if i in name_map]
    counts = [int(r["n"]) for r in rows if r["pilot_id"] in name_map]
    return {"names": names, "counts": counts}
