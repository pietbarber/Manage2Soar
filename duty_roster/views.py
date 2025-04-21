from django.shortcuts import render, redirect
from django.utils.timezone import now
from django.conf import settings
from django.contrib import messages
from .models import MemberBlackout, DutyPreference, DutyPairing, DutyAvoidance
from .forms import DutyPreferenceForm
from members.models import Member
from datetime import date, timedelta
import calendar
from members.decorators import active_member_required

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

    # Get pairings and avoidances
    pair_with = Member.objects.filter(pairing_target__member=member)
    avoid_with = Member.objects.filter(avoid_target__member=member)
    all_other_members = Member.objects.exclude(id=member.id).filter(is_active=True).order_by("last_name", "first_name")

    if request.method == "POST":
        blackout_dates = set(date.fromisoformat(d) for d in request.POST.getlist("blackout_dates"))
        default_note = request.POST.get("default_note", "").strip()

        for d in blackout_dates - existing_dates:
            MemberBlackout.objects.get_or_create(member=member, date=d, defaults={"note": default_note})

        for d in existing_dates - blackout_dates:
            MemberBlackout.objects.filter(member=member, date=d).delete()

        form = DutyPreferenceForm(request.POST)
        if form.is_valid():
            dp, _ = DutyPreference.objects.update_or_create(
                member=member,
                defaults=form.cleaned_data
            )

            # Pairings and avoidances
            DutyPairing.objects.filter(member=member).delete()
            DutyAvoidance.objects.filter(member=member).delete()

            for m in form.cleaned_data["pair_with"]:
                DutyPairing.objects.get_or_create(member=member, pair_with=m)

            for m in form.cleaned_data["avoid_with"]:
                DutyAvoidance.objects.get_or_create(member=member, avoid_with=m)

            messages.success(request, "Preferences saved successfully.")
            return redirect("duty_roster:blackout_manage")

    else:
        initial = {
            "preferred_day": preference.preferred_day if preference else None,
            "dont_schedule": preference.dont_schedule if preference else False,
            "scheduling_suspended": preference.scheduling_suspended if preference else False,
            "suspended_reason": preference.suspended_reason if preference else "",
            "instructor_percent": preference.instructor_percent if preference else 0,
            "duty_officer_percent": preference.duty_officer_percent if preference else 0,
            "ado_percent": preference.ado_percent if preference else 0,
            "towpilot_percent": preference.towpilot_percent if preference else 0,
            "pair_with": pair_with,
            "avoid_with": avoid_with,
        }
        form = DutyPreferenceForm(initial=initial)

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
        "pair_with": pair_with,
        "avoid_with": avoid_with,
        "all_other_members": all_other_members,
        "form": form,
    })
