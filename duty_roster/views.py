import calendar
import json
from collections import defaultdict
from datetime import date
from datetime import date as dt_date
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.mail import send_mail
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.http import require_GET, require_POST

from duty_roster.utils.email import notify_ops_status
from logsheet.models import Airfield
from members.constants.membership import DEFAULT_ROLES, ROLE_FIELD_MAP
from members.decorators import active_member_required
from members.models import Member
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title

from .forms import DutyAssignmentForm, DutyPreferenceForm
from .models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutySlot,
    MemberBlackout,
    OpsIntent,
)
from .roster_generator import generate_roster


def calendar_refresh_response(year, month):
    """Helper function to create HTMX response that refreshes calendar with month context"""
    trigger_data = {
        'refreshCalendar': {
            'year': int(year),
            'month': int(month)
        }
    }
    return HttpResponse(
        headers={
            'HX-Trigger': json.dumps(trigger_data)
        }
    )


def roster_home(request):
    return HttpResponse("Duty Roster Home")


@active_member_required
def blackout_manage(request):
    member = request.user
    preference, _ = DutyPreference.objects.get_or_create(member=member)

    max_choices = preference._meta.get_field("max_assignments_per_month").choices

    existing = MemberBlackout.objects.filter(member=member)
    existing_dates = set(b.date for b in existing)

    today = now().date()

    def generate_calendar(year, month):
        cal = calendar.Calendar()
        month_days = cal.itermonthdates(year, month)
        weeks, week = [], []
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
        m1 = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        months.append(
            {
                "label": m1.strftime("%B %Y"),
                "calendar": generate_calendar(m1.year, m1.month),
            }
        )

    percent_options = [0, 25, 33, 50, 66, 75, 100]
    role_choices = []
    if member.instructor:
        role_choices.append(("instructor", "Flight Instructor"))
    if member.duty_officer:
        role_choices.append(
            ("duty_officer", get_role_title("duty_officer") or "Duty Officer")
        )
    if member.assistant_duty_officer:
        role_choices.append(
            (
                "ado",
                get_role_title("assistant_duty_officer") or "Assistant Duty Officer",
            )
        )
    if member.towpilot:
        role_choices.append(("towpilot", "Tow Pilot"))

    pair_with = Member.objects.filter(pairing_target__member=member)
    avoid_with = Member.objects.filter(avoid_target__member=member)
    all_other = Member.objects.exclude(id=member.id).filter(is_active=True)

    if request.method == "POST":
        blackout_dates = set(
            date.fromisoformat(d) for d in request.POST.getlist("blackout_dates")
        )
        note = request.POST.get("default_note", "").strip()
        for d in blackout_dates - existing_dates:
            MemberBlackout.objects.get_or_create(
                member=member, date=d, defaults={"note": note}
            )
        for d in existing_dates - blackout_dates:
            MemberBlackout.objects.filter(member=member, date=d).delete()

        form = DutyPreferenceForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            DutyPreference.objects.update_or_create(
                member=member,
                defaults={
                    "preferred_day": data["preferred_day"],
                    "comment": data["comment"],
                    "dont_schedule": data["dont_schedule"],
                    "scheduling_suspended": data["scheduling_suspended"],
                    "suspended_reason": data["suspended_reason"],
                    "last_duty_date": data["last_duty_date"],
                    "instructor_percent": data["instructor_percent"],
                    "duty_officer_percent": data["duty_officer_percent"],
                    "ado_percent": data["ado_percent"],
                    "towpilot_percent": data["towpilot_percent"],
                    "max_assignments_per_month": data["max_assignments_per_month"],
                    "allow_weekend_double": data.get("allow_weekend_double", False),
                },
            )
            DutyPairing.objects.filter(member=member).delete()
            DutyAvoidance.objects.filter(member=member).delete()
            for m in data.get("pair_with", []):
                DutyPairing.objects.create(member=member, pair_with=m)
            for m in data.get("avoid_with", []):
                DutyAvoidance.objects.create(member=member, avoid_with=m)

            messages.success(request, "Preferences saved successfully.")
            return redirect("duty_roster:blackout_manage")
    else:
        initial = {
            "preferred_day": preference.preferred_day,
            "comment": preference.comment,
            "dont_schedule": preference.dont_schedule,
            "scheduling_suspended": preference.scheduling_suspended,
            "suspended_reason": preference.suspended_reason,
            "last_duty_date": preference.last_duty_date,
            "instructor_percent": preference.instructor_percent,
            "duty_officer_percent": preference.duty_officer_percent,
            "ado_percent": preference.ado_percent,
            "towpilot_percent": preference.towpilot_percent,
            "max_assignments_per_month": preference.max_assignments_per_month,
            "allow_weekend_double": preference.allow_weekend_double,
            "pair_with": pair_with,
            "avoid_with": avoid_with,
        }
        form = DutyPreferenceForm(initial=initial)

    return render(
        request,
        "duty_roster/blackout_calendar.html",
        {
            "months": months,
            "existing_dates": existing_dates,
            "today": today,
            "percent_options": percent_options,
            "role_percent_choices": role_choices,
            "preference": preference,
            "pair_with": pair_with,
            "avoid_with": avoid_with,
            "all_other_members": all_other,
            "form": form,
            # pass the choices into the template:
            "max_assignments_choices": max_choices,
        },
    )


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
    assignments = DutyAssignment.objects.filter(
        date__range=(first_visible_day, last_visible_day)
    )

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

    # Add formatted month and date context
    month_name = calendar.month_name[month]
    formatted_date = f"{month_name} {year}"

    # Get previous and next month names for navigation
    prev_month_name = calendar.month_name[prev_month]
    next_month_name = calendar.month_name[next_month]

    context = {
        "year": year,
        "month": month,
        "month_name": month_name,
        "formatted_date": formatted_date,
        "prev_month_name": prev_month_name,
        "next_month_name": next_month_name,
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
        intent_exists = OpsIntent.objects.filter(
            member=request.user, date=day_date
        ).exists()

    # Pull all intents for the day
    intents = (
        OpsIntent.objects.filter(date=day_date)
        .select_related("member")
        .order_by("member__last_name")
    )

    # Check for instruction-specific intent
    instruction_intent_count = sum(
        1 for i in intents if "instruction" in i.available_as
    )
    tow_count = sum(
        1 for i in intents if "club" in i.available_as or "private" in i.available_as
    )

    show_surge_alert = instruction_intent_count > 3
    show_tow_surge_alert = tow_count >= 6

    return render(
        request,
        "duty_roster/calendar_day_modal.html",
        {
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
        },
    )


@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils import timezone

    day_date = date(year, month, day)

    # remember prior intent so we only email on true cancellations
    old_intent = OpsIntent.objects.filter(member=request.user, date=day_date).first()
    old_available = old_intent.available_as if old_intent else []

    available_as = request.POST.getlist("available_as") or []

    # enforce 14-day rule for instruction
    if "instruction" in available_as:
        days_until = (day_date - timezone.now().date()).days
        if days_until > 14:
            response = '<p class="text-red-700">⏰ You can only request instruction within 14 days of your duty date.</p>'
            response += (
                f'<form hx-get="{request.path}form/" '
                'hx-post="{request.path}"'
                'hx-target="#ops-intent-response" hx-swap="innerHTML">'
                '<button type="submit" class="btn btn-sm btn-primary">'
                "🛩️ I Plan to Fly This Day</button></form>"
            )
            return HttpResponse(response)

    # SIGNUP FLOW
    if available_as:
        OpsIntent.objects.update_or_create(
            member=request.user, date=day_date, defaults={"available_as": available_as}
        )

        # who’s signed up now?
        intents = OpsIntent.objects.filter(date=day_date)
        students = [
            i.member.full_display_name
            for i in intents
            if "instruction" in i.available_as
        ]

        assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
        duty_inst = assignment.instructor
        surge_inst = assignment.surge_instructor

        # do we need surge? (you choose your own threshold)
        need_surge = len(students) > 3

        # build the email
        subject = f"Instruction Signup on {day_date:%b %d}"
        body = (
            f"Student {request.user.full_display_name} signed up for instruction on "
            f"{day_date:%B %d, %Y}.\n"
            "Others signed up: " + (", ".join(students) or "None") + "\n"
        )
        if need_surge:
            body += "Surge instructor may be needed.\n"

        # recipients: duty instructor plus (if exists) surge instructor
        recipients = []
        if duty_inst and duty_inst.email:
            recipients.append(duty_inst.email)
        if surge_inst and surge_inst.email:
            recipients.append(surge_inst.email)

        if recipients:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=True,
            )

        response = '<p class="text-green-700">✅ You’re now marked as planning to fly this day.</p>'
        response += (
            f'<button hx-post="{request.path}" '
            'hx-target="#ops-intent-response" '
            'hx-swap="innerHTML" '
            'class="btn btn-sm btn-danger">'
            "Cancel Intent</button>"
        )

    # CANCELLATION FLOW
    else:
        # only email cancellation if they had previously requested instruction
        if "instruction" in old_available:
            assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
            duty_inst = assignment.instructor
            if duty_inst and duty_inst.email:
                subject = f"Instruction Cancellation on {day_date:%b %d}"
                body = (
                    f"Student {request.user.full_display_name} cancelled their instruction signup "
                    f"for {day_date:%B %d, %Y}."
                )
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [duty_inst.email],
                    fail_silently=True,
                )

        OpsIntent.objects.filter(member=request.user, date=day_date).delete()
        response = '<p class="text-gray-700">❌ You’ve removed your intent to fly.</p>'
        response += (
            f'<form hx-get="{request.path}form/" '
            'hx-target="#ops-intent-response" hx-swap="innerHTML">'
            '<button type="submit" class="btn btn-sm btn-primary">'
            "🛩️ I Plan to Fly This Day</button></form>"
        )

    # still check for surges across the board
    maybe_notify_surge_instructor(day_date)
    maybe_notify_surge_towpilot(day_date)

    return HttpResponse(response)


