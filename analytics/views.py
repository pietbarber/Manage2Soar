# analytics/views.py
from datetime import date
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
    cumu = queries.cumulative_flights_by_year(start, end, finalized_only=finalized_only)

    current_year = today.year if today.year in cumu["years"] else (cumu["years"][-1] if cumu["years"] else today.year)
# analytics/views.py (only the ctx changes shown)
    ctx = {
        "year": end,
        "start": start,
        "end": end,
        "finalized": finalized_only,
        "labels": cumu["labels"],
        "years": cumu["years"],
        "data": {str(y): cumu["data"][y] for y in cumu["years"]},   # already strings
        "totals": {str(k): v for k, v in cumu["totals"].items()},   # <- normalize
        "instr": {str(k): v for k, v in cumu["instr_counts"].items()},  # <- normalize
        "ops_days": cumu["ops_days"],
        "current_year": current_year,
        "user_name": getattr(request.user, "full_display_name", request.user.get_username()),
    }

    return render(request, "analytics/dashboard.html", ctx)
