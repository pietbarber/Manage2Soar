import calendar
from calendar import Calendar, monthrange
from collections import defaultdict
from datetime import date, timedelta
from django.utils.timezone import now
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from members.models import Member
from members.decorators import active_member_required
from .models import MemberBlackout, DutyPreference, DutyPairing, DutyAvoidance, OpsIntent, DutyAssignment, DutyDay, DutySlot
from .forms import DutyAssignmentForm, DutyPreferenceForm
from django.template.loader import render_to_string
from logsheet.models import Airfield
from duty_roster.utils.email import notify_ops_status
from django.contrib.auth.decorators import user_passes_test
from .roster_generator import generate_roster  # your existing generation logic
from datetime import date as dt_date
from django.utils import timezone
from members.constants.membership import DEFAULT_ROLES, ROLE_FIELD_MAP
from django.urls import reverse
from django.contrib import messages



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

    # After building `weeks` for the calendar
    visible_dates = [day for week in weeks for day in week]
    
    # Then safely run these:
    instruction_count = defaultdict(int)
    tow_count = defaultdict(int)
    
    intents = OpsIntent.objects.filter(date__in=visible_dates)

    for intent in intents:
        roles = intent.available_as or []
        if "instruction" in roles:
            instruction_count[intent.date] += 1
        if "private" in roles or "club" in roles:
            tow_count[intent.date] += 1


    surge_needed_by_date = {}

    for day in visible_dates:
        day_date = day if isinstance(day, date) else day.date()
        surge_needed_by_date[day_date] = {
            "instructor": instruction_count[day_date] > 3,
            "towpilot": tow_count[day_date] >= 6,
        }

    context = {
        "year": year,
        "month": month,
        "weeks": weeks,
        "assignments_by_date": assignments_by_date,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
        "surge_needed_by_date": surge_needed_by_date,
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

    # Check for instruction-specific intent
    instruction_intent_count = sum(1 for i in intents if "instruction" in i.available_as)
    tow_count = sum(1 for i in intents if "club" in i.available_as or "private" in i.available_as)

    show_surge_alert = instruction_intent_count > 3
    show_tow_surge_alert = tow_count >= 6

    return render(request, "duty_roster/calendar_day_modal.html", {
        "day": day_date,
        "assignment": assignment,
        "intent_exists": intent_exists,
        "can_submit_intent": can_submit_intent,
        "intents": intents,
        "show_surge_alert": show_surge_alert,
        "instruction_intent_count": instruction_intent_count,
        "tow_count": tow_count,
        "show_tow_surge_alert": show_tow_surge_alert,
        "today": date.today(),

    })

@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    day_date = date(year, month, day)

    available_as = request.POST.getlist("available_as") or []
    if available_as:
        OpsIntent.objects.update_or_create(
            member=request.user,
            date=day_date,
            defaults={"available_as": available_as}
        )
        response = '<p class="text-green-700">✅ You’re now marked as planning to fly this day.</p>'
        response += f'<button hx-post="{request.path}" hx-target="#ops-intent-response" hx-swap="innerHTML" class="btn btn-sm btn-danger">Cancel Intent</button>'
    else:
        OpsIntent.objects.filter(member=request.user, date=day_date).delete()
        response = '<p class="text-gray-700">❌ You’ve removed your intent to fly.</p>'
        response += f'<form hx-get="{request.path}form/" hx-target="#ops-intent-response" hx-swap="innerHTML">'
        response += f'<button type="submit" class="btn btn-sm btn-primary">🛩️ I Plan to Fly This Day</button></form>'
    maybe_notify_surge_instructor(day_date)
    maybe_notify_surge_towpilot(day_date)

    return HttpResponse(response)

def ops_intent_form(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=403)

    day_date = date(year, month, day)
    return render(request, "duty_roster/ops_intent_form.html", {
        "day": day_date,
    })

def maybe_notify_surge_instructor(day_date):
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
    if assignment.surge_notified:
        return

    intents = OpsIntent.objects.filter(date=day_date)
    instruction_count = sum(1 for i in intents if "instruction" in i.available_as)

    if instruction_count > 3:
        send_mail(
            subject=f"Surge Instructor May Be Needed - {day_date.strftime('%A, %B %d')}",
            message=f"There are currently {instruction_count} pilots requesting instruction for {day_date.strftime('%A, %B %d, %Y')}.\n\nYou may want to coordinate a surge instructor.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=["instructors@skylinesoaring.org"],
            fail_silently=True,
        )
        assignment.surge_notified = True
        assignment.save()

def maybe_notify_surge_towpilot(day_date):
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
    if assignment.tow_surge_notified:
        return

    intents = OpsIntent.objects.filter(date=day_date)
    tow_count = sum(1 for i in intents if "club" in i.available_as or "private" in i.available_as)

    if tow_count >= 6:
        send_mail(
            subject=f"Surge Tow Pilot May Be Needed - {day_date.strftime('%A, %B %d')}",
            message=f"There are currently {tow_count} pilots planning flights requiring tows on {day_date.strftime('%A, %B %d, %Y')}.\n\nYou may want to coordinate a surge tow pilot.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=["towpilots@skylinesoaring.org"],
            fail_silently=True,
        )
        assignment.tow_surge_notified = True
        assignment.save()

def assignment_edit_form(request, year, month, day):
    if not request.user.is_authenticated or not request.user.rostermeister:
        return HttpResponse("Forbidden", status=403)

    day_date = date(year, month, day)
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)

    form = DutyAssignmentForm(instance=assignment)

    return render(request, "duty_roster/assignment_edit_form.html", {
        "form": form,
        "day": day_date,
    })