def ops_intent_form(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=403)

    day_date = date(year, month, day)
    return render(
        request,
        "duty_roster/ops_intent_form.html",
        {
            "day": day_date,
            "available_activities": OpsIntent.AVAILABLE_ACTIVITIES,
        },
    )


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
            recipient_list=["instructors@default.manage2soar.com"],
            fail_silently=True,
        )
        assignment.surge_notified = True
        assignment.save()


def maybe_notify_surge_towpilot(day_date):
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
    if assignment.tow_surge_notified:
        return

    intents = OpsIntent.objects.filter(date=day_date)
    tow_count = sum(
        1 for i in intents if "club" in i.available_as or "private" in i.available_as
    )

    if tow_count >= 6:
        send_mail(
            subject=f"Surge Tow Pilot May Be Needed - {day_date.strftime('%A, %B %d')}",
            message=f"There are currently {tow_count} pilots planning flights requiring tows on {day_date.strftime('%A, %B %d, %Y')}.\n\nYou may want to coordinate a surge tow pilot.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=["towpilots@default.manage2soar.com"],
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

    return render(
        request,
        "duty_roster/assignment_edit_form.html",
        {
            "form": form,
            "day": day_date,
        },
    )


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

        # Return HTMX response to refresh calendar body with specific month context
        return calendar_refresh_response(year, month)
    else:
        return render(
            request,
            "duty_roster/assignment_edit_form.html",
            {
                "form": form,
                "day": day_date,
            },
        )


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
        },
    )
    notify_ops_status(assignment)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


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

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_dutyofficer_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    member = request.user
    if not member.duty_officer:
        title = get_role_title("duty_officer") or "Duty Officer"
        return HttpResponseForbidden(f"You are not a {title.lower()}.")

    if not assignment.duty_officer:
        assignment.duty_officer = member

        assignment.save()
        notify_ops_status(assignment)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


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

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_ado_signup(request, year, month, day):
    day_obj = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=day_obj)

    member = request.user
    if not member.assistant_duty_officer:
        title = get_role_title("assistant_duty_officer") or "Assistant Duty Officer"
        return HttpResponseForbidden(f"You are not an {title.lower()}.")

    if not assignment.assistant_duty_officer:
        assignment.assistant_duty_officer = member
        assignment.save()

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


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
        return HttpResponseBadRequest(
            "Cancellation reason is required and must be at least 10 characters."
        )

    canceller_name = request.user.full_display_name

    body = (
        f"Operations for {ops_date.strftime('%A, %B %d, %Y')} have been canceled.\n\n"
        f"Canceled by: {canceller_name}\n\n"
        f"Reason:\n{reason}\n\n"
        f"Stay safe and we'll see you next time!"
    )

    # Send to members@default.manage2soar.com
    send_mail(
        subject=f"[Manage2Soar] Operations Canceled - {ops_date.strftime('%B %d')}",
        message=body,
        from_email="noreply@default.manage2soar.com",
        recipient_list=["members@default.manage2soar.com"],
    )

    # Delete the DutyAssignment entry
    assignment.delete()

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@active_member_required
def calendar_cancel_ops_modal(request, year, month, day):
    from datetime import date

    ops_date = date(int(year), int(month), int(day))
    assignment = get_object_or_404(DutyAssignment, date=ops_date)

    return render(
        request, "duty_roster/calendar_cancel_modal.html", {"assignment": assignment}
    )


