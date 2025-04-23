from django.shortcuts import render, redirect
from django.utils.timezone import now
from django.conf import settings
from django.contrib import messages
from .models import MemberBlackout, DutyPreference, DutyPairing, DutyAvoidance
from .forms import DutyPreferenceForm
from members.models import Member
from datetime import date, timedelta
import calendar
from calendar import Calendar, monthrange
from members.decorators import active_member_required
from django.http import HttpResponse
from .models import DutyAssignment
from django.shortcuts import get_object_or_404
from .models import OpsIntent
from django.views.decorators.http import require_POST
from django.http import HttpResponse


# Create your views here.

def roster_home(request):
    return HttpResponse("Duty Roster Home")

@active_member_required
def blackout_manage(request):
    member = request.user
    preference, _ = DutyPreference.objects.get_or_create(member=member)

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
    role_percent_choices = []
    if member.instructor:
        role_percent_choices.append(("instructor", "Flight Instructor"))
    if member.duty_officer:
        role_percent_choices.append(("duty_officer", "Duty Officer"))
    if member.assistant_duty_officer:
        role_percent_choices.append(("ado", "Assistant Duty Officer"))
    if member.towpilot:
        role_percent_choices.append(("towpilot", "Tow Pilot"))



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

            for m in form.cleaned_data.get("pair_with", []):
                DutyPairing.objects.get_or_create(member=member, pair_with=m)

            for m in form.cleaned_data.get("avoid_with", []):
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
            "max_assignments_choices": [1,2,3,4],
            "preference": preference,
            "role_percent_choices": role_percent_choices
        }
        form = DutyPreferenceForm(initial=initial)

    return render(request, "duty_roster/blackout_calendar.html", {
        "months": months,
        "existing_dates": existing_dates,
        "today": today,
        "percent_options": percent_options,
        "role_percent_choices": role_percent_choices,
        "preference": preference,
        "pair_with": pair_with,
        "avoid_with": avoid_with,
        "all_other_members": all_other_members,
        "form": form,
        "max_assignments_choices": [1,2,3,4],
        "role_percent_choices": role_percent_choices,
        "all_possible_roles": ["instructor", "duty_officer", "ado", "towpilot"],
        "shown_roles": [r[0] for r in role_percent_choices],

    })


# duty_roster/views.py



def get_adjacent_months(year, month):
    # Previous month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    # Next month
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return prev_year, prev_month, next_year, next_month

def duty_calendar_view(request, year=None, month=None):
    today = date.today()
    year = int(year) if year else today.year
    month = int(month) if month else today.month

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(year, month)
    first_visible_day = weeks[0][0]
    last_visible_day = weeks[-1][-1]
    assignments = DutyAssignment.objects.filter(date__range=(first_visible_day, last_visible_day))


    assignments_by_date = {a.date: a for a in assignments}

    prev_year, prev_month, next_year, next_month = get_adjacent_months(year, month)

    context = {
        "year": year,
        "month": month,
        "weeks": weeks,
        "assignments_by_date": assignments_by_date,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
    }

    if request.htmx:
        return render(request, "duty_roster/_calendar_body.html", context)
    return render(request, "duty_roster/calendar.html", context)

def calendar_day_detail(request, year, month, day):
    day_date = date(year, month, day)
    assignment = DutyAssignment.objects.filter(date=day_date).first()

    # Show current user intent status
    intent_exists = False
    can_submit_intent = request.user.is_authenticated and day_date >= date.today()
    if request.user.is_authenticated:
        intent_exists = OpsIntent.objects.filter(member=request.user, date=day_date).exists()

    # Pull all intents for the day
    intents = OpsIntent.objects.filter(date=day_date).select_related("member").order_by("member__last_name")

    return render(request, "duty_roster/calendar_day_modal.html", {
        "day": day_date,
        "assignment": assignment,
        "intent_exists": intent_exists,
        "can_submit_intent": can_submit_intent,
        "intents": intents,
    })


@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    day_date = date(year, month, day)
    intent, created = OpsIntent.objects.get_or_create(member=request.user, date=day_date)

    if not created:
        # Already existed — remove it
        intent.delete()
        response = '<p class="text-gray-700">❌ You’ve removed your intent to fly.</p>'
        response += f'<button hx-post="{request.path}" hx-target="#ops-intent-response" hx-swap="innerHTML" class="btn btn-sm btn-primary">🛩️ I Plan to Fly This Day</button>'
    else:
        response = '<p class="text-green-700">✅ You’re now marked as planning to fly this day.</p>'
        response += f'<button hx-post="{request.path}" hx-target="#ops-intent-response" hx-swap="innerHTML" class="btn btn-sm btn-danger">Cancel Intent</button>'

    return HttpResponse(response)