@require_POST
def assignment_save_form(request, year, month, day):
    if not request.user.is_authenticated or not request.user.rostermeister:
        return HttpResponse("Forbidden", status=403)

    day_date = date(year, month, day)
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)

    form = DutyAssignmentForm(request.POST, instance=assignment)
    if form.is_valid():
        assignment = form.save(commit=False)

        # Check for tow pilot to confirm ad-hoc day
        if not assignment.is_confirmed and not assignment.is_scheduled:
            if assignment.tow_pilot and assignment.duty_officer:
                assignment.is_confirmed = True

        assignment.save()

        form.save()
        # Reload the full modal so crew updates show
        return JsonResponse({"reload": True})
    else:
        return render(request, "duty_roster/assignment_edit_form.html", {
            "form": form,
            "day": day_date,
        })


@require_GET
def calendar_ad_hoc_start(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))

    # Extra safety check
    if day_obj <= date.today():
        return HttpResponse(status=400)

    html = render_to_string(
        "duty_roster/calendar_ad_hoc_start.html", 
        {"date": day_obj},
        request=request,
    )
    return HttpResponse(html)

@require_POST
def calendar_ad_hoc_confirm(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))

    # Make sure it's still a valid future date
    if day_obj <= date.today():
        return HttpResponse(status=400)
    default_airfield = Airfield.objects.get(identifier="KFRR")

    assignment, created = DutyAssignment.objects.get_or_create(
        date=day_obj,
        defaults={
            "location": default_airfield,
            "is_scheduled": False,
            "is_confirmed": False,
        }
    )
    notify_ops_status(assignment)
    return JsonResponse({"reload": True })


@require_POST
@active_member_required
def calendar_tow_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    # Validate that user is allowed
    member = request.user
    if not member.towpilot:
        return HttpResponseForbidden("You are not a tow pilot.")

    # Assign as tow pilot if none already assigned
    if not assignment.tow_pilot:
        assignment.tow_pilot = member

        assignment.save()
        notify_ops_status(assignment)

    return JsonResponse({"reload": True})

@require_POST
@active_member_required
def calendar_dutyofficer_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    member = request.user
    if not member.duty_officer:
        return HttpResponseForbidden("You are not a duty officer.")

    if not assignment.duty_officer:
        assignment.duty_officer = member

        assignment.save()
        notify_ops_status(assignment)

    return JsonResponse({"reload": True})

@require_POST
@active_member_required
def calendar_instructor_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    member = request.user
    if not member.instructor:
        return HttpResponseForbidden("You are not an instructor.")

    if not assignment.instructor:
        assignment.instructor = member
        assignment.save()

    return HttpResponse(status=204)

@require_POST
@active_member_required
def calendar_ado_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    member = request.user
    if not member.assistant_duty_officer:
        return HttpResponseForbidden("You are not an assistant duty officer.")

    if not assignment.assistant_duty_officer:
        assignment.assistant_duty_officer = member
        assignment.save()

    return HttpResponse(status=204)


@require_POST
@active_member_required
def calendar_cancel_ops_day(request, year, month, day):
    from datetime import date
    
    ops_date = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=ops_date)

    # Check that it's an ad-hoc day
    if assignment.is_scheduled:
        return HttpResponseBadRequest("Cannot cancel scheduled operations.")

    reason = request.POST.get("reason", "").strip()
    if not reason or len(reason) < 10:
        return HttpResponseBadRequest("Cancellation reason is required and must be at least 10 characters.")

    canceller_name = request.user.full_display_name

    body = (
        f"Operations for {ops_date.strftime('%A, %B %d, %Y')} have been canceled.\n\n"
        f"Canceled by: {canceller_name}\n\n"
        f"Reason:\n{reason}\n\n"
        f"Stay safe and we'll see you next time!"
    )

    # Send to members@skylinesoaring.org
    send_mail(
        subject=f"[Skyline Soaring] Operations Canceled – {ops_date.strftime('%B %d')}",
        message=body,
        from_email="noreply@skylinesoaring.org",
        recipient_list=["members@skylinesoaring.org"],
    )

    # Delete the DutyAssignment entry
    assignment.delete()

    return JsonResponse({"reload": True})

