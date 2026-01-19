import calendar
import json
import logging
from collections import defaultdict
from datetime import date
from datetime import date as dt_date
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.db import models
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import format_html
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from duty_roster.utils.email import (
    get_email_config,
    get_mailing_list,
    notify_ops_status,
)
from logsheet.models import Airfield
from members.constants.membership import DEFAULT_ROLES, ROLE_FIELD_MAP
from members.decorators import active_member_required
from members.models import Member
from members.utils.membership import get_active_membership_statuses
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url

from .forms import DutyAssignmentForm, DutyPreferenceForm
from .models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
    OpsIntent,
)
from .roster_generator import generate_roster, is_within_operational_season

logger = logging.getLogger("duty_roster.views")


def calendar_refresh_response(year, month):
    """Helper function to create HTMX response that refreshes calendar with month context"""
    trigger_data = {"refreshCalendar": {"year": int(year), "month": int(month)}}
    return HttpResponse(headers={"HX-Trigger": json.dumps(trigger_data)})


def roster_home(request):
    return HttpResponse("Duty Roster Home")


@active_member_required
@never_cache
def blackout_manage(request):
    member = request.user
    preference, _ = DutyPreference.objects.get_or_create(member=member)

    max_choices = preference._meta.get_field("max_assignments_per_month").choices

    existing = MemberBlackout.objects.filter(member=member)
    existing_dates = set(b.date for b in existing)

    today = now().date()

    def generate_calendar(year, month):
        cal = calendar.Calendar(firstweekday=6)  # 6 = Sunday as first day of week
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

    # Create optgroups for member pairing fields (similar to logsheet forms)
    active_statuses = get_active_membership_statuses()

    # Active members (excluding current user)
    active_members = (
        Member.objects.filter(membership_status__in=active_statuses)
        .exclude(id=member.id)
        .order_by("last_name", "first_name")
    )

    # Non-active members (excluding current user)
    inactive_members = (
        Member.objects.exclude(membership_status__in=active_statuses)
        .exclude(id=member.id)
        .filter(is_active=True)
        .order_by("last_name", "first_name")
    )

    # Build optgroups for template
    member_optgroups = []
    if active_members.exists():
        member_optgroups.append(("Active Members", active_members))
    if inactive_members.exists():
        member_optgroups.append(("Inactive Members", inactive_members))

    # For backward compatibility, keep all_other for any legacy template usage
    all_other = Member.objects.exclude(id=member.id).filter(is_active=True)

    if request.method == "POST":
        blackout_dates = set(
            date.fromisoformat(d) for d in request.POST.getlist("blackout_dates")
        )

        note = request.POST.get("default_note", "").strip()

        to_add = blackout_dates - existing_dates
        to_remove = existing_dates - blackout_dates

        for d in to_add:
            MemberBlackout.objects.get_or_create(
                member=member, date=d, defaults={"note": note}
            )

        for d in to_remove:
            MemberBlackout.objects.filter(member=member, date=d).delete()

        # Always redirect after blackout processing, regardless of duty preference validation
        # This ensures blackout changes are immediately visible
        if to_add or to_remove:
            messages.success(request, "Blackout dates updated successfully.")

        # Try to process duty preferences, but don't let it block blackout updates
        form = DutyPreferenceForm(request.POST, member=member)
        if not form.is_valid():
            # Add form errors to messages so user can see them
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        if form.is_valid():
            data = form.cleaned_data
            DutyPreference.objects.update_or_create(
                member=member,
                defaults={
                    "preferred_day": data["preferred_day"],
                    "dont_schedule": data["dont_schedule"],
                    "scheduling_suspended": data["scheduling_suspended"],
                    "suspended_reason": data["suspended_reason"],
                    # Use 'or 0' to convert None to 0, as the database fields don't allow NULL
                    "instructor_percent": data["instructor_percent"] or 0,
                    "duty_officer_percent": data["duty_officer_percent"] or 0,
                    "ado_percent": data["ado_percent"] or 0,
                    "towpilot_percent": data["towpilot_percent"] or 0,
                    "max_assignments_per_month": data["max_assignments_per_month"],
                    "allow_weekend_double": data.get("allow_weekend_double", False),
                    "comment": data["comment"],
                },
            )
            DutyPairing.objects.filter(member=member).delete()
            DutyAvoidance.objects.filter(member=member).delete()
            for m in data.get("pair_with", []):
                DutyPairing.objects.create(member=member, pair_with=m)
            for m in data.get("avoid_with", []):
                DutyAvoidance.objects.create(member=member, avoid_with=m)

            messages.success(request, "Duty preferences saved successfully.")

        # Always redirect after POST to prevent double-submission and ensure fresh page load
        return redirect("duty_roster:blackout_manage")
    else:
        initial = {
            "preferred_day": preference.preferred_day,
            "dont_schedule": preference.dont_schedule,
            "scheduling_suspended": preference.scheduling_suspended,
            "suspended_reason": preference.suspended_reason,
            "instructor_percent": preference.instructor_percent,
            "duty_officer_percent": preference.duty_officer_percent,
            "ado_percent": preference.ado_percent,
            "towpilot_percent": preference.towpilot_percent,
            "max_assignments_per_month": preference.max_assignments_per_month,
            "allow_weekend_double": preference.allow_weekend_double,
            "comment": preference.comment,
            "pair_with": pair_with,
            "avoid_with": avoid_with,
        }
        form = DutyPreferenceForm(initial=initial, member=member)

    response = render(
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
            "member_optgroups": member_optgroups,
            "form": form,
            # pass the choices into the template:
            "max_assignments_choices": max_choices,
        },
    )

    return response


