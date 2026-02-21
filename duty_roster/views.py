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

from duty_roster.utils.delinquents import apply_duty_delinquent_exemptions
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

from .forms import DutyAssignmentForm, DutyPreferenceForm, DutyRosterMessageForm
from .models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutyRosterMessage,
    MemberBlackout,
    OpsIntent,
)
from .roster_generator import generate_roster, is_within_operational_season

logger = logging.getLogger("duty_roster.views")

# Allowed roles for roster slot editing/assignment endpoints
ALLOWED_ROLES = ["instructor", "duty_officer", "assistant_duty_officer", "towpilot"]


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


# Sentinel shared by get_surge_thresholds() and _check_instruction_request_window()
# to distinguish a cache miss from a legitimately cached None (no SiteConfiguration
# row), preventing repeated DB hits when the table is empty.
_SITECONFIG_CACHE_SENTINEL = object()


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
    config = cache.get("siteconfig_instance", _SITECONFIG_CACHE_SENTINEL)
    if config is _SITECONFIG_CACHE_SENTINEL:
        config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", config, timeout=60)
    tow_surge_threshold = config.tow_surge_threshold if config else 6
    instruction_surge_threshold = config.instruction_surge_threshold if config else 4
    return tow_surge_threshold, instruction_surge_threshold


def _check_instruction_request_window(day_date):
    """
    Check whether instruction requests are permitted for *day_date* today.

    Returns a (too_early, opens_on) tuple:
      - too_early  (bool)  – True when the window restriction is active and the
                             date is still too far in the future.
      - opens_on   (date | None) – The first day on which a request is allowed
                             (only set when too_early is True).

    When the site-wide restriction is disabled (the default), always returns
    (False, None) so existing behaviour is unchanged.

    Uses the same SiteConfiguration cache as get_surge_thresholds() (60-second
    TTL) to avoid unnecessary DB queries on every calendar modal view.
    """
    config = cache.get("siteconfig_instance", _SITECONFIG_CACHE_SENTINEL)
    if config is _SITECONFIG_CACHE_SENTINEL:
        config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", config, timeout=60)
    if not config or not config.restrict_instruction_requests_window:
        return False, None
    if day_date < date.today():
        return False, None
    days_until = (day_date - date.today()).days
    if days_until > config.instruction_request_max_days_ahead:
        opens_on = day_date - timedelta(days=config.instruction_request_max_days_ahead)
        return True, opens_on
    return False, None


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
    instruction_request_too_early = False
    instruction_request_opens_on = None
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

        # Check instruction request window restriction (Issue #648)
        instruction_request_too_early, instruction_request_opens_on = (
            _check_instruction_request_window(day_date)
        )

        # Only show form if user doesn't already have a request and an instructor is assigned
        if (
            not user_has_instruction_request
            and not instruction_request_too_early
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
            "instruction_request_too_early": instruction_request_too_early,
            "instruction_request_opens_on": instruction_request_opens_on,
            "has_instructor_assigned": bool(
                assignment and (assignment.instructor or assignment.surge_instructor)
            ),
        },
    )