@active_member_required
def calendar_cancel_ops_modal(request, year, month, day):
    from datetime import date

    ops_date = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=ops_date)

    return render(request, "duty_roster/calendar_cancel_modal.html", {"assignment": assignment})

def is_rostermeister(user):
    return user.is_authenticated and user.rostermeister

@active_member_required
@user_passes_test(is_rostermeister)
def propose_roster(request):
    year = request.POST.get('year') or request.GET.get('year')
    month = request.POST.get('month') or request.GET.get('month')
    if year and month:
        year, month = int(year), int(month)
    else:
        today = timezone.now().date()
        year, month = today.year, today.month
    incomplete = False
    if request.method == 'POST':
        action = request.POST.get('action')
        draft = request.session.get('proposed_roster', [])
        if action == 'roll':
            raw = generate_roster(year, month)
            if not raw:
                cal = calendar.Calendar()
                weekend = [
                    d for d in cal.itermonthdates(year, month)
                    if d.month == month and d.weekday() in (5, 6)
                ]
                raw = [{'date': d, 'slots': {r: None for r in DEFAULT_ROLES}} for d in weekend]
                incomplete = True
            draft = [{'date': e['date'].isoformat(), 'slots': e['slots']} for e in raw]
            request.session['proposed_roster'] = draft

        elif action == 'publish':
            from .models import DutyAssignment
            default_field = Airfield.objects.get(pk=settings.DEFAULT_AIRFIELD_ID)
            DutyAssignment.objects.filter(
                date__year=year, date__month=month
            ).delete()
        
            for e in request.session.get('proposed_roster', []):
                edt = dt_date.fromisoformat(e['date'])
                assignment_data = {
                    'date': edt,
                    'location': default_field,
                }
                for role, mem in e['slots'].items():
                    field_name = ROLE_FIELD_MAP.get(role)
                    if field_name and mem:
                        assignment_data[field_name] = Member.objects.get(pk=mem)
        
                DutyAssignment.objects.create(**assignment_data)
        
            request.session.pop('proposed_roster', None)
            messages.success(request, f"Duty roster published for {month}/{year}.")
            return redirect(
                'duty_roster:duty_calendar_month', year=year, month=month
            )

        elif action == 'cancel':
            request.session.pop('proposed_roster', None)
            return redirect('duty_roster:duty_calendar')
    else:
        raw = generate_roster(year, month)
        if not raw:
            cal = calendar.Calendar()
            weekend = [
                d for d in cal.itermonthdates(year, month)
                if d.month == month and d.weekday() in (5, 6)
            ]
            raw = [{'date': d, 'slots': {r: None for r in DEFAULT_ROLES}} for d in weekend]
            incomplete = True
        draft = [{'date': e['date'].isoformat(), 'slots': e['slots']} for e in raw]
        request.session['proposed_roster'] = draft
    display = [{'date': dt_date.fromisoformat(e['date']), 'slots': e['slots']} for e in request.session.get('proposed_roster', [])]
    return render(request, 'duty_roster/propose_roster.html', {
        'draft': display,
        'year': year,
        'month': month,
        'incomplete': incomplete,
        'DEFAULT_ROLES': DEFAULT_ROLES
    })

@active_member_required
def calendar_view(request, year=None, month=None):
    today = timezone.now().date()
    year = int(year) if year else today.year
    month = int(month) if month else today.month
    cal = calendar.Calendar()
    weeks = cal.monthdatescalendar(year, month)
    grid = []
    for week in weeks:
        days = []
        for d in week:
            if d.month != month:
                days.append({'date': d, 'slots': None})
            else:
                assignments = DutySlot.objects.filter(duty_day__date=d)
                slots = {role: '' for role in DEFAULT_ROLES}
                for a in assignments:
                    slots[a.role] = a.member.full_display_name
                days.append({'date': d, 'slots': slots})
        grid.append(days)
    context = {'weeks': grid, 'year': year, 'month': month, 'DEFAULT_ROLES': DEFAULT_ROLES}
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'duty_roster/partials/calendar_grid.html', context)
    return render(request, 'duty_roster/calendar.html', context)