def get_adjacent_months(year, month):
    # Previous month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    # Next month
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return prev_year, prev_month, next_year, next_month


def get_surge_thresholds():
    """
    Get surge thresholds from SiteConfiguration with sensible defaults.
    Returns tuple: (tow_surge_threshold, instruction_surge_threshold)

    This function uses Django's cache framework to avoid redundant database queries.
    The SiteConfiguration is cached for 60 seconds. If not present, it is fetched
    from the database and then cached. Adjust the TTL as needed for your use case.

    Note on threshold semantics (Issue #403):
    Both thresholds trigger AT or ABOVE the specified value (using >= comparison).
    This makes both thresholds semantically consistent. Previously, instruction used
    > 3 (triggering at 4+), while tow used >= 6. The new defaults (instruction=4, tow=6)
    maintain backward compatibility while providing more intuitive threshold behavior.
    """
    config = cache.get("siteconfig_instance")
    if config is None:
        config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", config, timeout=60)
    tow_surge_threshold = config.tow_surge_threshold if config else 6
    instruction_surge_threshold = config.instruction_surge_threshold if config else 4
    return tow_surge_threshold, instruction_surge_threshold


def duty_calendar_view(request, year=None, month=None):
    today = date.today()
    year = int(year) if year else today.year
    month = int(month) if month else today.month

    # Get site config for surge thresholds
    tow_surge_threshold, instruction_surge_threshold = get_surge_thresholds()

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(year, month)
    first_visible_day = weeks[0][0]
    last_visible_day = weeks[-1][-1]
    assignments = DutyAssignment.objects.filter(
        date__range=(first_visible_day, last_visible_day)
    ).order_by("date")

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
            "instructor": instruction_count[day_date] >= instruction_surge_threshold,
            "towpilot": tow_count[day_date] >= tow_surge_threshold,
        }

    # Add formatted month and date context
    month_name = calendar.month_name[month]
    formatted_date = f"{month_name} {year}"

    # Get previous and next month names for navigation
    prev_month_name = calendar.month_name[prev_month]
    next_month_name = calendar.month_name[next_month]

    # Check if there are any upcoming assignments for the agenda view
    has_upcoming_assignments = any(
        day.month == month and day >= today for day in assignments_by_date.keys()
    )

    context = {
        "year": year,
        "month": month,
        "month_name": month_name,
        "formatted_date": formatted_date,
        "prev_month_name": prev_month_name,
        "next_month_name": next_month_name,
        "weeks": weeks,
        "assignments_by_date": assignments_by_date,
        "has_upcoming_assignments": has_upcoming_assignments,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
        "surge_needed_by_date": surge_needed_by_date,
        "tow_surge_threshold": tow_surge_threshold,
        "instruction_surge_threshold": instruction_surge_threshold,
    }

    if request.htmx:
        return render(request, "duty_roster/_calendar_body.html", context)
    return render(request, "duty_roster/calendar.html", context)