@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    from django.conf import settings

    day_date = date(year, month, day)

    # remember prior intent so we only email on true cancellations
    old_intent = OpsIntent.objects.filter(member=request.user, date=day_date).first()
    old_available = old_intent.available_as if old_intent else []

    available_as = request.POST.getlist("available_as") or []

    # enforce site-configured instruction request window (Issue #648)
    if "instruction" in available_as:
        too_early_intent, opens_on_intent = _check_instruction_request_window(day_date)
        if too_early_intent:
            opens_str = (
                opens_on_intent.strftime("%B %d, %Y")
                if opens_on_intent
                else "a future date"
            )
            response = format_html(
                '<p class="text-danger">⏰ Instruction requests for this date do not open until {}.</p>'
                '<form hx-get="{}form/" '
                'hx-post="{}" '
                'hx-target="#ops-intent-response" hx-swap="innerHTML">'
                '<button type="submit" class="btn btn-sm btn-primary">'
                "🛩️ I Plan to Fly This Day</button></form>",
                opens_str,
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

    # Get default airfield - prefer KFRR if active, otherwise use first active
    default_airfield = (
        Airfield.objects.filter(identifier="KFRR", is_active=True).first()
        or Airfield.objects.filter(is_active=True).first()
    )

    assignment, created = DutyAssignment.objects.get_or_create(
        date=day_obj,
        defaults={
            "location": default_airfield,
            "is_scheduled": False,
            "is_confirmed": False,
        },
    )
    # Only send the proposal email when the day is genuinely new.
    # If the day already existed (e.g. a second "Propose" click), skip
    # to avoid sending a duplicate proposal (issue #654).
    if created:
        notify_ops_status(assignment)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_tow_signup(request, year, month, day):
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    # Validate that user is allowed
    if not member.towpilot:
        return HttpResponseForbidden("You are not a tow pilot.")

    # Use transaction with row lock to prevent race conditions
    assignment_changed = False
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # For ad-hoc days, prevent dual signup as both towpilot and instructor
        if not assignment.is_scheduled:
            if assignment.instructor == member:
                title = get_role_title("instructor") or "Instructor"
                return HttpResponseForbidden(
                    f"You are already signed up as {title} for this day. "
                    "Please rescind that signup first if you want to tow instead."
                )

        # Assign as tow pilot if none already assigned
        if not assignment.tow_pilot:
            assignment.tow_pilot = member
            assignment.save()
            assignment_changed = True

    # Notify after transaction completes to avoid holding row lock during email sends
    # Only notify if assignment was actually changed
    if assignment_changed:
        # Refresh from DB to get current state (in case concurrent signups updated other roles)
        assignment.refresh_from_db()
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
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    if not member.instructor:
        return HttpResponseForbidden("You are not an instructor.")

    # Use transaction with row lock to prevent race conditions
    assignment_changed = False
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # For ad-hoc days, prevent dual signup as both towpilot and instructor
        if not assignment.is_scheduled:
            if assignment.tow_pilot == member:
                title = get_role_title("towpilot") or "Tow Pilot"
                return HttpResponseForbidden(
                    f"You are already signed up as {title} for this day. "
                    "Please rescind that signup first if you want to instruct instead."
                )

        if not assignment.instructor:
            assignment.instructor = member
            assignment.save()
            assignment_changed = True

    # Notify after transaction completes to avoid holding row lock during email sends
    # Only notify if assignment was actually changed
    if assignment_changed:
        # Refresh from DB to get current state (in case concurrent signups updated other roles)
        assignment.refresh_from_db()
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
def calendar_tow_rescind(request, year, month, day):
    """Allow a member to rescind their tow pilot signup for an ad-hoc day."""
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    # Use transaction with row lock to prevent race conditions
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # Only allow rescinding on ad-hoc days (not scheduled)
        if assignment.is_scheduled:
            return HttpResponseForbidden("Cannot rescind from scheduled operations.")

        # Only allow rescinding if you're the one signed up
        if assignment.tow_pilot != member:
            return HttpResponseForbidden("You are not the tow pilot for this day.")

        # Remove the signup and recalculate confirmation state
        # Ad-hoc ops are only confirmed when both tow pilot and duty officer are assigned
        assignment.tow_pilot = None
        assignment.is_confirmed = bool(assignment.tow_pilot and assignment.duty_officer)
        assignment.save()

    notify_ops_status(assignment, is_rescind=True)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_instructor_rescind(request, year, month, day):
    """Allow a member to rescind their instructor signup for an ad-hoc day."""
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    # Use transaction with row lock to prevent race conditions
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # Only allow rescinding on ad-hoc days (not scheduled)
        if assignment.is_scheduled:
            return HttpResponseForbidden("Cannot rescind from scheduled operations.")

        # Only allow rescinding if you're the one signed up
        if assignment.instructor != member:
            return HttpResponseForbidden("You are not the instructor for this day.")

        # Remove the signup
        assignment.instructor = None
        assignment.save()

    notify_ops_status(assignment, is_rescind=True)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_dutyofficer_rescind(request, year, month, day):
    """Allow a member to rescind their duty officer signup for an ad-hoc day."""
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    # Use transaction with row lock to prevent race conditions
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # Only allow rescinding on ad-hoc days (not scheduled)
        if assignment.is_scheduled:
            return HttpResponseForbidden("Cannot rescind from scheduled operations.")

        # Only allow rescinding if you're the one signed up
        if assignment.duty_officer != member:
            return HttpResponseForbidden("You are not the duty officer for this day.")

        # Remove the signup and recalculate confirmation state
        # Ad-hoc ops are only confirmed when both tow pilot and duty officer are assigned
        assignment.duty_officer = None
        assignment.is_confirmed = bool(assignment.tow_pilot and assignment.duty_officer)
        assignment.save()

    notify_ops_status(assignment, is_rescind=True)

    # Return HTMX response to refresh calendar body with specific month context
    return calendar_refresh_response(year, month)


@require_POST
@active_member_required
def calendar_ado_rescind(request, year, month, day):
    """Allow a member to rescind their ADO signup for an ad-hoc day."""
    from django.db import transaction

    day_obj = date(int(year), int(month), int(day))
    member = request.user

    # Use transaction with row lock to prevent race conditions
    with transaction.atomic():
        assignment = get_object_or_404(
            DutyAssignment.objects.select_for_update(),
            date=day_obj,
        )

        # Only allow rescinding on ad-hoc days (not scheduled)
        if assignment.is_scheduled:
            return HttpResponseForbidden("Cannot rescind from scheduled operations.")

        # Only allow rescinding if you're the one signed up
        if assignment.assistant_duty_officer != member:
            title = get_role_title("assistant_duty_officer") or "Assistant Duty Officer"
            return HttpResponseForbidden(
                f"You are not the {title.lower()} for this day."
            )

        # Remove the signup
        assignment.assistant_duty_officer = None
        assignment.save()

    notify_ops_status(assignment, is_rescind=True)

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
@require_POST
def get_eligible_members_for_slot(request):
    """
    AJAX endpoint to get eligible members for a specific roster slot.
    Returns JSON with eligible members and their availability info.
    """
    try:
        from datetime import date as dt_date

        date_str = request.POST.get("date")
        role = request.POST.get("role")

        if not date_str or not role:
            return JsonResponse({"error": "Missing date or role"}, status=400)

        # Validate role is one of the allowed role names (security)
        if role not in ALLOWED_ROLES:
            return JsonResponse({"error": "Invalid role"}, status=400)

        try:
            day = dt_date.fromisoformat(date_str)
        except ValueError:
            return JsonResponse({"error": "Invalid date format"}, status=400)

        # Get current roster from session
        draft = request.session.get("proposed_roster", [])
        day_entry = next((e for e in draft if e["date"] == date_str), None)

        if not day_entry:
            return JsonResponse({"error": "Date not found in roster"}, status=404)

        # Ensure the requested role is actually enabled for this day in the draft roster
        slots = day_entry.get("slots", {})
        if role not in slots:
            return JsonResponse(
                {"error": "Role not enabled for this date in the current roster"},
                status=400,
            )
    except Exception as e:
        logger.exception("Error in get_eligible_members_for_slot (initial checks)")
        return JsonResponse({"error": "Internal error processing request"}, status=500)

    try:
        # Get all members and prefs for eligibility checking
        members = list(Member.objects.filter(is_active=True))
        prefs = {
            p.member_id: p
            for p in DutyPreference.objects.select_related("member").all()
        }
        blackouts = {
            (b.member_id, b.date)
            for b in MemberBlackout.objects.filter(
                date__year=day.year, date__month=day.month
            )
        }
        avoidances = {
            (a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()
        }

        # Get currently assigned members for this day
        # Collect all member IDs from the slots, then bulk-fetch to avoid N+1 queries.
        # Exclude the member currently assigned to the slot being edited (if provided),
        # so they are not incorrectly flagged as "already assigned" elsewhere today.
        current_member_id = request.POST.get("current_member_id")
        try:
            current_member_id = int(current_member_id) if current_member_id else None
        except (TypeError, ValueError):
            current_member_id = None

        assigned_member_ids = {
            member_id
            for _, member_id in day_entry["slots"].items()
            if member_id and member_id != current_member_id
        }

        assigned_today_queryset = Member.objects.filter(pk__in=assigned_member_ids)
        found_ids = set(assigned_today_queryset.values_list("id", flat=True))
        missing_ids = assigned_member_ids - found_ids
        for missing_id in missing_ids:
            # Draft may reference a member that has since been deleted; skip but log
            logger.warning(
                "Duty roster draft refers to missing Member id=%s; skipping.",
                missing_id,
            )

        assigned_today = set(assigned_today_queryset)

        # Calculate assignments for the month
        assignments = defaultdict(int)
        for entry in draft:
            for r, member_id in entry["slots"].items():
                if member_id:
                    assignments[member_id] += 1

        # Find eligible members
        DEFAULT_MAX_ASSIGNMENTS = 8
        eligible_members = []
        for m in members:
            # Check if member has the role flag
            if not getattr(m, role, False):
                continue

            p = prefs.get(m.id)

            # If no preference, treat as eligible with defaults
            if not p:
                # Still check basic constraints
                if (m.id, day) in blackouts:
                    continue

                avoids = False
                for o in assigned_today:
                    if m != o and (
                        (m.id, o.id) in avoidances or (o.id, m.id) in avoidances
                    ):
                        avoids = True
                        break

                already_assigned = m in assigned_today
                at_max = assignments[m.id] >= DEFAULT_MAX_ASSIGNMENTS

                eligible_members.append(
                    {
                        "id": m.id,
                        "name": m.full_display_name,
                        "warnings": {
                            "avoids_someone": avoids,
                            "already_assigned": already_assigned,
                            "at_max": at_max,
                        },
                        "assignments_this_month": assignments[m.id],
                        "max_assignments": DEFAULT_MAX_ASSIGNMENTS,
                    }
                )
                continue

            # Member has preferences - check them
            if p.dont_schedule or p.scheduling_suspended:
                continue

            if (m.id, day) in blackouts:
                continue

            # Check avoidances (but less strict - show as "warning")
            avoids = False
            for o in assigned_today:
                if m != o and (
                    (m.id, o.id) in avoidances or (o.id, m.id) in avoidances
                ):
                    avoids = True
                    break

            # Check if already assigned (also show as warning)
            already_assigned = m in assigned_today

            # Check percentage
            percent_fields = [
                ("instructor", "instructor_percent"),
                ("duty_officer", "duty_officer_percent"),
                ("assistant_duty_officer", "ado_percent"),
                ("towpilot", "towpilot_percent"),
            ]
            eligible_role_fields = [
                field for r, field in percent_fields if getattr(m, r, False)
            ]

            if len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                pct = getattr(p, field, 0)
                if pct == 0:
                    pct = 100
            else:
                all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
                if role == "assistant_duty_officer":
                    pct = p.ado_percent if not all_zero else 100
                else:
                    pct = getattr(p, f"{role}_percent", 0) if not all_zero else 100

            if pct == 0:
                continue

            # Check max assignments
            at_max = assignments[m.id] >= getattr(p, "max_assignments_per_month", 0)

            eligible_members.append(
                {
                    "id": m.id,
                    "name": m.full_display_name,
                    "warnings": {
                        "avoids_someone": avoids,
                        "already_assigned": already_assigned,
                        "at_max": at_max,
                    },
                    "assignments_this_month": assignments[m.id],
                    "max_assignments": getattr(p, "max_assignments_per_month", 0),
                }
            )

        # Sort by assignments (fewest first) and name
        eligible_members.sort(key=lambda x: (x["assignments_this_month"], x["name"]))

        return JsonResponse(
            {
                "eligible_members": eligible_members,
                "current_assignment": day_entry["slots"].get(role),
                "date": date_str,
                "role": role,
            }
        )
    except Exception as e:
        logger.exception("Error in get_eligible_members_for_slot (main logic)")
        return JsonResponse(
            {"error": "Internal error loading eligible members"}, status=500
        )


@active_member_required
@user_passes_test(is_rostermeister)
@require_POST
def update_roster_slot(request):
    """
    AJAX endpoint to update a specific roster slot.
    """
    date_str = request.POST.get("date")
    role = request.POST.get("role")
    member_id = request.POST.get("member_id")  # Can be empty string to clear

    if not date_str or not role:
        return JsonResponse({"error": "Missing date or role"}, status=400)

    # Validate role is one of the allowed role names (security)
    if role not in ALLOWED_ROLES:
        return JsonResponse({"error": "Invalid role"}, status=400)

    # Validate member exists and is eligible if provided
    member = None
    member_name = "—"
    if member_id and member_id != "":
        try:
            member_id = int(member_id)
            member = Member.objects.get(pk=member_id)
        except (ValueError, Member.DoesNotExist):
            return JsonResponse({"error": "Invalid member"}, status=400)

        # Enforce that the selected member is actually eligible for this role.
        # For the allowed roles, the Member capability flag matches the role name
        # (e.g., member.instructor, member.duty_officer, member.towpilot).
        if not getattr(member, role, False):
            return JsonResponse(
                {"error": "Member not eligible for this role"},
                status=400,
            )

        # Check active membership status
        if not member.is_active:
            return JsonResponse(
                {"error": "Member is not active"},
                status=400,
            )

        # Parse the date for constraint checks
        try:
            day = dt_date.fromisoformat(date_str)
        except ValueError:
            return JsonResponse({"error": "Invalid date format"}, status=400)

        # Check for preference-based constraints
        try:
            pref = DutyPreference.objects.get(member=member)
            if pref.dont_schedule:
                return JsonResponse(
                    {"error": "Member has opted out of scheduling"},
                    status=400,
                )
            if pref.scheduling_suspended:
                return JsonResponse(
                    {"error": "Member scheduling is suspended"},
                    status=400,
                )

            # Check role percentage (0% means don't schedule for this role)
            percent_fields = [
                ("instructor", "instructor_percent"),
                ("duty_officer", "duty_officer_percent"),
                ("assistant_duty_officer", "ado_percent"),
                ("towpilot", "towpilot_percent"),
            ]
            eligible_role_fields = [
                field for r, field in percent_fields if getattr(member, r, False)
            ]

            if len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                pct = getattr(pref, field, 0)
                if pct == 0:
                    pct = 100  # Single role, treat 0 as 100
            else:
                all_zero = all(getattr(pref, f, 0) == 0 for f in eligible_role_fields)
                if role == "assistant_duty_officer":
                    pct = pref.ado_percent if not all_zero else 100
                else:
                    pct = getattr(pref, f"{role}_percent", 0) if not all_zero else 100

            if pct == 0:
                return JsonResponse(
                    {"error": "Member has 0% preference for this role"},
                    status=400,
                )
        except DutyPreference.DoesNotExist:
            # No preference means eligible with defaults (no specific checks needed)
            pass

        # Check blackouts
        blackout_exists = MemberBlackout.objects.filter(
            member=member, date=day
        ).exists()
        if blackout_exists:
            return JsonResponse(
                {"error": "Member is blacked out on this date"},
                status=400,
            )

        # Store member name now that we have the object
        member_name = member.full_display_name
    else:
        member_id = None

    # Get current roster from session
    draft = request.session.get("proposed_roster", [])

    # Find and update the day entry
    updated = False
    for entry in draft:
        if entry["date"] == date_str:
            # Ensure the role exists in this date's slots (prevents creating new keys)
            if role not in entry.get("slots", {}):
                return JsonResponse({"error": "Invalid role for this date"}, status=400)

            entry["slots"][role] = member_id

            # Clear any stale diagnostics for this role only when the slot is now filled.
            # If the slot is cleared (member_id is empty/None), retain diagnostics so the
            # UI can still explain why the slot is empty.
            diagnostics = entry.get("diagnostics")
            if isinstance(diagnostics, dict) and role in diagnostics and member_id:
                diagnostics.pop(role, None)

            updated = True
            break

    if not updated:
        return JsonResponse({"error": "Date not found in roster"}, status=404)

    # Save back to session
    request.session["proposed_roster"] = draft
    request.session.modified = True

    # Get the updated entry to retrieve current diagnostic (if any)
    current_diagnostic = None
    for entry in draft:
        if entry["date"] == date_str:
            diagnostics = entry.get("diagnostics", {})
            if isinstance(diagnostics, dict):
                current_diagnostic = diagnostics.get(role)
            break

    # member_name was already set during validation (or defaults to "—")

    return JsonResponse(
        {
            "success": True,
            "member_id": member_id,
            "member_name": member_name,
            "date": date_str,
            "role": role,
            "diagnostic": current_diagnostic,  # Include current diagnostic state
        }
    )


def _get_removed_dates_from_session(request, year, month, clean_invalid=False):
    """
    Parse removed dates from session for a given year/month.

    Args:
        request: Django HttpRequest with session data
        year: Year to filter removed dates
        month: Month to filter removed dates
        clean_invalid: If True, update session to remove malformed dates

    Returns:
        List of datetime.date objects (malformed entries are skipped)
    """
    session_key = f"removed_roster_dates_{year}_{month:02d}"
    removed_date_strs = request.session.get(session_key, [])
    exclude_dates = []
    cleaned_removed_date_strs = []

    for ds in removed_date_strs:
        try:
            parsed_date = dt_date.fromisoformat(ds)
        except (TypeError, ValueError):
            # Skip any malformed or non-ISO-formatted values
            continue
        else:
            exclude_dates.append(parsed_date)
            cleaned_removed_date_strs.append(ds)

    # If we dropped any bad entries and caller wants cleanup, update the session
    if clean_invalid and len(cleaned_removed_date_strs) != len(removed_date_strs):
        request.session[session_key] = cleaned_removed_date_strs

    return exclude_dates


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

                # Track removed dates so Roll Again remembers them (scoped to year/month)
                session_key = f"removed_roster_dates_{year}_{month:02d}"
                previously_removed = set(request.session.get(session_key, []))
                previously_removed.update(d.isoformat() for d in dates_to_remove_set)
                request.session[session_key] = sorted(previously_removed)

                messages.success(
                    request,
                    f"Removed {len(dates_to_remove_set)} date(s) from the proposed roster. "
                    f"These dates will stay removed on Roll Again.",
                )

        elif action == "roll":
            # Retrieve dates previously removed by the user so we skip them (scoped to year/month)
            exclude_dates = _get_removed_dates_from_session(
                request, year, month, clean_invalid=True
            )

            raw = generate_roster(
                year, month, roles=enabled_roles, exclude_dates=exclude_dates
            )
            if not raw:
                exclude_set = set(exclude_dates)
                cal = calendar.Calendar()
                weekend = [
                    d
                    for d in cal.itermonthdates(year, month)
                    if d.month == month
                    and d.weekday() in (5, 6)
                    and is_within_operational_season(d)
                    and d not in exclude_set
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
                    "diagnostics": e.get("diagnostics", {}),
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
            # Clear removed dates for the current month
            session_key = f"removed_roster_dates_{year}_{month:02d}"
            request.session.pop(session_key, None)

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

        elif action == "restore_dates":
            # Clear removed dates so Roll Again includes all dates again (scoped to year/month)
            session_key = f"removed_roster_dates_{year}_{month:02d}"
            request.session.pop(session_key, None)
            messages.info(
                request,
                "All previously removed dates have been restored. "
                "Click Roll Again to regenerate the full roster.",
            )

        elif action == "cancel":
            request.session.pop("proposed_roster", None)
            # Clear removed dates for the current month
            session_key = f"removed_roster_dates_{year}_{month:02d}"
            request.session.pop(session_key, None)
            return redirect("duty_roster:duty_calendar")
    else:
        # Retrieve any previously removed dates for this year/month
        exclude_dates = _get_removed_dates_from_session(request, year, month)

        raw = generate_roster(
            year, month, roles=enabled_roles, exclude_dates=exclude_dates
        )
        if not raw:
            exclude_set = set(exclude_dates)
            cal = calendar.Calendar()
            weekend = [
                d
                for d in cal.itermonthdates(year, month)
                if d.month == month
                and d.weekday() in (5, 6)
                and is_within_operational_season(d)
                and d not in exclude_set
            ]
            raw = [
                {"date": d, "slots": {r: None for r in enabled_roles}} for d in weekend
            ]
            incomplete = True
        draft = [
            {
                "date": e["date"].isoformat(),
                "slots": {r: e["slots"].get(r) for r in enabled_roles},
                "diagnostics": e.get("diagnostics", {}),
            }
            for e in raw
        ]
        request.session["proposed_roster"] = draft
    display = [
        {
            "date": dt_date.fromisoformat(e["date"]),
            "slots": e["slots"],
            "diagnostics": e.get("diagnostics", {}),
        }
        for e in request.session.get("proposed_roster", [])
    ]
    # Build list of removed dates for display in the template (scoped to year/month)
    removed_dates = _get_removed_dates_from_session(request, year, month)

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
            "removed_dates": removed_dates,
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
    # Apply duty delinquency exemptions (treasurer, emeritus)
    active_flyers = apply_duty_delinquent_exemptions(
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

    Only checks ACTUAL duty performed (flight activity and logsheet assignments),
    not scheduled duty (DutyAssignment). Being scheduled but not showing up
    doesn't count as performing duty.

    For instructors and tow pilots, checks actual flight participation.
    For duty officers and assistant duty officers, checks logsheet assignments.
    """
    from django.db.models import Q

    from logsheet.models import Flight, Logsheet

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

    # Check Logsheet duty assignments (actual operations) for all duty roles
    logsheet_duty = Logsheet.objects.filter(
        Q(duty_officer=member)
        | Q(assistant_duty_officer=member)
        | Q(duty_instructor=member)
        | Q(surge_instructor=member)
        | Q(tow_pilot=member)
        | Q(surge_tow_pilot=member),
        log_date__gte=cutoff_date,
        finalized=True,
    ).order_by("-log_date")

    latest_logsheet_duty = logsheet_duty.first()
    if latest_logsheet_duty is not None:
        roles = []
        if latest_logsheet_duty.duty_officer == member:
            roles.append("Duty Officer")
        if latest_logsheet_duty.assistant_duty_officer == member:
            roles.append("Assistant Duty Officer")
        if latest_logsheet_duty.duty_instructor == member:
            roles.append("Duty Instructor")
        if latest_logsheet_duty.surge_instructor == member:
            roles.append("Surge Instructor")
        if latest_logsheet_duty.tow_pilot == member:
            roles.append("Tow Pilot")
        if latest_logsheet_duty.surge_tow_pilot == member:
            roles.append("Surge Tow Pilot")

        return {
            "has_duty": True,
            "last_duty_date": latest_logsheet_duty.log_date,
            "last_duty_role": f"{', '.join(roles)}",
            "last_duty_type": "Logsheet Duty",
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

    # Enforce instruction request window restriction (Issue #648)
    too_early, opens_on = _check_instruction_request_window(day_date)
    if too_early:
        if opens_on is None:
            logger.error(
                "Instruction request window check returned too_early=True but opens_on=None "
                "for date %s",
                day_date,
            )
            messages.error(
                request,
                "Instruction requests for this date cannot be submitted yet. Please try again later.",
            )
            return redirect("duty_roster:duty_calendar_month", year=year, month=month)
        max_days_ahead = (day_date - opens_on).days
        messages.error(
            request,
            f"Instruction requests for {day_date.strftime('%B %d, %Y')} cannot be submitted yet. "
            f"Requests open on {opens_on.strftime('%B %d, %Y')} "
            f"({max_days_ahead} days before the scheduled date).",
        )
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

    _, instruction_surge_threshold = get_surge_thresholds()

    return render(
        request,
        "duty_roster/instructor_requests.html",
        {
            "pending_by_date": dict(pending_by_date),
            "accepted_by_date": dict(accepted_by_date),
            "pending_count": len(pending_slots),
            "accepted_count": len(accepted_slots),
            "today": today,
            "instruction_surge_threshold": instruction_surge_threshold,
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


@active_member_required
@require_POST
def request_surge_instructor(request, assignment_id):
    """
    Allow the primary instructor to manually request a surge instructor for their day.

    Sends a notification to the instructors mailing list and marks the assignment
    surge_notified=True.  The button is visible whenever the accepted student count
    is high AND no surge instructor has yet been assigned.  Clicking it a second time
    (re-send) is intentionally allowed so instructors can follow up if needed.
    """
    from .models import InstructionSlot

    assignment = get_object_or_404(DutyAssignment, id=assignment_id)

    # Only the primary instructor may trigger this; surge instructors cannot self-request
    if assignment.instructor != request.user:
        return HttpResponseForbidden(
            "Only the primary instructor for this day can request a surge instructor."
        )

    # Guard: if a surge instructor is already assigned, no new notification is needed
    if assignment.surge_instructor_id:
        messages.info(
            request,
            "A surge instructor is already assigned for this day; no new request was sent.",
        )
        return redirect("duty_roster:instructor_requests")

    accepted_count = (
        InstructionSlot.objects.filter(
            assignment=assignment,
            instructor_response="accepted",
        )
        .exclude(status="cancelled")
        .count()
    )

    sent = _notify_surge_instructor_needed(assignment, accepted_count)
    if sent:
        assignment.surge_notified = True
        assignment.save(update_fields=["surge_notified"])
        messages.success(
            request,
            f"Surge instructor request sent for {assignment.date.strftime('%B %d, %Y')}. "
            f"The instructors list has been notified.",
        )
    else:
        messages.error(
            request,
            "Could not send surge instructor request. "
            "Verify that an instructors e-mail address is configured in Site Configuration.",
        )

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
    Check if the assignment now has accepted students at or above the configured
    instruction_surge_threshold and needs a surge instructor.

    If so, and no surge instructor is already assigned, notify the instructor list.
    Uses the same configurable instruction_surge_threshold as the ops-intent surge
    system so both mechanisms stay in sync with admin configuration.
    """
    from .models import InstructionSlot

    _, instruction_threshold = get_surge_thresholds()

    accepted_count = (
        InstructionSlot.objects.filter(
            assignment=assignment,
            instructor_response="accepted",
        )
        .exclude(status="cancelled")
        .count()
    )

    # If accepted students reach the configured threshold and no surge instructor yet, notify
    if accepted_count >= instruction_threshold and not assignment.surge_instructor:
        # Only notify once, and only mark surge_notified=True if the email
        # was actually sent (prevents silently swallowing config errors)
        if not assignment.surge_notified:
            sent = _notify_surge_instructor_needed(assignment, accepted_count)
            if sent:
                assignment.surge_notified = True
                assignment.save(update_fields=["surge_notified"])


def _notify_surge_instructor_needed(assignment, student_count):
    """Notify the instructors mailing list that a surge instructor is needed.

    Returns True if the email was sent successfully, False otherwise.
    The caller should only set surge_notified=True when this returns True,
    so a misconfigured email address doesn't permanently suppress future attempts.
    """
    try:
        config = SiteConfiguration.objects.first()
        instructor_email = config.instructors_email if config else ""

        if not instructor_email:
            logger.warning(
                "No instructors_email configured in SiteConfiguration; "
                "surge instructor alert for %s suppressed",
                assignment.date,
            )
            return False

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

        sent_count = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [instructor_email],
            fail_silently=False,
        )
        return sent_count > 0
    except Exception:
        logger.exception("Failed to send surge instructor notification")
        return False


@active_member_required
@user_passes_test(lambda u: is_rostermeister(u) or u.is_staff or u.is_superuser)
@never_cache
def edit_roster_message(request):
    """
    View for Rostermeisters to edit the duty roster announcement message (Issue #551).

    This replaces the plain-text announcement in SiteConfiguration with a
    rich HTML message editable through TinyMCE.
    """
    message = DutyRosterMessage.get_or_create_message()

    if request.method == "POST":
        form = DutyRosterMessageForm(request.POST, instance=message)
        if form.is_valid():
            roster_message = form.save(commit=False)
            roster_message.updated_by = request.user
            roster_message.save()
            messages.success(
                request, "Roster announcement message updated successfully."
            )
            return redirect("duty_roster:duty_calendar")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = DutyRosterMessageForm(instance=message)

    return render(
        request,
        "duty_roster/edit_roster_message.html",
        {
            "form": form,
            "message": message,
        },
    )