def is_rostermeister(user):
    return user.is_authenticated and user.rostermeister


@active_member_required
@user_passes_test(is_rostermeister)
def propose_roster(request):
    year = request.POST.get("year") or request.GET.get("year")
    month = request.POST.get("month") or request.GET.get("month")
    if year and month:
        year, month = int(year), int(month)
    else:
        today = timezone.now().date()
        year, month = today.year, today.month
    incomplete = False

    # Get site config and determine which roles to schedule
    siteconfig = SiteConfiguration.objects.first()
    enabled_roles = []
    if siteconfig:
        if getattr(siteconfig, "schedule_instructors", False):
            enabled_roles.append("instructor")
        if getattr(siteconfig, "schedule_duty_officers", False):
            enabled_roles.append("duty_officer")
        if getattr(siteconfig, "schedule_assistant_duty_officers", False):
            enabled_roles.append("assistant_duty_officer")
        if getattr(siteconfig, "schedule_tow_pilots", False):
            enabled_roles.append("towpilot")
    else:
        enabled_roles = DEFAULT_ROLES.copy()

    if not enabled_roles:
        # No scheduling for this club
        return render(
            request,
            "duty_roster/propose_roster.html",
            {
                "draft": [],
                "year": year,
                "month": month,
                "incomplete": False,
                "enabled_roles": [],
                "no_scheduling": True,
            },
        )

    if request.method == "POST":
        action = request.POST.get("action")
        draft = request.session.get("proposed_roster", [])
        if action == "roll":
            raw = generate_roster(year, month)
            if not raw:
                cal = calendar.Calendar()
                weekend = [
                    d
                    for d in cal.itermonthdates(year, month)
                    if d.month == month and d.weekday() in (5, 6)
                ]
                raw = [
                    {"date": d, "slots": {r: None for r in enabled_roles}}
                    for d in weekend
                ]
                incomplete = True
            draft = [
                {
                    "date": e["date"].isoformat(),
                    "slots": {r: e["slots"].get(r) for r in enabled_roles},
                }
                for e in raw
            ]
            request.session["proposed_roster"] = draft

        elif action == "publish":
            from .models import DutyAssignment

            default_field = Airfield.objects.get(pk=settings.DEFAULT_AIRFIELD_ID)
            DutyAssignment.objects.filter(date__year=year, date__month=month).delete()

            for e in request.session.get("proposed_roster", []):
                edt = dt_date.fromisoformat(e["date"])
                assignment_data = {
                    "date": edt,
                    "location": default_field,
                }
                for role, mem in e["slots"].items():
                    field_name = ROLE_FIELD_MAP.get(role)
                    if field_name and mem:
                        assignment_data[field_name] = Member.objects.get(pk=mem)

                DutyAssignment.objects.create(**assignment_data)

            request.session.pop("proposed_roster", None)
            messages.success(request, f"Duty roster published for {month}/{year}.")
            return redirect("duty_roster:duty_calendar_month", year=year, month=month)

        elif action == "cancel":
            request.session.pop("proposed_roster", None)
            return redirect("duty_roster:duty_calendar")
    else:
        raw = generate_roster(year, month)
        if not raw:
            cal = calendar.Calendar()
            weekend = [
                d
                for d in cal.itermonthdates(year, month)
                if d.month == month and d.weekday() in (5, 6)
            ]
            raw = [
                {"date": d, "slots": {r: None for r in enabled_roles}} for d in weekend
            ]
            incomplete = True
        draft = [
            {
                "date": e["date"].isoformat(),
                "slots": {r: e["slots"].get(r) for r in enabled_roles},
            }
            for e in raw
        ]
        request.session["proposed_roster"] = draft
    display = [
        {"date": dt_date.fromisoformat(e["date"]), "slots": e["slots"]}
        for e in request.session.get("proposed_roster", [])
    ]
    return render(
        request,
        "duty_roster/propose_roster.html",
        {
            "draft": display,
            "year": year,
            "month": month,
            "incomplete": incomplete,
            "enabled_roles": enabled_roles,
            "no_scheduling": False,
        },
    )


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
                days.append({"date": d, "slots": None})
            else:
                assignments = DutySlot.objects.filter(duty_day__date=d)
                slots = {role: "" for role in DEFAULT_ROLES}
                for a in assignments:
                    slots[a.role] = a.member.full_display_name
                days.append({"date": d, "slots": slots})
        grid.append(days)
    context = {
        "weeks": grid,
        "year": year,
        "month": month,
        "DEFAULT_ROLES": DEFAULT_ROLES,
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "duty_roster/partials/calendar_grid.html", context)
    return render(request, "duty_roster/calendar.html", context)


