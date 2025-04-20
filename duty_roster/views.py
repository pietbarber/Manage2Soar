from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from .models import MemberBlackout, DutyPreference
from members.decorators import active_member_required
import calendar
from datetime import timedelta, date
from django.contrib import messages

# Create your views here.
from django.http import HttpResponse

def roster_home(request):
    return HttpResponse("Duty Roster Home")

@active_member_required
def blackout_manage(request):
    member = request.user
    existing = MemberBlackout.objects.filter(member=member)
    existing_dates = set(b.date for b in existing)

    today = now().date()
    def generate_calendar(year, month):
        cal = calendar.Calendar()
        month_days = cal.itermonthdates(year, month)
        weeks = []
        week = []
        for day in month_days:
            if len(week) == 7:
                weeks.append(week)
                week = []
            week.append(day if day.month == month else None)
        if week:
            while len(week) < 7:
                week.append(None)
            weeks.append(week)
        return weeks

    months = []
    for i in range(3):
        next_month = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        calendar_data = generate_calendar(next_month.year, next_month.month)
        months.append({
            "label": next_month.strftime("%B %Y"),
            "calendar": calendar_data,
        })

    preference = DutyPreference.objects.filter(member=member).first()
    percent_options = [0, 25, 33, 50, 66, 75, 100]
    role_percent_choices = [
        ("instructor", "Instructor"),
        ("duty_officer", "Duty Officer"),
        ("ado", "Assistant Duty Officer"),
        ("towpilot", "Tow Pilot"),
    ]

    if request.method == "POST":
        submitted = set(
            date.fromisoformat(d)
            for d in request.POST.getlist("blackout_dates")
        )
        default_note = request.POST.get("default_note", "").strip()

        for d in submitted - existing_dates:
            MemberBlackout.objects.get_or_create(member=member, date=d, defaults={"note": default_note})

        for d in existing_dates - submitted:
            MemberBlackout.objects.filter(member=member, date=d).delete()

        dont_schedule = bool(request.POST.get("dont_schedule"))
        preferred_day = request.POST.get("preferred_day") or None
        suspended_reason = request.POST.get("suspended_reason") or None

        role_percentages = {
            k: int(request.POST.get(f"{k}_percent", 0))
            for k, _ in role_percent_choices
        }

        total = sum(role_percentages.values())
        if total < 98 or total > 102:
            return render(request, "duty_roster/blackout_calendar.html", {
                "months": months,
                "existing_dates": existing_dates,
                "today": today,
                "error": "Your duty preferences must add up to approximately 100%",
                "preference": role_percentages,
                "percent_options": percent_options,
                "role_percent_choices": role_percent_choices,
            })

        DutyPreference.objects.update_or_create(
            member=member,
            defaults={
                "dont_schedule": dont_schedule,
                "preferred_day": preferred_day,
                "scheduling_suspended": bool(suspended_reason),
                "suspended_reason": suspended_reason,
                **{f"{k}_percent": v for k, v in role_percentages.items()}
            }
        )

        messages.success(request, "Preferences saved successfully.")
        return redirect("duty_roster:blackout_manage")

    return render(request, "duty_roster/blackout_calendar.html", {
        "months": months,
        "existing_dates": existing_dates,
        "today": today,
        "percent_options": percent_options,
        "role_percent_choices": role_percent_choices,
        "preference": {
            "instructor": preference.instructor_percent if preference else 0,
            "duty_officer": preference.duty_officer_percent if preference else 0,
            "ado": preference.ado_percent if preference else 0,
            "towpilot": preference.towpilot_percent if preference else 0,
        } if preference else {},
    })
