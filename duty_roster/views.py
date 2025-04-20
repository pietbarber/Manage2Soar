from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from .models import MemberBlackout
from .forms import MemberBlackoutForm
from members.decorators import active_member_required
import calendar
from datetime import timedelta, date

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

    # Generate three consecutive months starting from current month
    months = []
    for i in range(3):
        next_month = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        calendar_data = generate_calendar(next_month.year, next_month.month)
        months.append({
            "label": next_month.strftime("%B %Y"),
            "calendar": calendar_data,
        })

    if request.method == "POST":
        submitted = set(
            date.fromisoformat(d)
            for d in request.POST.getlist("blackout_dates")
        )
        default_note = request.POST.get("default_note", "").strip()

        # Add new blackouts
        for d in submitted - existing_dates:
            MemberBlackout.objects.create(member=member, date=d, note=default_note)

        # Remove unselected ones
        for d in existing_dates - submitted:
            MemberBlackout.objects.filter(member=member, date=d).delete()

        return redirect("duty_roster:blackout_manage")

    return render(request, "duty_roster/blackout_calendar.html", {
        "months": months,
        "existing_dates": existing_dates,
        "today": today,
    })