def calendar_day_detail(request, year, month, day):
    day_date = date(year, month, day)
    assignment = DutyAssignment.objects.filter(date=day_date).first()

    # Get site config for surge thresholds
    tow_surge_threshold, instruction_surge_threshold = get_surge_thresholds()

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

    show_surge_alert = instruction_intent_count >= instruction_surge_threshold
    show_tow_surge_alert = tow_count >= tow_surge_threshold

    # Check if user already has a non-cancelled instruction request for this day
    user_has_instruction_request = False
    instruction_request_form = None
    if request.user.is_authenticated and assignment:
        from .forms import InstructionRequestForm
        from .models import InstructionSlot

        user_has_instruction_request = (
            InstructionSlot.objects.filter(
                assignment=assignment,
                student=request.user,
            )
            .exclude(status="cancelled")
            .exists()
        )

        # Only show form if user doesn't already have a request and an instructor is assigned
        if (
            not user_has_instruction_request
            and (assignment.instructor or assignment.surge_instructor)
            and day_date >= date.today()
        ):
            instruction_request_form = InstructionRequestForm(
                assignment=assignment, student=request.user
            )

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
            "user_has_instruction_request": user_has_instruction_request,
            "instruction_request_form": instruction_request_form,
        },
    )


@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    from django.conf import settings
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
            response = format_html(
                '<p class="text-red-700">⏰ You can only request instruction '
                "within 14 days of your duty date.</p>"
                '<form hx-get="{}form/" '
                'hx-post="{}" '
                'hx-target="#ops-intent-response" hx-swap="innerHTML">'
                '<button type="submit" class="btn btn-sm btn-primary">'
                "🛩️ I Plan to Fly This Day</button></form>",
                request.path,
                request.path,
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

        # recipients: duty instructor plus (if exists) surge instructor
        recipients = []
        if duty_inst and duty_inst.email:
            recipients.append(duty_inst.email)
        if surge_inst and surge_inst.email:
            recipients.append(surge_inst.email)

        if recipients:
            # Prepare template context
            email_config = get_email_config()

            context = {
                "student_name": request.user.full_display_name,
                "instructor_name": (
                    duty_inst.full_display_name if duty_inst else "Instructor"
                ),
                "ops_date": day_date.strftime("%A, %B %d, %Y"),
                "club_name": email_config["club_name"],
                "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
                "roster_url": email_config["roster_url"],
            }

            # Render email templates
            html_message = render_to_string(
                "duty_roster/emails/ops_intent_notification.html", context
            )
            text_message = render_to_string(
                "duty_roster/emails/ops_intent_notification.txt", context
            )

            send_mail(
                subject=f"[{email_config['club_name']}] Student Plans to Fly - {day_date:%b %d}",
                message=text_message,
                from_email=email_config["from_email"],
                recipient_list=recipients,
                html_message=html_message,
                fail_silently=True,
            )

        response = format_html(
            '<p class="text-green-700">✅ You\'re now marked as planning to fly '
            "this day.</p>"
            '<button hx-post="{}" '
            'hx-target="#ops-intent-response" '
            'hx-swap="innerHTML" '
            'class="btn btn-sm btn-danger">'
            "Cancel Intent</button>",
            request.path,
        )

    # CANCELLATION FLOW
    else:
        # only email cancellation if they had previously requested instruction
        if "instruction" in old_available:
            assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
            duty_inst = assignment.instructor
            if duty_inst and duty_inst.email:
                # Prepare template context
                email_config = get_email_config()

                context = {
                    "student_name": request.user.full_display_name,
                    "instructor_name": duty_inst.full_display_name,
                    "ops_date": day_date.strftime("%A, %B %d, %Y"),
                    "club_name": email_config["club_name"],
                    "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
                    "roster_url": email_config["roster_url"],
                }

                # Render email templates
                html_message = render_to_string(
                    "duty_roster/emails/instruction_cancellation.html", context
                )
                text_message = render_to_string(
                    "duty_roster/emails/instruction_cancellation.txt", context
                )

                send_mail(
                    subject=f"[{email_config['club_name']}] Instruction Cancellation - {day_date:%b %d}",
                    message=text_message,
                    from_email=email_config["from_email"],
                    recipient_list=[duty_inst.email],
                    html_message=html_message,
                    fail_silently=True,
                )

        OpsIntent.objects.filter(member=request.user, date=day_date).delete()
        response = format_html(
            '<p class="text-gray-700">❌ You\'ve removed your intent to fly.</p>'
            '<form hx-get="{}form/" '
            'hx-target="#ops-intent-response" hx-swap="innerHTML">'
            '<button type="submit" class="btn btn-sm btn-primary">'
            "🛩️ I Plan to Fly This Day</button></form>",
            request.path,
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

    # Get surge threshold
    _, instruction_surge_threshold = get_surge_thresholds()

    intents = OpsIntent.objects.filter(date=day_date)
    instruction_count = sum(1 for i in intents if "instruction" in i.available_as)

    if instruction_count >= instruction_surge_threshold:
        # Prepare template context
        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "INSTRUCTORS_MAILING_LIST", "instructors", email_config["config"]
        )

        context = {
            "student_count": instruction_count,
            "ops_date": day_date.strftime("%A, %B %d, %Y"),
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
            "roster_url": email_config["roster_url"],
        }

        # Render email templates
        html_message = render_to_string(
            "duty_roster/emails/surge_instructor_alert.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_instructor_alert.txt", context
        )

        send_mail(
            subject=f"[{email_config['club_name']}] Surge Instructor May Be Needed - {day_date.strftime('%A, %B %d')}",
            message=text_message,
            from_email=email_config["from_email"],
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
        assignment.surge_notified = True
        assignment.save()


def maybe_notify_surge_towpilot(day_date):
    assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
    if assignment.tow_surge_notified:
        return

    # Get surge threshold
    tow_surge_threshold, _ = get_surge_thresholds()

    intents = OpsIntent.objects.filter(date=day_date)
    tow_count = sum(
        1 for i in intents if "club" in i.available_as or "private" in i.available_as
    )

    if tow_count >= tow_surge_threshold:
        # Prepare template context
        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "TOWPILOTS_MAILING_LIST", "towpilots", email_config["config"]
        )

        context = {
            "tow_count": tow_count,
            "ops_date": day_date.strftime("%A, %B %d, %Y"),
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
            "roster_url": email_config["roster_url"],
        }

        # Render email templates
        html_message = render_to_string(
            "duty_roster/emails/surge_towpilot_alert.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_towpilot_alert.txt", context
        )

        send_mail(
            subject=f"[{email_config['club_name']}] Surge Tow Pilot May Be Needed - {day_date.strftime('%A, %B %d')}",
            message=text_message,
            from_email=email_config["from_email"],
            recipient_list=recipient_list,
            html_message=html_message,
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

    # Check if user is authenticated
    if not request.user.is_authenticated:
        html = render_to_string(
            "duty_roster/calendar_ad_hoc_login_required.html",
            {"date": day_obj},
            request=request,
        )
        return HttpResponse(html)

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

    # Check if user is authenticated
    if not request.user.is_authenticated:
        return HttpResponse(
            "You must be signed in to propose and edit operations", status=403
        )

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
        notify_ops_status(assignment)

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
        notify_ops_status(assignment)

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

    # Get configuration
    email_config = get_email_config()
    recipient_list = get_mailing_list(
        "MEMBERS_MAILING_LIST", "members", email_config["config"]
    )

    # Render email
    context = {
        "ops_date": ops_date.strftime("%A, %B %d, %Y"),
        "canceller_name": canceller_name,
        "cancel_reason": reason,
        "club_name": email_config["club_name"],
        "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
        "roster_url": email_config["roster_url"],
    }
    html_message = render_to_string(
        "duty_roster/emails/operations_cancelled.html", context
    )
    text_message = render_to_string(
        "duty_roster/emails/operations_cancelled.txt", context
    )

    # Send email
    send_mail(
        subject=f"[{email_config['club_name']}] Operations Canceled - {ops_date.strftime('%B %d')}",
        message=text_message,
        from_email=email_config["from_email"],
        recipient_list=recipient_list,
        html_message=html_message,
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

    # Get operational calendar information for display
    operational_info = {}
    filtered_dates = []
    if siteconfig:
        from .roster_generator import get_operational_season_bounds

        try:
            season_start, season_end = get_operational_season_bounds(year)

            # Only show operational info if we have filtering enabled
            if season_start or season_end:
                if season_start:
                    operational_info["season_start"] = season_start
                if season_end:
                    operational_info["season_end"] = season_end

                # Find which dates would be filtered out
                cal = calendar.Calendar()
                all_weekend_dates = [
                    d
                    for d in cal.itermonthdates(year, month)
                    if d.month == month and d.weekday() in (5, 6)
                ]
                filtered_dates = [
                    d for d in all_weekend_dates if not is_within_operational_season(d)
                ]
        except Exception as e:
            logger.warning(f"Error calculating operational season info: {e}")

    if request.method == "POST":
        action = request.POST.get("action")
        draft = request.session.get("proposed_roster", [])

        if action == "remove_dates":
            # Handle removing specific dates from the roster
            dates_to_remove = request.POST.getlist("remove_date")
            if dates_to_remove:
                # Convert Y-m-d strings to date objects for reliable comparison
                dates_to_remove_set = set()
                for date_str in dates_to_remove:
                    try:
                        dates_to_remove_set.add(dt_date.fromisoformat(date_str))
                    except ValueError:
                        # Handle any malformed dates gracefully
                        continue

                draft = [
                    entry
                    for entry in draft
                    if dt_date.fromisoformat(entry["date"]) not in dates_to_remove_set
                ]
                request.session["proposed_roster"] = draft
                messages.success(
                    request,
                    f"Removed {len(dates_to_remove)} date(s) from the proposed roster.",
                )

        elif action == "roll":
            raw = generate_roster(year, month)
            if not raw:
                cal = calendar.Calendar()
                weekend = [
                    d
                    for d in cal.itermonthdates(year, month)
                    if d.month == month
                    and d.weekday() in (5, 6)
                    and is_within_operational_season(d)
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
            from .utils.email import send_roster_published_notifications

            default_field = Airfield.objects.get(pk=settings.DEFAULT_AIRFIELD_ID)
            DutyAssignment.objects.filter(date__year=year, date__month=month).delete()

            created_assignments = []
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

                assignment = DutyAssignment.objects.create(**assignment_data)
                created_assignments.append(assignment)

            request.session.pop("proposed_roster", None)

            # Send ICS calendar invites to all assigned members
            if created_assignments:
                try:
                    result = send_roster_published_notifications(
                        year, month, created_assignments
                    )
                    if result["sent_count"] > 0:
                        messages.success(
                            request,
                            f"Duty roster published for {month}/{year}. "
                            f"Calendar invites sent to {result['sent_count']} member(s).",
                        )
                    else:
                        messages.success(
                            request, f"Duty roster published for {month}/{year}."
                        )
                    if result["errors"]:
                        for error in result["errors"]:
                            messages.warning(request, error)
                except Exception as e:
                    messages.success(
                        request, f"Duty roster published for {month}/{year}."
                    )
                    messages.warning(
                        request,
                        f"Could not send calendar invites: {str(e)}",
                    )
            else:
                messages.success(request, f"Duty roster published for {month}/{year}.")
                messages.info(
                    request,
                    "No duty assignments to notify, so no calendar invites were sent.",
                )

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
            "operational_info": operational_info,
            "filtered_dates": filtered_dates,
            "siteconfig": siteconfig,
        },
    )


@user_passes_test(
    lambda u: u.is_authenticated
    and (u.rostermeister or u.member_manager or u.director or u.is_superuser)
)
def duty_delinquents_detail(request):
    """
    Detailed view of members who haven't been performing duty.
    Accessible only to rostermeister, member-meister, directors, and superusers.
    """
    from datetime import timedelta

    from django.db.models import Count, Q
    from django.utils.timezone import now

    from duty_roster.models import DutyAssignment, DutyPreference, MemberBlackout
    from logsheet.models import Flight
    from members.models import Member
    from members.utils.membership import get_active_membership_statuses

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
    # Use centralized helper for active status filtering (matches email command)
    active_status_names = get_active_membership_statuses()

    eligible_members = Member.objects.filter(
        Q(joined_club__lt=membership_cutoff_date) | Q(joined_club__isnull=True),
        membership_status__in=active_status_names,  # Only active statuses
    )

    # Step 2: Find members who have been actively flying
    active_flyers = (
        eligible_members.filter(
            flights_as_pilot__logsheet__log_date__gte=recent_flight_cutoff,
            flights_as_pilot__logsheet__finalized=True,
        )
        .annotate(flight_count=Count("flights_as_pilot", distinct=True))
        .filter(flight_count__gte=min_flights)
        .distinct()
    )

    # Step 3: Build detailed report for each active flyer
    duty_delinquents = []

    for member in active_flyers:
        # Check if member has performed any duty in the lookback period
        duty_performed = _has_performed_duty_detailed(member, duty_cutoff_date)

        if not duty_performed["has_duty"]:
            # Get member's flight details
            flight_count = Flight.objects.filter(
                pilot=member,
                logsheet__log_date__gte=recent_flight_cutoff,
                logsheet__finalized=True,
            ).count()

            # Get most recent flight
            recent_flight = (
                Flight.objects.filter(
                    pilot=member,
                    logsheet__log_date__gte=recent_flight_cutoff,
                    logsheet__finalized=True,
                )
                .order_by("-logsheet__log_date")
                .first()
            )

            # Get member's roles
            roles = []
            if member.duty_officer:
                roles.append("Duty Officer")
            if member.assistant_duty_officer:
                roles.append("Assistant Duty Officer")
            if member.instructor:
                roles.append("Instructor")
            if member.towpilot:
                roles.append("Tow Pilot")

            # Get blackout information (current and recent)
            current_blackouts = MemberBlackout.objects.filter(
                member=member,
                date__gte=today,
                date__lte=today + timedelta(days=90),  # Next 3 months
            ).order_by("date")

            recent_blackouts = MemberBlackout.objects.filter(
                member=member, date__gte=duty_cutoff_date, date__lt=today
            ).order_by("-date")[
                :5
            ]  # Last 5 blackouts in the period

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

            duty_delinquents.append(
                {
                    "member": member,
                    "flight_count": flight_count,
                    "most_recent_flight": (
                        recent_flight.logsheet.log_date if recent_flight else None
                    ),
                    "most_recent_flight_logsheet": (
                        recent_flight.logsheet if recent_flight else None
                    ),
                    "membership_duration": _calculate_membership_duration(
                        member, today
                    ),
                    "eligible_roles": roles,
                    "last_duty_info": duty_performed,
                    "current_blackouts": current_blackouts,
                    "recent_blackouts": recent_blackouts,
                    "is_suspended": is_suspended,
                    "suspension_reason": suspension_reason,
                    "dont_schedule": dont_schedule,
                }
            )

    # Sort by last name for easy navigation
    duty_delinquents.sort(key=lambda x: x["member"].last_name.lower())

    context = {
        "duty_delinquents": duty_delinquents,
        "lookback_months": lookback_months,
        "min_flights": min_flights,
        "min_membership_months": min_membership_months,
        "duty_cutoff_date": duty_cutoff_date,
        "report_date": today,
        "total_count": len(duty_delinquents),
    }

    return render(request, "duty_roster/duty_delinquents_detail.html", context)


def _has_performed_duty_detailed(member, cutoff_date):
    """
    Check if member has performed any duty since cutoff_date with detailed info.
    For instructors and tow pilots, checks actual flight participation.
    For duty officers and assistant duty officers, checks scheduled assignments.
    """
    from django.db.models import Q

    from duty_roster.models import DutyAssignment
    from logsheet.models import Flight

    # Check actual flight participation for instructors and tow pilots
    # This is more important than just being scheduled
    # Check if they performed instruction (appeared as instructor in flights)
    instruction_flights = Flight.objects.filter(
        instructor=member, logsheet__log_date__gte=cutoff_date, logsheet__finalized=True
    ).order_by("-logsheet__log_date")

    latest_instruction = instruction_flights.first()
    if latest_instruction is not None:
        return {
            "has_duty": True,
            "last_duty_date": latest_instruction.logsheet.log_date,
            "last_duty_role": "Instructor (Flight)",
            "last_duty_type": "Flight Activity",
            "flight_count": instruction_flights.count(),
        }

    # Check if they performed towing (appeared as tow pilot in flights)
    towing_flights = Flight.objects.filter(
        tow_pilot=member, logsheet__log_date__gte=cutoff_date, logsheet__finalized=True
    ).order_by("-logsheet__log_date")

    latest_towing = towing_flights.first()
    if latest_towing is not None:
        return {
            "has_duty": True,
            "last_duty_date": latest_towing.logsheet.log_date,
            "last_duty_role": "Tow Pilot (Flight)",
            "last_duty_type": "Flight Activity",
            "flight_count": towing_flights.count(),
        }

    # For duty officers and assistant duty officers, check scheduled assignments
    # (since this is the only way to track their participation)

    # Check DutyAssignment assignments - for DO/ADO
    duty_assignments = DutyAssignment.objects.filter(
        Q(duty_officer=member) | Q(assistant_duty_officer=member), date__gte=cutoff_date
    ).order_by("-date")

    latest_do_assignment = duty_assignments.first()
    if latest_do_assignment is not None:
        role = []
        if latest_do_assignment.duty_officer == member:
            role.append("Duty Officer")
        if latest_do_assignment.assistant_duty_officer == member:
            role.append("Assistant Duty Officer")

        return {
            "has_duty": True,
            "last_duty_date": latest_do_assignment.date,
            "last_duty_role": f"{', '.join(role)} (Scheduled)",
            "last_duty_type": "DutyAssignment",
        }

    # Check if instructors/tow pilots were scheduled via DutyAssignment
    instructor_assignments = DutyAssignment.objects.filter(
        Q(instructor=member)
        | Q(surge_instructor=member)
        | Q(tow_pilot=member)
        | Q(surge_tow_pilot=member),
        date__gte=cutoff_date,
    ).order_by("-date")

    latest_scheduled = instructor_assignments.first()
    if latest_scheduled is not None:
        roles = []
        if latest_scheduled.instructor == member:
            roles.append("Instructor")
        if latest_scheduled.surge_instructor == member:
            roles.append("Surge Instructor")
        if latest_scheduled.tow_pilot == member:
            roles.append("Tow Pilot")
        if latest_scheduled.surge_tow_pilot == member:
            roles.append("Surge Tow Pilot")

        return {
            "has_duty": True,
            "last_duty_date": latest_scheduled.date,
            "last_duty_role": f"{', '.join(roles)} (Scheduled Only)",
            "last_duty_type": "DutyAssignment - Scheduled",
        }

    return {
        "has_duty": False,
        "last_duty_date": None,
        "last_duty_role": None,
        "last_duty_type": None,
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


# =============================================================================
# Instruction Request Views
# =============================================================================


@active_member_required
@require_POST
def request_instruction(request, year, month, day):
    """
    Student requests instruction on a specific duty day.

    This creates an InstructionSlot with status=pending, which the instructor
    can then accept or reject.
    """
    from .forms import InstructionRequestForm
    from .models import InstructionSlot

    day_date = date(year, month, day)
    assignment = get_object_or_404(DutyAssignment, date=day_date)

    # Check if day is in the past
    if day_date < date.today():
        messages.error(request, "Cannot request instruction for past dates.")
        return redirect("duty_roster:duty_calendar_month", year=year, month=month)

    form = InstructionRequestForm(
        request.POST,
        assignment=assignment,
        student=request.user,
    )

    if form.is_valid():
        slot = form.save()
        messages.success(
            request,
            f"Instruction request submitted for {day_date.strftime('%B %d, %Y')}. "
            "The instructor will review your request.",
        )
        # HTML email sent via signal (send_student_signup_notification)

    else:
        for error in form.non_field_errors():
            messages.error(request, str(error))

    return redirect("duty_roster:duty_calendar_month", year=year, month=month)


@active_member_required
@require_POST
def cancel_instruction_request(request, slot_id):
    """Student cancels their own instruction request."""
    from .models import InstructionSlot

    slot = get_object_or_404(InstructionSlot, id=slot_id, student=request.user)

    if slot.assignment.date < date.today():
        messages.error(request, "Cannot cancel instruction for past dates.")
    elif slot.status == "cancelled":
        messages.warning(request, "This request was already cancelled.")
    else:
        slot.status = "cancelled"
        slot.save()
        messages.success(request, "Your instruction request has been cancelled.")

        if slot.instructor_response == "accepted":
            _notify_instructor_cancellation(slot)

    return redirect(
        "duty_roster:duty_calendar_month",
        year=slot.assignment.date.year,
        month=slot.assignment.date.month,
    )


@active_member_required
def my_instruction_requests(request):
    """Show a student their pending and upcoming instruction requests."""
    from .models import InstructionSlot

    today = date.today()

    # Get all non-cancelled requests for this user
    requests_qs = (
        InstructionSlot.objects.filter(student=request.user)
        .exclude(status="cancelled")
        .select_related("assignment", "instructor")
        .order_by("assignment__date")
    )

    upcoming = requests_qs.filter(assignment__date__gte=today)
    past = requests_qs.filter(assignment__date__lt=today)[:10]

    return render(
        request,
        "duty_roster/my_instruction_requests.html",
        {
            "upcoming_requests": upcoming,
            "past_requests": past,
            "today": today,
        },
    )


# =============================================================================
# Instructor Management Views
# =============================================================================


@active_member_required
def instructor_requests(request):
    """
    Show an instructor all pending instruction requests for days they are scheduled.

    Only visible to members who are instructors.
    """
    from .models import InstructionSlot

    if not request.user.instructor:
        messages.error(request, "Only instructors can access this page.")
        return redirect("duty_roster:duty_calendar")

    today = date.today()

    # Get all future assignments where this user is the instructor
    my_assignments = DutyAssignment.objects.filter(
        date__gte=today,
    ).filter(
        models.Q(instructor=request.user) | models.Q(surge_instructor=request.user)
    )

    # Get all instruction slots for those assignments
    pending_slots = (
        InstructionSlot.objects.filter(
            assignment__in=my_assignments,
            instructor_response="pending",
        )
        .exclude(status="cancelled")
        .select_related("assignment", "student")
        .order_by("assignment__date", "created_at")
    )

    accepted_slots = (
        InstructionSlot.objects.filter(
            assignment__in=my_assignments,
            instructor_response="accepted",
        )
        .exclude(status="cancelled")
        .select_related("assignment", "student")
        .order_by("assignment__date", "created_at")
    )

    # Group by assignment date for easier display
    from collections import defaultdict

    pending_by_date = defaultdict(list)
    for slot in pending_slots:
        pending_by_date[slot.assignment.date].append(slot)

    accepted_by_date = defaultdict(list)
    for slot in accepted_slots:
        accepted_by_date[slot.assignment.date].append(slot)

    return render(
        request,
        "duty_roster/instructor_requests.html",
        {
            "pending_by_date": dict(pending_by_date),
            "accepted_by_date": dict(accepted_by_date),
            "pending_count": len(pending_slots),
            "accepted_count": len(accepted_slots),
            "today": today,
        },
    )


@active_member_required
@require_POST
def instructor_respond(request, slot_id):
    """
    Instructor accepts or rejects a student's instruction request.
    """
    from .forms import InstructorResponseForm
    from .models import InstructionSlot

    if not request.user.instructor:
        return HttpResponseForbidden("Only instructors can respond to requests.")

    slot = get_object_or_404(InstructionSlot, id=slot_id)

    # Verify this instructor is assigned to this day
    assignment = slot.assignment
    if request.user not in [assignment.instructor, assignment.surge_instructor]:
        return HttpResponseForbidden("You are not the instructor for this day.")

    # Check if already responded
    if slot.instructor_response != "pending":
        messages.warning(request, "You have already responded to this request.")
        return redirect("duty_roster:instructor_requests")

    action = request.POST.get("action")
    if action not in ["accept", "reject"]:
        messages.error(request, "Invalid action.")
        return redirect("duty_roster:instructor_requests")

    form = InstructorResponseForm(request.POST, instance=slot, instructor=request.user)

    if form.is_valid():
        if action == "accept":
            form.accept()
            messages.success(
                request,
                f"Accepted {slot.student.full_display_name} for {slot.assignment.date.strftime('%B %d')}.",
            )
            # HTML email sent via signal (send_request_response_email)

            # Check if we now have 3+ students and need surge instructor
            _check_surge_instructor_needed(slot.assignment)

        elif action == "reject":
            form.reject()
            messages.info(
                request,
                f"Declined {slot.student.full_display_name} for {slot.assignment.date.strftime('%B %d')}.",
            )
            # HTML email sent via signal (send_request_response_email)

    return redirect("duty_roster:instructor_requests")


# =============================================================================
# Instruction Notification Helpers
# Note: Most instruction notifications are now handled via signals.py
# using HTML email templates. Only cancellation notification remains here.
# =============================================================================


def _notify_instructor_cancellation(slot):
    """Notify instructor when an accepted student cancels."""
    instructor = slot.instructor
    if not instructor or not instructor.email:
        return

    try:
        subject = (
            f"Instruction Cancellation for {slot.assignment.date.strftime('%B %d, %Y')}"
        )
        message = (
            f"{slot.student.full_display_name} has cancelled their instruction request for "
            f"{slot.assignment.date.strftime('%A, %B %d, %Y')}.\n\n"
            f"You now have one fewer student for this day."
        )

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instructor.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send cancellation notification")


def _check_surge_instructor_needed(assignment):
    """
    Check if the assignment now has 3+ accepted students and needs a surge instructor.

    If so, and no surge instructor is already assigned, notify the instructor list.
    """
    from .models import InstructionSlot

    accepted_count = (
        InstructionSlot.objects.filter(
            assignment=assignment,
            instructor_response="accepted",
        )
        .exclude(status="cancelled")
        .count()
    )

    # If 3+ students and no surge instructor yet, notify
    if accepted_count >= 3 and not assignment.surge_instructor:
        # Only notify once
        if not assignment.surge_notified:
            _notify_surge_instructor_needed(assignment, accepted_count)
            assignment.surge_notified = True
            assignment.save(update_fields=["surge_notified"])


def _notify_surge_instructor_needed(assignment, student_count):
    """Notify the instructors mailing list that a surge instructor is needed."""
    try:
        config = SiteConfiguration.objects.first()
        instructor_email = getattr(config, "instructors_email", None)

        if not instructor_email:
            logger.warning("No instructor email configured in SiteConfiguration")
            return

        primary_instructor = assignment.instructor
        instructor_name = (
            primary_instructor.full_display_name if primary_instructor else "Unknown"
        )

        subject = f"Surge Instructor Needed - {assignment.date.strftime('%B %d, %Y')}"
        message = (
            f"Instructor {instructor_name} has {student_count} students signed up for "
            f"{assignment.date.strftime('%A, %B %d, %Y')} and needs assistance.\n\n"
            f"If you are available to provide instruction on this day, please contact "
            f"{instructor_name} or update your availability in Manage2Soar.\n\n"
            f"Students signed up: {student_count}"
        )

        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instructor_email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send surge instructor notification")
