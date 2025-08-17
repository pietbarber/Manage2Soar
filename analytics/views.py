# analytics/views.py
from datetime import date
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

    fy_years = cast(list[int], by_acft_raw.get("years") or [])
    fy_categories = cast(list[str], by_acft_raw.get("categories") or [])
    fy_matrix = cast(Dict[str, list[int]], by_acft_raw.get("matrix") or {})

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

        # stacked bar inputs
        "fy_years": fy_years,
        "fy_categories": fy_categories,
        "fy_matrix": fy_matrix,

        "user_name": getattr(request.user, "full_display_name", request.user.get_username()),
    }
    return render(request, "analytics/dashboard.html", ctx)
