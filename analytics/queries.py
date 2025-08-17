from collections import defaultdict
from datetime import date
from django.db.models import Count, Q, F          # <-- add F
from django.db.models.functions import Extract, ExtractYear
from logsheet.models import Flight

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
    """
    Pivot data for a stacked bar:
      {
        "years": [2015, ...],
        "categories": ["N341KS","N321K","GROB 103","Private","Other",...],
        "matrix": {category: [counts aligned to years]},
        "totals_by_cat": {category: total across all years},
      }
    Buckets non-club ships (glider.club_owned == False) into "Private".
    Low-volume ships beyond top_n are grouped under "Other".
    """
    from logsheet.models import Flight  # local to avoid accidental circulars

    FINALIZED_ONLY = Q(logsheet__finalized=True)
    LANDED_ONLY = Q(landing_time__isnull=False) & Q(launch_time__isnull=False)

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
 
