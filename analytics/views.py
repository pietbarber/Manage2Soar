# analytics/views.py
from datetime import date, datetime
from typing import Any, Dict, cast
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from members.constants.membership import DEFAULT_ACTIVE_STATUSES
from . import queries

def _is_active_member(user):
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return getattr(user, "membership_status", None) in DEFAULT_ACTIVE_STATUSES

@user_passes_test(_is_active_member, login_url="login")
def dashboard(request):
    today = date.today()
    start = int(request.GET.get("start", today.year - 14))
    end = int(request.GET.get("end", today.year))
    finalized_only = request.GET.get("all") != "1"

    # --- cumulative flights (defensive) ---
    cumu_raw: Dict[str, Any] = queries.cumulative_flights_by_year(
        start, end, finalized_only=finalized_only
    ) or {}  # <- ensure dict, never None

    labels = cast(list[int], cumu_raw.get("labels") or [])
    years_list = cast(list[int], cumu_raw.get("years") or [])
    data_map = cast(Dict[int, list[int]], cumu_raw.get("data") or {})
    totals_map = cast(Dict[int, int], cumu_raw.get("totals") or {})
    instr_map = cast(Dict[int, int], cumu_raw.get("instr_counts") or {})
    ops_days_map = cast(Dict[int, int], cumu_raw.get("ops_days") or {})

    # JSON-safe keys for template
    data_json = {str(y): (data_map.get(y) or [0] * 365) for y in years_list}
    totals_json = {str(k): int(v) for k, v in totals_map.items()}
    instr_json = {str(k): int(v) for k, v in instr_map.items()}

    # pick a current year that actually exists in the dataset
    if years_list:
        current_year = today.year if today.year in years_list else years_list[-1]
    else:
        current_year = today.year

    # --- flights by year by aircraft (defensive) ---
    by_acft_raw = cast(
        Dict[str, Any],
        queries.flights_by_year_by_aircraft(
            start, end, finalized_only=finalized_only, top_n=10
        ) or {}
    )
    # --- Glider utilization date range (defaults to YTD) ---
    def _parse_dt(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            return None
    
    util_start = _parse_dt(request.GET.get("util_start"))
    util_end   = _parse_dt(request.GET.get("util_end"))
    
    today = date.today()
    default_start = date(today.year, 1, 1)
    util_start = util_start or default_start
    util_end   = util_end or today
    util = queries.glider_utilization(util_start, util_end, finalized_only=finalized_only, top_n=12)
    util_private = queries.glider_utilization(
        util_start, util_end,
        finalized_only=finalized_only,
        top_n=12,
        fleet="private",
        bucket_private=False,     # list each private ship individually
        include_unknown=False,    # omit null-glider flights
    )
   
    fy_years = cast(list[int], by_acft_raw.get("years") or [])
    fy_categories = cast(list[str], by_acft_raw.get("categories") or [])
    fy_matrix = cast(Dict[str, list[int]], by_acft_raw.get("matrix") or {})
    fdays = queries.flying_days_by_member(util_start, util_end, finalized_only=finalized_only, min_days=2) or {}
    dur   = queries.flight_duration_distribution(util_start, util_end, finalized_only=finalized_only) or {}
    pgf   = queries.pilot_glider_flights(util_start, util_end, finalized_only=finalized_only, min_flights=2) or {}

    ctx = {
        "year": end,
        "start": start,
        "end": end,
        "finalized": finalized_only,
        "labels": labels,
        "years": years_list,
        "data": data_json,
        "totals": totals_json,
        "instr": instr_json,
        "ops_days": ops_days_map,
        "current_year": current_year,

        "fy_years": fy_years,
        "fy_categories": fy_categories,
        "fy_matrix": fy_matrix,

        "user_name": getattr(request.user, "full_display_name", request.user.get_username()),
        "util_names": util.get("names", []),
        "util_flights": util.get("flights", []),
        "util_hours": util.get("hours", []),
        "util_avg_minutes": util.get("avg_minutes", []),
        "util_start": util_start.isoformat(),
        "util_end": util_end.isoformat(),

        "utilp_names": util_private.get("names", []),
        "utilp_flights": util_private.get("flights", []),
        "utilp_hours": util_private.get("hours", []),
        "utilp_avg_minutes": util_private.get("avg_minutes", []),

        # flying days
        "fd_names": fdays.get("names", []),
        "fd_days": fdays.get("days", []),
        "fd_ops_total": fdays.get("ops_days_total", 0),

        # duration distribution
        "dur_x_hours": dur.get("x_hours", []),
        "dur_cdf_pct": dur.get("cdf_pct", []),
        "dur_median_min": dur.get("median_min", 0),
        "dur_pct_gt": dur.get("pct_gt", {1:0.0,2:0.0,3:0.0}),
        "dur_points": dur.get("points", []),
 
        # pilot flights (non-instruction)
        "pgf_names": pgf.get("names", []),
        "pgf_counts": pgf.get("counts", []),

    }
    analytics_data = {
        "cumulative": {
            "labels": labels,
            "years": years_list,
            "data": data_json,
            "totals": totals_json,
            "instr": instr_json,
            "current_year": current_year,
        },
        "by_acft": {
            "years": ctx.get("fy_years", []),
            "cats": ctx.get("fy_categories", []),
            "matrix": ctx.get("fy_matrix", {}),
        },
        "util": {
            "names": ctx.get("util_names", []),
            "flights": ctx.get("util_flights", []),
            "hours": ctx.get("util_hours", []),
            "avgm": ctx.get("util_avg_minutes", []),
        },
        "util_priv": {
            "names": ctx.get("utilp_names", []),
            "flights": ctx.get("utilp_flights", []),
            "hours": ctx.get("utilp_hours", []),
            "avgm": ctx.get("utilp_avg_minutes", []),
        },
        "fdays": {
            "names": ctx.get("fd_names", []),
            "days": ctx.get("fd_days", []),
            "ops_total": ctx.get("fd_ops_total", 0),
        },
        "pgf": {
            "names": ctx.get("pgf_names", []),
            "counts": ctx.get("pgf_counts", []),
        },
        "duration": {
            "points": ctx.get("dur_points", []),
            "x_hours": ctx.get("dur_x_hours", []),
            "cdf_pct": ctx.get("dur_cdf_pct", []),
            "median_min": ctx.get("dur_median_min", 0),
            "pct_gt": ctx.get("dur_pct_gt", {"1":0,"2":0,"3":0}),
        },

    }

    ctx["analytics_data"] = analytics_data
 
    return render(request, "analytics/dashboard.html", ctx)