@user_passes_test(lambda u: u.is_authenticated and (
    u.rostermeister or u.member_manager or u.director or u.is_superuser
))
def duty_delinquents_detail(request):
    """
    Detailed view of members who haven't been performing duty.
    Accessible only to rostermeister, member-meister, directors, and superusers.
    """
    from datetime import timedelta
    from django.db.models import Q, Count
    from django.utils.timezone import now
    from logsheet.models import Flight
    from members.models import Member
    from duty_roster.models import DutySlot, DutyAssignment, MemberBlackout, DutyPreference

    # Parameters (could be made configurable via URL params)
    lookback_months = 12
    min_flights = 3
    min_membership_months = 3

    # Calculate date ranges
    today = now().date()
    duty_cutoff_date = today - timedelta(days=lookback_months * 30)
    membership_cutoff_date = today - timedelta(days=min_membership_months * 30)
    recent_flight_cutoff = today - timedelta(days=lookback_months * 30)

    # Step 1: Find all members who have been in the club for 3+ months
    eligible_members = Member.objects.filter(
        Q(joined_club__lt=membership_cutoff_date) | Q(joined_club__isnull=True),
        membership_status__in=['Full Member', 'Student Member', 'Life Member']
    ).exclude(
        membership_status__in=['Inactive', 'Terminated', 'Suspended']
    )

    # Step 2: Find members who have been actively flying
    active_flyers = eligible_members.filter(
        flights_as_pilot__logsheet__log_date__gte=recent_flight_cutoff,
        flights_as_pilot__logsheet__finalized=True
    ).annotate(
        flight_count=Count('flights_as_pilot', distinct=True)
    ).filter(
        flight_count__gte=min_flights
    ).distinct()

    # Step 3: Build detailed report for each active flyer
    duty_delinquents = []

    for member in active_flyers:
        # Check if member has performed any duty in the lookback period
        duty_performed = _has_performed_duty_detailed(member, duty_cutoff_date)

        if not duty_performed['has_duty']:
            # Get member's flight details
            flight_count = Flight.objects.filter(
                pilot=member,
                logsheet__log_date__gte=recent_flight_cutoff,
                logsheet__finalized=True
            ).count()

            # Get most recent flight
            recent_flight = Flight.objects.filter(
                pilot=member,
                logsheet__log_date__gte=recent_flight_cutoff,
                logsheet__finalized=True
            ).order_by('-logsheet__log_date').first()

            # Get member's roles
            roles = []
            if member.duty_officer:
                roles.append('Duty Officer')
            if member.assistant_duty_officer:
                roles.append('Assistant Duty Officer')
            if member.instructor:
                roles.append('Instructor')
            if member.towpilot:
                roles.append('Tow Pilot')

            # Get blackout information (current and recent)
            current_blackouts = MemberBlackout.objects.filter(
                member=member,
                date__gte=today,
                date__lte=today + timedelta(days=90)  # Next 3 months
            ).order_by('date')

            recent_blackouts = MemberBlackout.objects.filter(
                member=member,
                date__gte=duty_cutoff_date,
                date__lt=today
            ).order_by('-date')[:5]  # Last 5 blackouts in the period

            # Get duty preferences and suspension info
            try:
                duty_preference = DutyPreference.objects.get(member=member)
                is_suspended = duty_preference.scheduling_suspended
                suspension_reason = duty_preference.suspended_reason
                dont_schedule = duty_preference.dont_schedule
            except DutyPreference.DoesNotExist:
                is_suspended = False
                suspension_reason = None
                dont_schedule = False

            duty_delinquents.append({
                'member': member,
                'flight_count': flight_count,
                'most_recent_flight': recent_flight.logsheet.log_date if recent_flight else None,
                'most_recent_flight_logsheet': recent_flight.logsheet if recent_flight else None,
                'membership_duration': _calculate_membership_duration(member, today),
                'eligible_roles': roles,
                'last_duty_info': duty_performed,
                'current_blackouts': current_blackouts,
                'recent_blackouts': recent_blackouts,
                'is_suspended': is_suspended,
                'suspension_reason': suspension_reason,
                'dont_schedule': dont_schedule,
            })

    # Sort by last name for easy navigation
    duty_delinquents.sort(key=lambda x: x['member'].last_name.lower())

    context = {
        'duty_delinquents': duty_delinquents,
        'lookback_months': lookback_months,
        'min_flights': min_flights,
        'min_membership_months': min_membership_months,
        'duty_cutoff_date': duty_cutoff_date,
        'report_date': today,
        'total_count': len(duty_delinquents),
    }

    return render(request, 'duty_roster/duty_delinquents_detail.html', context)


