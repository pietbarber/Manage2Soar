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
    util_end = _parse_dt(request.GET.get("util_end"))

    today = date.today()
    default_start = date(today.year, 1, 1)
    util_start = util_start or default_start
    util_end = util_end or today
    util = queries.glider_utilization(
        util_start, util_end, finalized_only=finalized_only, top_n=12)
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
    fdays = queries.flying_days_by_member(
        util_start, util_end, finalized_only=finalized_only, min_days=2) or {}
    dur = queries.flight_duration_distribution(
        util_start, util_end, finalized_only=finalized_only) or {}
    pgf = queries.pilot_glider_flights(
        util_start, util_end, finalized_only=finalized_only, min_flights=2) or {}
    inst = queries.instructor_flights_by_member(
        util_start, util_end, finalized_only=finalized_only, top_n=20) or {}
    tow = queries.towpilot_flights_by_member(
        util_start, util_end, finalized_only=finalized_only, top_n=20) or {}
    long3h = queries.long_flights_by_pilot(
        util_start, util_end, finalized_only=finalized_only, threshold_hours=3.0, top_n=30) or {}
    duty = queries.duty_days_by_member(
        util_start, util_end, finalized_only=finalized_only, top_n=30) or {}

    # Tow pilot scheduled vs unscheduled chart data
    tow_sched = queries.tow_pilot_schedule_vs_actual(
        util_start, util_end, finalized_only=finalized_only, top_n=20) or {}

    # Instructor scheduled vs unscheduled chart data
    instructor_sched = queries.instructor_schedule_vs_actual(
        util_start, util_end, finalized_only=finalized_only, top_n=20) or {}

    # Time of day operations for yearly view (using start/end years)
    time_ops = queries.time_of_day_operations(
        start, end, finalized_only=finalized_only) or {}

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
        "dur_pct_gt": dur.get("pct_gt", {1: 0.0, 2: 0.0, 3: 0.0}),
        "dur_points": dur.get("points", []),

        # pilot flights (non-instruction)
        "pgf_names": pgf.get("names", []),
        "pgf_counts": pgf.get("counts", []),

        "inst_names":  inst.get("names", []),
        "inst_labels": inst.get("labels", []),
        "inst_matrix": inst.get("matrix", {}),
        "inst_totals": inst.get("totals", []),
        "inst_total":  inst.get("inst_total", 0),
        "all_total":   inst.get("all_total", 0),

        "tow_names":   tow.get("names", []),
        "tow_labels":  tow.get("labels", []),
        "tow_matrix":  tow.get("matrix", {}),
        "tow_totals":  tow.get("totals", []),
        "tow_total":   tow.get("tow_total", 0),

        "long3h_names": long3h.get("names", []),
        "long3h_counts": long3h.get("counts", []),
        "long3h_longest_min": long3h.get("longest_min", 0),
        "long3h_thresh": long3h.get("threshold_hours", 3.0),

        "duty_names": duty.get("names", []),
        "duty_labels": duty.get("labels", ["DO", "ADO"]),
        "duty_matrix": duty.get("matrix", {"DO": [], "ADO": []}),
        "duty_totals": duty.get("totals", []),
        "duty_do_total": duty.get("do_total", 0),
        "duty_ado_total": duty.get("ado_total", 0),
        "duty_ops_days_total": duty.get("ops_days_total", 0),

        # Tow pilot scheduled vs unscheduled
        "tow_sched_names": tow_sched.get("names", []),
        "tow_sched_scheduled": tow_sched.get("scheduled", []),
        "tow_sched_unscheduled": tow_sched.get("unscheduled", []),
        "tow_sched_labels": tow_sched.get("labels", ["Scheduled (Blue)", "Unscheduled (Burnt Orange)"]),

        # Instructor scheduled vs unscheduled
        "instructor_sched_names": instructor_sched.get("names", []),
        "instructor_sched_scheduled": instructor_sched.get("scheduled", []),
        "instructor_sched_unscheduled": instructor_sched.get("unscheduled", []),
        "instructor_sched_labels": instructor_sched.get("labels", ["Scheduled (Blue)", "Unscheduled (Burnt Orange)"]),

        # Time of day operations
        "timeops_takeoff_points": time_ops.get("takeoff_points", []),
        "timeops_landing_points": time_ops.get("landing_points", []),
        "timeops_mean_earliest_takeoff": time_ops.get("mean_earliest_takeoff", []),
        "timeops_mean_latest_landing": time_ops.get("mean_latest_landing", []),
        "timeops_total_flight_days": time_ops.get("total_flight_days", 0),

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
            "pct_gt": ctx.get("dur_pct_gt", {"1": 0, "2": 0, "3": 0}),
        },
        "instructors": {
            "names": ctx.get("inst_names", []),
            "labels": ctx.get("inst_labels", []),
            "matrix": ctx.get("inst_matrix", {}),
            "totals": ctx.get("inst_totals", []),
            "inst_total": ctx.get("inst_total", 0),
            "all_total": ctx.get("all_total", 0),
        },
        "tows": {
            "names": ctx.get("tow_names", []),
            "labels": ctx.get("tow_labels", []),
            "matrix": ctx.get("tow_matrix", {}),
            "totals": ctx.get("tow_totals", []),
            "tow_total": ctx.get("tow_total", 0),
        },

        "long3h": {
            "names": ctx.get("long3h_names", []),
            "counts": ctx.get("long3h_counts", []),
            "longest_min": ctx.get("long3h_longest_min", 0),
            "threshold_hours": ctx.get("long3h_thresh", 3.0),
        },
        "duty": {
            "names": ctx.get("duty_names", []),
            "labels": ctx.get("duty_labels", ["DO", "ADO"]),
            "matrix": ctx.get("duty_matrix", {"DO": [], "ADO": []}),
            "totals": ctx.get("duty_totals", []),
            "do_total": ctx.get("duty_do_total", 0),
            "ado_total": ctx.get("duty_ado_total", 0),
            "ops_days_total": ctx.get("duty_ops_days_total", 0),
        },

        "tow_sched": {
            "names": ctx.get("tow_sched_names", []),
            "scheduled": ctx.get("tow_sched_scheduled", []),
            "unscheduled": ctx.get("tow_sched_unscheduled", []),
            "labels": ctx.get("tow_sched_labels", []),
        },

        "instructor_sched": {
            "names": ctx.get("instructor_sched_names", []),
            "scheduled": ctx.get("instructor_sched_scheduled", []),
            "unscheduled": ctx.get("instructor_sched_unscheduled", []),
            "labels": ctx.get("instructor_sched_labels", []),
        },

        "time_ops": {
            "takeoff_points": ctx.get("timeops_takeoff_points", []),
            "landing_points": ctx.get("timeops_landing_points", []),
            "mean_earliest_takeoff": ctx.get("timeops_mean_earliest_takeoff", []),
            "mean_latest_landing": ctx.get("timeops_mean_latest_landing", []),
            "total_flight_days": ctx.get("timeops_total_flight_days", 0),
        },

    }

    ctx["analytics_data"] = analytics_data

    return render(request, "analytics/dashboard.html", ctx)