def _has_performed_duty_detailed(member, cutoff_date):
    """
    Check if member has performed any duty since cutoff_date with detailed info.
    For instructors and tow pilots, checks actual flight participation.
    For duty officers and assistant duty officers, checks scheduled assignments.
    """
    from django.db.models import Q
    from duty_roster.models import DutySlot, DutyAssignment
    from logsheet.models import Flight

    # Check actual flight participation for instructors and tow pilots
    # This is more important than just being scheduled

    # Check if they performed instruction (appeared as instructor in flights)
    instruction_flights = Flight.objects.filter(
        instructor=member,
        logsheet__log_date__gte=cutoff_date,
        logsheet__finalized=True
    ).order_by('-logsheet__log_date')

    latest_instruction = instruction_flights.first()
    if latest_instruction is not None:
        return {
            'has_duty': True,
            'last_duty_date': latest_instruction.logsheet.log_date,
            'last_duty_role': 'Instructor (Flight)',
            'last_duty_type': 'Flight Activity',
            'flight_count': instruction_flights.count()
        }

    # Check if they performed towing (appeared as tow pilot in flights)
    towing_flights = Flight.objects.filter(
        tow_pilot=member,
        logsheet__log_date__gte=cutoff_date,
        logsheet__finalized=True
    ).order_by('-logsheet__log_date')

    latest_towing = towing_flights.first()
    if latest_towing is not None:
        return {
            'has_duty': True,
            'last_duty_date': latest_towing.logsheet.log_date,
            'last_duty_role': 'Tow Pilot (Flight)',
            'last_duty_type': 'Flight Activity',
            'flight_count': towing_flights.count()
        }

    # For duty officers and assistant duty officers, check scheduled assignments
    # (since this is the only way to track their participation)

    # Check DutySlot assignments (newer system) - only for DO/ADO roles
    duty_officer_slots = DutySlot.objects.filter(
        member=member,
        duty_day__date__gte=cutoff_date,
        role__in=['duty_officer', 'assistant_duty_officer']
    ).order_by('-duty_day__date')

    latest_do_slot = duty_officer_slots.first()
    if latest_do_slot is not None:
        role_display = 'Duty Officer' if latest_do_slot.role == 'duty_officer' else 'Assistant Duty Officer'
        return {
            'has_duty': True,
            'last_duty_date': latest_do_slot.duty_day.date,
            'last_duty_role': f'{role_display} (Scheduled)',
            'last_duty_type': 'DutySlot'
        }

    # Check DutyAssignment assignments (older system) - only for DO/ADO
    duty_assignments = DutyAssignment.objects.filter(
        Q(duty_officer=member) | Q(assistant_duty_officer=member),
        date__gte=cutoff_date
    ).order_by('-date')

    latest_do_assignment = duty_assignments.first()
    if latest_do_assignment is not None:
        role = []
        if latest_do_assignment.duty_officer == member:
            role.append('Duty Officer')
        if latest_do_assignment.assistant_duty_officer == member:
            role.append('Assistant Duty Officer')

        return {
            'has_duty': True,
            'last_duty_date': latest_do_assignment.date,
            'last_duty_role': f"{', '.join(role)} (Scheduled)",
            'last_duty_type': 'DutyAssignment'
        }

    # Also check if instructors/tow pilots were scheduled (less important but still relevant)
    scheduled_slots = DutySlot.objects.filter(
        member=member,
        duty_day__date__gte=cutoff_date,
        role__in=['instructor', 'surge_instructor', 'tow_pilot', 'surge_tow_pilot']
    ).order_by('-duty_day__date')

    latest_scheduled = scheduled_slots.first()
    if latest_scheduled is not None:
        role_map = {
            'instructor': 'Instructor',
            'surge_instructor': 'Surge Instructor',
            'tow_pilot': 'Tow Pilot',
            'surge_tow_pilot': 'Surge Tow Pilot'
        }
        return {
            'has_duty': True,
            'last_duty_date': latest_scheduled.duty_day.date,
            'last_duty_role': f"{role_map[latest_scheduled.role]} (Scheduled Only)",
            'last_duty_type': 'DutySlot - Scheduled'
        }

    return {
        'has_duty': False,
        'last_duty_date': None,
        'last_duty_role': None,
        'last_duty_type': None
    }


def _calculate_membership_duration(member, today):
    """Calculate how long the member has been in the club"""
    if member.joined_club:
        delta = today - member.joined_club
        years = delta.days // 365
        months = (delta.days % 365) // 30

        if years > 0:
            return f"{years} year(s), {months} month(s)"
        else:
            return f"{months} month(s)"
    else:
        return "Unknown (no join date)"
