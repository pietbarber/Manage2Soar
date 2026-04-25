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
from django.db import models, transaction
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
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
from members.decorators import active_member_required
from members.models import Member
from members.utils.membership import get_active_membership_statuses
from siteconfig.models import ReservationLimitPeriod, SiteConfiguration
from siteconfig.utils import get_role_title
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url

from .forms import (
    DUTY_ROLE_FIELDS,
    DutyAssignmentForm,
    DutyPreferenceForm,
    DutyRosterMessageForm,
)
from .models import (
    DutyAssignment,
    DutyAssignmentRole,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutyRoleDefinition,
    DutyRosterMessage,
    DutySwapRequest,
    GliderReservation,
    MemberBlackout,
    OpsIntent,
)
from .roster_generator import (
    calculate_assignment_cap,
    count_calendar_months_inclusive,
    generate_roster,
    get_default_max_assignments_per_month,
    get_operational_season_bounds,
    get_weekend_dates_in_range,
    is_within_operational_season,
    resolve_roster_date_range,
)
from .utils.role_resolution import RoleResolutionService
from .utils.roles import member_is_commercial_pilot

logger = logging.getLogger("duty_roster.views")

# Allowed roles for roster slot editing/assignment endpoints
ALLOWED_ROLES = [
    "instructor",
    "duty_officer",
    "assistant_duty_officer",
    "towpilot",
    "commercial_pilot",
]
MAX_PROPOSAL_RANGE_MONTHS = 12

# OpsIntent activity keys that contribute to tow demand/surge calculations.
TOW_INTENT_KEYS = {"club", "club_single", "club_two", "guest", "private"}


def _is_commercial_pilot_qualified(member):
    return member_is_commercial_pilot(member)


def calendar_refresh_response(year, month):
    """Helper function to create HTMX response that refreshes calendar with month context"""
    trigger_data = {"refreshCalendar": {"year": int(year), "month": int(month)}}
    return HttpResponse(headers={"HX-Trigger": json.dumps(trigger_data)})


def _get_dynamic_role_assignments(
    assignment,
    site_config,
    *,
    role_service=None,
    enabled_roles=None,
    role_labels_by_key=None,
):
    """Return assigned non-legacy dynamic roles for an assignment."""
    if not assignment or not site_config or not site_config.enable_dynamic_duty_roles:
        return []

    role_service = role_service or RoleResolutionService(site_configuration=site_config)
    enabled_roles = (
        enabled_roles if enabled_roles is not None else role_service.get_enabled_roles()
    )
    role_labels_by_key = role_labels_by_key or {}
    legacy_to_swap_role = {
        "instructor": "INSTRUCTOR",
        "towpilot": "TOW",
        "duty_officer": "DO",
        "assistant_duty_officer": "ADO",
    }
    role_rows_by_key = {row.role_key: row for row in assignment.role_rows.all()}
    dynamic_role_assignments = []
    for role_key in enabled_roles:
        # Legacy role keys are rendered from fixed assignment fields.
        if role_key in DutyAssignment.LEGACY_ROLE_TO_FIELD:
            continue

        role_row = role_rows_by_key.get(role_key)
        member = role_row.member if role_row and role_row.member else None
        if not member:
            continue

        label = role_labels_by_key.get(role_key)
        if label is None:
            label = role_service.get_role_label(role_key)

        legacy_role_key = ""
        if role_row:
            legacy_role_key = role_row.legacy_role_key or ""
            if not legacy_role_key and role_row.role_definition:
                legacy_role_key = role_row.role_definition.legacy_role_key or ""

        swap_role_code = legacy_to_swap_role.get(legacy_role_key)
        if swap_role_code:
            # The current swap workflow enforces legacy duty-field assignment ownership.
            legacy_field_name = DutyAssignment.LEGACY_ROLE_TO_FIELD.get(legacy_role_key)
            assigned_legacy_member = (
                getattr(assignment, legacy_field_name, None)
                if legacy_field_name
                else None
            )
            if assigned_legacy_member != member:
                swap_role_code = None

        dynamic_role_assignments.append(
            {
                "key": role_key,
                "label": label,
                "member": member,
                "legacy_role_key": legacy_role_key,
                "swap_role_code": swap_role_code,
            }
        )

    return dynamic_role_assignments


def roster_home(request):
    return HttpResponse("Duty Roster Home")


@active_member_required
@never_cache
def blackout_manage(request):
    member = request.user
    preference, _ = DutyPreference.objects.get_or_create(member=member)

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
    role_form_key_map = {
        "assistant_duty_officer": "ado",
    }
    all_possible_roles = [
        role_form_key_map.get(role_attr, role_attr)
        for role_attr, _field_name in DUTY_ROLE_FIELDS
    ]

    site_config = SiteConfiguration.objects.first()
    dynamic_mode_enabled = bool(site_config and site_config.enable_dynamic_duty_roles)
    has_active_dynamic_role_definitions = False
    dynamic_roles_by_legacy = {}
    if dynamic_mode_enabled:
        active_dynamic_roles = DutyRoleDefinition.objects.filter(
            site_configuration=site_config,
            is_active=True,
        ).order_by("sort_order", "display_name", "key")
        has_active_dynamic_role_definitions = active_dynamic_roles.exists()
        for role_def in active_dynamic_roles.filter(
            legacy_role_key__isnull=False,
        ).exclude(legacy_role_key=""):
            dynamic_roles_by_legacy.setdefault(role_def.legacy_role_key, []).append(
                role_def.display_name
            )

    def _is_role_scheduled(legacy_role_key, legacy_schedule_flag):
        if dynamic_mode_enabled and has_active_dynamic_role_definitions:
            return bool(dynamic_roles_by_legacy.get(legacy_role_key))
        if site_config is None:
            return True
        return bool(legacy_schedule_flag)

    def _role_label_with_dynamic_variants(legacy_role_key, default_label):
        base_label = get_role_title(legacy_role_key) or default_label
        variants = dynamic_roles_by_legacy.get(legacy_role_key, [])
        if variants:
            seen = set()
            deduped = [v for v in variants if not (v in seen or seen.add(v))]
            return f"{base_label} ({', '.join(deduped)})"
        return base_label

    role_schedule_flags = {
        "instructor": _is_role_scheduled(
            "instructor", site_config and site_config.schedule_instructors
        ),
        "duty_officer": _is_role_scheduled(
            "duty_officer", site_config and site_config.schedule_duty_officers
        ),
        "ado": _is_role_scheduled(
            "assistant_duty_officer",
            site_config and site_config.schedule_assistant_duty_officers,
        ),
        "towpilot": _is_role_scheduled(
            "towpilot", site_config and site_config.schedule_tow_pilots
        ),
        "commercial_pilot": _is_role_scheduled(
            "commercial_pilot",
            site_config and site_config.schedule_commercial_pilots,
        ),
    }
    scheduled_roles_for_form = {
        "instructor": role_schedule_flags["instructor"],
        "duty_officer": role_schedule_flags["duty_officer"],
        "assistant_duty_officer": role_schedule_flags["ado"],
        "towpilot": role_schedule_flags["towpilot"],
        "commercial_pilot": role_schedule_flags["commercial_pilot"],
    }
    scheduled_roles = [
        role for role, is_scheduled in scheduled_roles_for_form.items() if is_scheduled
    ]

    role_choices = []
    if member.instructor and role_schedule_flags["instructor"]:
        role_choices.append(
            (
                "instructor",
                _role_label_with_dynamic_variants("instructor", "Instructor"),
            )
        )
    if member.duty_officer and role_schedule_flags["duty_officer"]:
        role_choices.append(
            (
                "duty_officer",
                _role_label_with_dynamic_variants("duty_officer", "Duty Officer"),
            )
        )
    if member.assistant_duty_officer and role_schedule_flags["ado"]:
        role_choices.append(
            (
                "ado",
                _role_label_with_dynamic_variants(
                    "assistant_duty_officer", "Assistant Duty Officer"
                ),
            )
        )
    if member.towpilot and role_schedule_flags["towpilot"]:
        role_choices.append(
            (
                "towpilot",
                _role_label_with_dynamic_variants("towpilot", "Tow Pilot"),
            )
        )
    if (
        _is_commercial_pilot_qualified(member)
        and role_schedule_flags["commercial_pilot"]
    ):
        role_choices.append(
            (
                "commercial_pilot",
                _role_label_with_dynamic_variants(
                    "commercial_pilot", "Commercial Pilot"
                ),
            )
        )
    shown_roles = [role for role, _label in role_choices]

    pair_with = list(
        Member.objects.filter(pairing_target__member=member).order_by(
            "last_name", "first_name"
        )
    )
    avoid_with = list(
        Member.objects.filter(avoid_target__member=member).order_by(
            "last_name", "first_name"
        )
    )
    pair_with_ids = {m.id for m in pair_with}
    avoid_with_ids = {m.id for m in avoid_with}

    # Create optgroups for member pairing fields (similar to logsheet forms)
    active_statuses = get_active_membership_statuses()

    # Active members (excluding current user)
    active_members = (
        Member.objects.filter(membership_status__in=active_statuses, is_active=True)
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

        # Ensure percent fields are always present even when hidden by role/config filtering.
        # This mirrors template hidden inputs and protects direct POST clients.
        post_data = request.POST.copy()
        for _role_attr, percent_field in DUTY_ROLE_FIELDS:
            if percent_field not in post_data:
                post_data[percent_field] = "0"

        # Try to process duty preferences, but don't let it block blackout updates
        form = DutyPreferenceForm(
            post_data,
            member=member,
            scheduled_roles=scheduled_roles,
        )
        form_is_valid = form.is_valid()
        if not form_is_valid:
            # Add form errors to messages so user can see them
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        if form_is_valid:
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
                    "commercial_pilot_percent": data["commercial_pilot_percent"] or 0,
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
            "commercial_pilot_percent": preference.commercial_pilot_percent,
            "max_assignments_per_month": preference.max_assignments_per_month,
            "allow_weekend_double": preference.allow_weekend_double,
            "comment": preference.comment,
            "pair_with": list(pair_with_ids),
            "avoid_with": list(avoid_with_ids),
        }
        form = DutyPreferenceForm(
            initial=initial,
            member=member,
            scheduled_roles=scheduled_roles,
        )

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
            "pair_with_ids": pair_with_ids,
            "avoid_with_ids": avoid_with_ids,
            "all_other_members": all_other,
            "member_optgroups": member_optgroups,
            "all_possible_roles": all_possible_roles,
            "shown_roles": shown_roles,
            "form": form,
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


def get_instruction_max_students_per_instructor():
    """Get accepted-student cap per instructor from SiteConfiguration."""
    config = cache.get("siteconfig_instance", _SITECONFIG_CACHE_SENTINEL)
    if config is _SITECONFIG_CACHE_SENTINEL:
        config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", config, timeout=60)

    if not config:
        return 4

    return getattr(
        config,
        "instruction_max_students_per_instructor",
        config.instruction_surge_threshold,
    )


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


def _build_agenda_quick_actions(
    request,
    day_date,
    assignment,
    site_config,
    active_statuses,
    intent_dates,
    instruction_dates,
    open_swap_keys,
):
    """Build quick actions for an agenda day card based on user/day state."""
    actions = []
    is_authenticated = request.user.is_authenticated
    is_active_member = bool(
        is_authenticated
        and request.user.is_active
        and request.user.membership_status in active_statuses
    )
    is_past = day_date < date.today()
    has_intent = day_date in intent_dates
    has_instruction_request = day_date in instruction_dates

    # Plan to Fly
    if has_intent:
        actions.append(
            {
                "key": "plan_to_fly_edit",
                "label": "Edit Plan to Fly",
                "enabled": True,
                "icon": "fas fa-pen",
                "kind": "modal",
                "url": reverse(
                    "duty_roster:calendar_day_detail",
                    kwargs={
                        "year": day_date.year,
                        "month": day_date.month,
                        "day": day_date.day,
                    },
                )
                + "?open_panel=plan_to_fly",
            }
        )
        actions.append(
            {
                "key": "plan_to_fly_cancel",
                "label": "Cancel Plan to Fly",
                "enabled": True,
                "icon": "fas fa-ban",
                "kind": "modal",
                "url": reverse(
                    "duty_roster:calendar_day_detail",
                    kwargs={
                        "year": day_date.year,
                        "month": day_date.month,
                        "day": day_date.day,
                    },
                )
                + "?open_panel=plan_to_fly",
            }
        )
    else:
        plan_reason = ""
        if is_past:
            plan_reason = "Unavailable for past dates."
        elif not is_active_member:
            plan_reason = "Active membership is required."
        elif has_instruction_request:
            plan_reason = "You already requested instruction for this day."

        actions.append(
            {
                "key": "plan_to_fly",
                "label": "Plan to Fly",
                "enabled": plan_reason == "",
                "disabled_reason": plan_reason,
                "icon": "fas fa-plane-departure",
                "kind": "modal",
                "url": reverse(
                    "duty_roster:calendar_day_detail",
                    kwargs={
                        "year": day_date.year,
                        "month": day_date.month,
                        "day": day_date.day,
                    },
                )
                + "?open_panel=plan_to_fly",
            }
        )

    # Request Instruction
    instruction_reason = ""
    has_instructor_assigned = bool(
        assignment and (assignment.instructor_id or assignment.surge_instructor_id)
    )
    too_early, opens_on = _check_instruction_request_window(day_date)
    if is_past:
        instruction_reason = "Unavailable for past dates."
    elif not is_active_member:
        instruction_reason = "Active membership is required."
    elif has_instruction_request:
        instruction_reason = "You already have an instruction request for this day."
    elif not has_instructor_assigned:
        instruction_reason = "No instructor is currently assigned for this day."
    elif too_early:
        opens_str = opens_on.strftime("%b %d, %Y") if opens_on else "a later date"
        instruction_reason = f"Instruction requests open on {opens_str}."

    actions.append(
        {
            "key": "request_instruction",
            "label": "Request Instruction",
            "enabled": instruction_reason == "",
            "disabled_reason": instruction_reason,
            "icon": "fas fa-graduation-cap",
            "kind": "modal",
            "url": reverse(
                "duty_roster:calendar_day_detail",
                kwargs={
                    "year": day_date.year,
                    "month": day_date.month,
                    "day": day_date.day,
                },
            )
            + "?open_panel=request_instruction",
        }
    )

    # Reserve a Glider
    reserve_reason = ""
    reservation_feature_enabled = bool(
        site_config and site_config.allow_glider_reservations
    )
    can_reserve_glider = False
    if is_past:
        reserve_reason = "Unavailable for past dates."
    elif not is_active_member:
        reserve_reason = "Active membership is required."
    elif not reservation_feature_enabled:
        reserve_reason = "Glider reservations are currently disabled."
    else:
        cache_attr = "_glider_reservation_eligibility_cache"
        if not hasattr(request, cache_attr):
            setattr(request, cache_attr, {})
        eligibility_cache = getattr(request, cache_attr)
        cache_key = (day_date.year, day_date.month)
        if cache_key not in eligibility_cache:
            eligibility_cache[cache_key] = GliderReservation.can_member_reserve(
                request.user,
                year=day_date.year,
                month=day_date.month,
                config=site_config,
            )
        can_reserve_glider, reserve_reason = eligibility_cache[cache_key]

    actions.append(
        {
            "key": "reserve_glider",
            "label": "Reserve a Glider",
            "enabled": can_reserve_glider,
            "disabled_reason": reserve_reason,
            "icon": "fas fa-calendar-check",
            "kind": "link",
            "url": reverse(
                "duty_roster:reservation_create_for_day",
                kwargs={
                    "year": day_date.year,
                    "month": day_date.month,
                    "day": day_date.day,
                },
            ),
        }
    )

    # Request Swap (only if this user is assigned to one or more scheduled roles)
    assigned_roles = []
    if assignment and is_authenticated:
        if assignment.instructor_id == request.user.id:
            assigned_roles.append(("INSTRUCTOR", get_role_title("instructor")))
        if assignment.tow_pilot_id == request.user.id:
            assigned_roles.append(("TOW", get_role_title("towpilot")))
        if assignment.duty_officer_id == request.user.id:
            assigned_roles.append(("DO", get_role_title("duty_officer")))
        if assignment.assistant_duty_officer_id == request.user.id:
            assigned_roles.append(("ADO", get_role_title("assistant_duty_officer")))

    scheduled_map = {
        "INSTRUCTOR": bool(site_config and site_config.schedule_instructors),
        "TOW": bool(site_config and site_config.schedule_tow_pilots),
        "DO": bool(site_config and site_config.schedule_duty_officers),
        "ADO": bool(site_config and site_config.schedule_assistant_duty_officers),
    }

    for role_code, role_title in assigned_roles:
        swap_reason = ""
        if is_past:
            swap_reason = "Unavailable for past dates."
        elif not is_active_member:
            swap_reason = "Active membership is required."
        elif not scheduled_map.get(role_code, False):
            swap_reason = f"{role_title} is not currently a scheduled role."
        elif (day_date, role_code) in open_swap_keys:
            swap_reason = "You already have an open swap request for this role."

        label = "Request Swap"
        if len(assigned_roles) > 1:
            label = f"Request Swap ({role_title})"

        actions.append(
            {
                "key": f"request_swap_{role_code.lower()}",
                "label": label,
                "enabled": swap_reason == "",
                "disabled_reason": swap_reason,
                "icon": "fas fa-exchange-alt",
                "kind": "link",
                "url": reverse(
                    "duty_roster:create_swap_request",
                    kwargs={
                        "year": day_date.year,
                        "month": day_date.month,
                        "day": day_date.day,
                        "role": role_code,
                    },
                ),
            }
        )

    # Review Student Requests (instructor roles)
    if is_authenticated and getattr(request.user, "instructor", False):
        review_reason = ""
        if not is_active_member:
            review_reason = "Active membership is required."

        actions.append(
            {
                "key": "review_student_requests",
                "label": "Review Student Requests",
                "enabled": review_reason == "",
                "disabled_reason": review_reason,
                "icon": "fas fa-user-check",
                "kind": "link",
                "url": reverse("duty_roster:instructor_requests"),
            }
        )

    return actions


def duty_calendar_view(request, year=None, month=None):
    today = date.today()
    year = int(year) if year else today.year
    month = int(month) if month else today.month

    # Get site config for surge thresholds
    tow_surge_threshold, instruction_surge_threshold = get_surge_thresholds()
    instruction_max_students_per_instructor = (
        get_instruction_max_students_per_instructor()
    )

    site_config = cache.get("siteconfig_instance", _SITECONFIG_CACHE_SENTINEL)
    if site_config is _SITECONFIG_CACHE_SENTINEL:
        site_config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", site_config, timeout=60)

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(year, month)
    first_visible_day = weeks[0][0]
    last_visible_day = weeks[-1][-1]
    assignments = (
        DutyAssignment.objects.filter(date__range=(first_visible_day, last_visible_day))
        .prefetch_related(
            models.Prefetch(
                "role_rows",
                queryset=DutyAssignmentRole.objects.select_related(
                    "role_definition", "member"
                ),
            )
        )
        .order_by("date")
    )
    visible_dates = [day for week in weeks for day in week]

    assignments_by_date = {a.date: a for a in assignments}
    role_service = RoleResolutionService(site_configuration=site_config)
    enabled_role_keys = (
        role_service.get_enabled_roles()
        if site_config and site_config.enable_dynamic_duty_roles
        else []
    )
    role_labels_by_key = {}
    if enabled_role_keys:
        role_definitions_by_key = {
            role_def.key: role_def
            for role_def in DutyRoleDefinition.objects.filter(
                site_configuration=site_config,
                is_active=True,
                key__in=enabled_role_keys,
            )
        }
        for role_key in enabled_role_keys:
            role_def = role_definitions_by_key.get(role_key)
            if role_def:
                role_labels_by_key[role_key] = (
                    get_role_title(role_def.legacy_role_key)
                    if role_def.legacy_role_key
                    else role_def.display_name
                )
            else:
                role_labels_by_key[role_key] = get_role_title(role_key)
    dynamic_role_assignments_by_date = {
        assignment.date: _get_dynamic_role_assignments(
            assignment,
            site_config,
            role_service=role_service,
            enabled_roles=enabled_role_keys,
            role_labels_by_key=role_labels_by_key,
        )
        for assignment in assignments
    }

    active_statuses = set(get_active_membership_statuses())

    intent_dates = set()
    instruction_dates = set()
    open_swap_keys = set()
    if request.user.is_authenticated:
        intent_dates = set(
            OpsIntent.objects.filter(member=request.user, date__in=visible_dates)
            .values_list("date", flat=True)
            .iterator()
        )

        from .models import InstructionSlot

        instruction_dates = set(
            InstructionSlot.objects.filter(
                assignment__date__in=visible_dates,
                student=request.user,
            )
            .exclude(status="cancelled")
            .values_list("assignment__date", flat=True)
            .iterator()
        )

        open_swap_keys = set(
            DutySwapRequest.objects.filter(
                requester=request.user,
                original_date__in=visible_dates,
                status="open",
            )
            .values_list("original_date", "role")
            .iterator()
        )

    agenda_quick_actions_by_date = {}
    for day, assignment in assignments_by_date.items():
        agenda_quick_actions_by_date[day] = _build_agenda_quick_actions(
            request=request,
            day_date=day,
            assignment=assignment,
            site_config=site_config,
            active_statuses=active_statuses,
            intent_dates=intent_dates,
            instruction_dates=instruction_dates,
            open_swap_keys=open_swap_keys,
        )

    prev_year, prev_month, next_year, next_month = get_adjacent_months(year, month)

    # Then safely run these:
    instruction_count = defaultdict(int)
    tow_count = defaultdict(int)

    # Instruction surge: count non-cancelled InstructionSlots per date.
    # (The 'instruction' OpsIntent checkbox was removed in Issue #679 as ambiguous;
    # actual InstructionSlot records are the authoritative signal.)
    from .models import InstructionSlot as _IS

    for row in (
        _IS.objects.filter(assignment__date__in=visible_dates)
        .exclude(status="cancelled")
        .values("assignment__date")
        .annotate(_count=models.Count("id"))
    ):
        instruction_count[row["assignment__date"]] += row["_count"]

    # Tow surge: driven by tow-relevant OpsIntent activity flags (Issue #803).
    intents = OpsIntent.objects.filter(date__in=visible_dates)
    for intent in intents:
        roles = intent.available_as or []
        if any(key in TOW_INTENT_KEYS for key in roles):
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
        "dynamic_role_assignments_by_date": dynamic_role_assignments_by_date,
        "has_upcoming_assignments": has_upcoming_assignments,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "today": today,
        "agenda_quick_actions_by_date": agenda_quick_actions_by_date,
        "surge_needed_by_date": surge_needed_by_date,
        "tow_surge_threshold": tow_surge_threshold,
        "instruction_surge_threshold": instruction_surge_threshold,
        "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
    }

    if request.htmx:
        return render(request, "duty_roster/_calendar_body.html", context)
    return render(request, "duty_roster/calendar.html", context)


def calendar_day_detail(request, year, month, day):
    day_date = date(year, month, day)
    assignment = (
        DutyAssignment.objects.filter(date=day_date)
        .prefetch_related(
            models.Prefetch(
                "role_rows",
                queryset=DutyAssignmentRole.objects.select_related(
                    "member", "role_definition"
                ),
            )
        )
        .first()
    )
    open_panel = request.GET.get("open_panel", "")
    if open_panel not in {"plan_to_fly", "request_instruction"}:
        open_panel = ""

    # Get site config for surge thresholds
    tow_surge_threshold, instruction_surge_threshold = get_surge_thresholds()
    instruction_max_students_per_instructor = (
        get_instruction_max_students_per_instructor()
    )

    # Show current user intent status
    intent_exists = False
    intent_blocked_reason = ""
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

    # Check for instruction-specific intent via InstructionSlots (Issue #679 –
    # the 'instruction' checkbox was removed from OpsIntent as ambiguous; use
    # actual instruction requests instead to drive the surge alert).
    from .models import InstructionSlot as _InstructionSlot

    instruction_intent_count = (
        _InstructionSlot.objects.filter(assignment=assignment)
        .exclude(status="cancelled")
        .count()
        if assignment
        else 0
    )
    tow_count = sum(
        1 for i in intents if any(key in TOW_INTENT_KEYS for key in i.available_as)
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

        if user_has_instruction_request and not intent_exists:
            can_submit_intent = False
            intent_blocked_reason = (
                "You already requested instruction for this day. "
                "Use only Request Instruction or cancel that request first."
            )

    site_config = cache.get("siteconfig_instance", _SITECONFIG_CACHE_SENTINEL)
    if site_config is _SITECONFIG_CACHE_SENTINEL:
        site_config = SiteConfiguration.objects.first()
        cache.set("siteconfig_instance", site_config, timeout=60)

    active_statuses = set(get_active_membership_statuses())
    can_access_reservations = bool(
        request.user.is_authenticated
        and request.user.is_active
        and request.user.membership_status in active_statuses
    )

    reservation_config = site_config
    reservation_feature_enabled = bool(
        reservation_config and reservation_config.allow_glider_reservations
    )
    reservation_enabled = bool(reservation_feature_enabled and can_access_reservations)
    day_reservations = []
    can_reserve_glider = False
    reserve_message = ""
    reservations_remaining = None
    reservation_limit_period = ReservationLimitPeriod.YEARLY
    if reservation_config is not None:
        reservation_limit_period = getattr(
            reservation_config,
            "reservation_limit_period",
            ReservationLimitPeriod.YEARLY,
        )
    reservation_period_label = (
        "quarter"
        if reservation_limit_period == ReservationLimitPeriod.QUARTERLY
        else "year"
    )

    if request.user.is_authenticated and reservation_enabled:
        day_reservations = GliderReservation.get_reservations_for_date(day_date)
        can_reserve_glider, reserve_message = GliderReservation.can_member_reserve(
            request.user,
            year=day_date.year,
            month=day_date.month,
            config=reservation_config,
        )

        # reservation_enabled implies reservation_config exists; keep explicit
        # guard so static type-checkers can narrow away Optional.
        if reservation_config is None:
            max_per_period = 0
        else:
            max_per_period = reservation_config.max_reservations_per_year

        if reservation_limit_period == ReservationLimitPeriod.QUARTERLY:
            current_period_count = GliderReservation.get_member_quarterly_count(
                request.user,
                year=day_date.year,
                month=day_date.month,
            )
        else:
            current_period_count = GliderReservation.get_member_yearly_count(
                request.user,
                year=day_date.year,
            )

        if max_per_period > 0:
            reservations_remaining = max(0, max_per_period - current_period_count)

    signed_up_members_by_id = {
        intent.member_id: intent.member for intent in intents if intent.member_id
    }
    signed_up_day_reservations = (
        day_reservations
        if reservation_enabled
        else GliderReservation.get_reservations_for_date(day_date)
    )
    for reservation in signed_up_day_reservations:
        if reservation.member_id:
            signed_up_members_by_id.setdefault(
                reservation.member_id,
                reservation.member,
            )
    instruction_student_ids = set()
    if assignment:
        for slot in assignment.active_instruction_slots:
            if not slot.student_id:
                continue
            instruction_student_ids.add(slot.student_id)
            signed_up_members_by_id.setdefault(slot.student_id, slot.student)
    signed_up_flyers = sorted(
        signed_up_members_by_id.values(),
        key=lambda member: (
            member.last_name.lower() if member.last_name else "",
            member.first_name.lower() if member.first_name else "",
            member.username.lower() if member.username else "",
        ),
    )
    signed_up_non_instruction_flyers = [
        member
        for member in signed_up_flyers
        if member.id not in instruction_student_ids
    ]

    # Determine scheduled but empty roles (visible to all users as an "unfilled" indicator)
    # and the subset the current user is qualified to volunteer for (Issue #679).
    scheduled_holes = {}
    volunteerable_holes = {}
    if assignment and day_date >= date.today():
        if site_config:
            if site_config.schedule_instructors and not assignment.instructor:
                scheduled_holes["instructor"] = True
            if site_config.schedule_tow_pilots and not assignment.tow_pilot:
                scheduled_holes["tow_pilot"] = True
            if site_config.schedule_duty_officers and not assignment.duty_officer:
                scheduled_holes["duty_officer"] = True
            if (
                site_config.schedule_assistant_duty_officers
                and not assignment.assistant_duty_officer
            ):
                scheduled_holes["assistant_duty_officer"] = True
            if (
                site_config.schedule_commercial_pilots
                and not assignment.commercial_pilot
            ):
                scheduled_holes["commercial_pilot"] = True

        if request.user.is_authenticated and scheduled_holes:
            for hole_role in scheduled_holes:
                qual_attr = _HOLE_FILL_ROLE_MAP[hole_role][0]
                is_qualified = (
                    _is_commercial_pilot_qualified(request.user)
                    if qual_attr == "__commercial_rating__"
                    else bool(getattr(request.user, qual_attr, False))
                )
                if is_qualified:
                    volunteerable_holes[hole_role] = True

    dynamic_role_assignments = _get_dynamic_role_assignments(assignment, site_config)
    user_dynamic_role_assignments = []
    if request.user.is_authenticated and dynamic_role_assignments:
        user_dynamic_role_assignments = [
            role
            for role in dynamic_role_assignments
            if role["member"].id == request.user.id
        ]

    return render(
        request,
        "duty_roster/calendar_day_modal.html",
        {
            "day": day_date,
            "assignment": assignment,
            "intent_exists": intent_exists,
            "intent_blocked_reason": intent_blocked_reason,
            "can_submit_intent": can_submit_intent,
            "intents": intents,
            "show_surge_alert": show_surge_alert,
            "instruction_intent_count": instruction_intent_count,
            "tow_count": tow_count,
            "show_tow_surge_alert": show_tow_surge_alert,
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
            "today": date.today(),
            "user_has_instruction_request": user_has_instruction_request,
            "instruction_request_form": instruction_request_form,
            "instruction_request_too_early": instruction_request_too_early,
            "instruction_request_opens_on": instruction_request_opens_on,
            "has_instructor_assigned": bool(
                assignment and (assignment.instructor or assignment.surge_instructor)
            ),
            "scheduled_holes": scheduled_holes,
            "volunteerable_holes": volunteerable_holes,
            # Surge-volunteer eligibility flags (Issue #688).
            # True when the primary slot is filled, the surge slot is empty,
            # the user is qualified, and the day is today or in the future.
            "can_volunteer_surge_instructor": bool(
                assignment
                and day_date >= date.today()
                and request.user.is_authenticated
                and getattr(request.user, "instructor", False)
                and assignment.instructor_id is not None
                and assignment.surge_instructor_id is None
                and request.user.id != assignment.instructor_id
            ),
            "can_volunteer_surge_tow_pilot": bool(
                assignment
                and day_date >= date.today()
                and request.user.is_authenticated
                and getattr(request.user, "towpilot", False)
                and assignment.tow_pilot_id is not None
                and assignment.surge_tow_pilot_id is None
                and request.user.id != assignment.tow_pilot_id
            ),
            "reservation_enabled": reservation_enabled,
            "reservation_feature_enabled": reservation_feature_enabled,
            "can_access_reservations": can_access_reservations,
            "day_reservations": day_reservations,
            "can_reserve_glider": can_reserve_glider,
            "reserve_message": reserve_message,
            "reservations_remaining": reservations_remaining,
            "reservation_period_label": reservation_period_label,
            "signed_up_flyers": signed_up_flyers,
            "signed_up_flyer_count": len(signed_up_flyers),
            "signed_up_non_instruction_flyers": signed_up_non_instruction_flyers,
            "signed_up_non_instruction_flyer_count": len(
                signed_up_non_instruction_flyers
            ),
            "available_activities": OpsIntent.AVAILABLE_ACTIVITIES,
            "open_panel": open_panel,
            "dynamic_role_assignments": dynamic_role_assignments,
            "user_dynamic_role_assignments": user_dynamic_role_assignments,
        },
    )


@require_POST
def ops_intent_toggle(request, year, month, day):
    if not request.user.is_authenticated:
        return HttpResponse("Not authorized", status=403)

    from django.conf import settings

    day_date = date(year, month, day)
    available_as = request.POST.getlist("available_as") or []

    assignment = DutyAssignment.objects.filter(date=day_date).first()

    if request.user.is_authenticated and assignment and available_as:
        from .models import InstructionSlot

        has_instruction_request = (
            InstructionSlot.objects.filter(
                assignment=assignment,
                student=request.user,
            )
            .exclude(status="cancelled")
            .exists()
        )
        if has_instruction_request:
            warning_html = (
                '<p class="text-warning mb-2">⚠️ You already requested instruction for this day. '
                "Use one workflow at a time to avoid duplicate planning.</p>"
            )
            form_html = render_to_string(
                "duty_roster/ops_intent_form.html",
                {
                    "day": day_date,
                    "available_activities": OpsIntent.AVAILABLE_ACTIVITIES,
                },
                request=request,
            )
            return HttpResponse(f"{warning_html}{form_html}")

    # remember prior intent so we only email on true cancellations
    old_intent = OpsIntent.objects.filter(member=request.user, date=day_date).first()
    old_available = old_intent.available_as if old_intent else []

    # enforce site-configured instruction request window (Issue #648)
    if "instruction" in available_as:
        too_early_intent, opens_on_intent = _check_instruction_request_window(day_date)
        if too_early_intent:
            opens_str = (
                opens_on_intent.strftime("%B %d, %Y")
                if opens_on_intent
                else "a future date"
            )
            warning_html = format_html(
                '<p class="text-danger mb-2">⏰ Instruction requests for this date do not open until {}.</p>',
                opens_str,
            )
            form_html = render_to_string(
                "duty_roster/ops_intent_form.html",
                {
                    "day": day_date,
                    "available_activities": OpsIntent.AVAILABLE_ACTIVITIES,
                },
                request=request,
            )
            return HttpResponse(f"{warning_html}{form_html}")

    # SIGNUP FLOW
    if available_as:
        OpsIntent.objects.update_or_create(
            member=request.user, date=day_date, defaults={"available_as": available_as}
        )

        assignment, _ = DutyAssignment.objects.get_or_create(date=day_date)
        duty_inst = assignment.instructor
        surge_inst = assignment.surge_instructor

        notify_keys = {"club_single", "club_two", "guest", "club"}
        should_notify_instructors = any(k in notify_keys for k in available_as)

        # recipients: duty instructor plus (if exists) surge instructor
        recipients = []
        if duty_inst and duty_inst.email:
            recipients.append(duty_inst.email)
        if surge_inst and surge_inst.email:
            recipients.append(surge_inst.email)

        if recipients and should_notify_instructors:
            intent_labels = OpsIntent(
                member=request.user,
                date=day_date,
                available_as=available_as,
            ).available_as_labels()
            # Prepare template context
            email_config = get_email_config()

            context = {
                "member_name": request.user.full_display_name,
                "instructor_name": (
                    duty_inst.full_display_name if duty_inst else "Instructor"
                ),
                "ops_date": day_date.strftime("%A, %B %d, %Y"),
                "intent_labels": intent_labels,
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
                subject=f"[{email_config['club_name']}] Member Flight Intent - {day_date:%b %d}",
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
        info_html = (
            '<p class="text-gray-700 mb-2">❌ You\'ve removed your intent to fly.</p>'
        )
        form_html = render_to_string(
            "duty_roster/ops_intent_form.html",
            {
                "day": day_date,
                "available_activities": OpsIntent.AVAILABLE_ACTIVITIES,
            },
            request=request,
        )
        response = f"{info_html}{form_html}"

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
    instruction_max_students_per_instructor = (
        get_instruction_max_students_per_instructor()
    )

    # Use InstructionSlot records as the authoritative instruction-demand signal.
    # (The 'instruction' OpsIntent checkbox was removed in Issue #679.)
    from .models import InstructionSlot

    instruction_count = (
        InstructionSlot.objects.filter(assignment=assignment)
        .exclude(status="cancelled")
        .count()
    )

    if instruction_count >= instruction_surge_threshold:
        # Prepare template context
        email_config = get_email_config()
        recipient_list = get_mailing_list(
            "INSTRUCTORS_MAILING_LIST", "instructors", email_config["config"]
        )
        volunteer_url = build_absolute_url(
            reverse("duty_roster:volunteer_surge_instructor", args=[assignment.id]),
            canonical=email_config["site_url"],
        )

        context = {
            "student_count": instruction_count,
            "ops_date": day_date.strftime("%A, %B %d, %Y"),
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(email_config["config"]),
            "roster_url": email_config["roster_url"],
            "volunteer_url": volunteer_url,
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
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
        1 for i in intents if any(key in TOW_INTENT_KEYS for key in i.available_as)
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
        assignment.refresh_from_db()  # type: ignore[call-arg]
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
        assignment.refresh_from_db()  # type: ignore[call-arg]
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

        # Validate role is one of the allowed role names (security).
        # If dynamic roles are enabled, include enabled dynamic role keys.
        site_config = SiteConfiguration.objects.first()
        allowed = set(ALLOWED_ROLES)
        if site_config and site_config.enable_dynamic_duty_roles:
            allowed.update(
                RoleResolutionService(
                    site_configuration=site_config
                ).get_enabled_roles()
            )
        if role not in allowed:
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

        range_months = 1
        start_date_raw = request.POST.get("start_date")
        end_date_raw = request.POST.get("end_date")

        if start_date_raw and end_date_raw:
            try:
                selected_start, selected_end = resolve_roster_date_range(
                    start_date=dt_date.fromisoformat(start_date_raw),
                    end_date=dt_date.fromisoformat(end_date_raw),
                )
                range_months = count_calendar_months_inclusive(
                    selected_start, selected_end
                )
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid selected range in eligible-member request: %s to %s",
                    start_date_raw,
                    end_date_raw,
                )

        if range_months == 1:
            draft_range = _get_draft_date_range(draft)
            if draft_range:
                range_months = count_calendar_months_inclusive(
                    draft_range[0], draft_range[1]
                )

        # Find eligible members
        default_cap = calculate_assignment_cap(
            get_default_max_assignments_per_month(), range_months
        )
        eligible_members = []

        # If dynamic roles are enabled, precompute eligible member ids for the
        # requested dynamic role to avoid per-member attribute checks that
        # don't exist for dynamic keys (e.g. "am_tow"). Use RoleResolutionService
        # which applies qualification requirements and legacy-role fallbacks.
        role_service = RoleResolutionService(site_configuration=site_config)
        dynamic_role_keys = set()
        dynamic_role_legacy_by_key = {}
        if site_config and site_config.enable_dynamic_duty_roles:
            dynamic_role_rows = DutyRoleDefinition.objects.filter(
                site_configuration=site_config,
                is_active=True,
            ).values("key", "legacy_role_key")
            dynamic_role_keys = {row["key"] for row in dynamic_role_rows}
            dynamic_role_legacy_by_key = {
                row["key"]: row["legacy_role_key"] for row in dynamic_role_rows
            }

        dynamic_role_eligible_ids = None
        dynamic_role_legacy_key = None
        if role in dynamic_role_keys:
            dynamic_role_eligible_ids = role_service.get_eligible_member_ids(
                role, members_queryset=Member.objects.filter(is_active=True)
            )
            # Derive a legacy_role_key (if any) for preference percent field lookups
            dynamic_role_legacy_key = dynamic_role_legacy_by_key.get(role)

        for m in members:
            # If we have a computed dynamic-eligibility set, only consider members
            # whose IDs are included. Otherwise fall back to legacy attribute checks.
            if dynamic_role_eligible_ids is not None:
                if m.id not in dynamic_role_eligible_ids:
                    continue
                has_role = True
            else:
                # Check if member has the role flag
                has_role = (
                    _is_commercial_pilot_qualified(m)
                    if role == "commercial_pilot"
                    else bool(getattr(m, role, False))
                )
                if not has_role:
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
                at_max = assignments[m.id] >= default_cap

                eligible_members.append(
                    {
                        "id": m.id,
                        "name": m.full_display_name,
                        "warnings": {
                            "avoids_someone": avoids,
                            "already_assigned": already_assigned,
                            "at_max": at_max,
                        },
                        "assignments_in_range": assignments[m.id],
                        "max_assignments": default_cap,
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

            # Check percentage. For dynamic roles, prefer legacy role mapping
            # when determining which percent field applies (e.g. am_tow -> towpilot).
            percent_fields = [
                ("instructor", "instructor_percent"),
                ("duty_officer", "duty_officer_percent"),
                ("assistant_duty_officer", "ado_percent"),
                ("towpilot", "towpilot_percent"),
                ("commercial_pilot", "commercial_pilot_percent"),
            ]
            percent_field_by_role = {r: field for r, field in percent_fields}
            effective_role_for_flag = dynamic_role_legacy_key or role
            eligible_role_fields = [
                field
                for r, field in percent_fields
                if (
                    _is_commercial_pilot_qualified(m)
                    if r == "commercial_pilot"
                    else getattr(m, r, False)
                )
            ]

            if len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                pct = getattr(p, field, 0)
                if pct == 0:
                    pct = 100
            else:
                all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
                target_field = percent_field_by_role.get(
                    effective_role_for_flag,
                    f"{effective_role_for_flag}_percent",
                )
                if all_zero:
                    pct = 100
                elif hasattr(p, target_field):
                    pct = getattr(p, target_field, 0)
                else:
                    pct = 100

            if pct == 0:
                continue

            # Check max assignments
            member_cap = calculate_assignment_cap(
                getattr(p, "max_assignments_per_month", 0), range_months
            )
            at_max = assignments[m.id] >= member_cap

            eligible_members.append(
                {
                    "id": m.id,
                    "name": m.full_display_name,
                    "warnings": {
                        "avoids_someone": avoids,
                        "already_assigned": already_assigned,
                        "at_max": at_max,
                    },
                    "assignments_in_range": assignments[m.id],
                    "max_assignments": member_cap,
                }
            )

        # Sort by assignments (fewest first) and name
        eligible_members.sort(key=lambda x: (x["assignments_in_range"], x["name"]))

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

    # Validate role is one of the allowed role names (security).
    site_config = SiteConfiguration.objects.first()
    allowed = set(ALLOWED_ROLES)
    if site_config and site_config.enable_dynamic_duty_roles:
        allowed.update(
            RoleResolutionService(site_configuration=site_config).get_enabled_roles()
        )
    if role not in allowed:
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
        # If dynamic roles are enabled, consult RoleResolutionService which
        # applies qualification requirements and legacy fallbacks.
        role_service = RoleResolutionService(site_configuration=site_config)
        dynamic_role_keys = set()
        dynamic_role_legacy_by_key = {}
        if site_config and site_config.enable_dynamic_duty_roles:
            dynamic_role_rows = DutyRoleDefinition.objects.filter(
                site_configuration=site_config,
                is_active=True,
            ).values("key", "legacy_role_key")
            dynamic_role_keys = {row["key"] for row in dynamic_role_rows}
            dynamic_role_legacy_by_key = {
                row["key"]: row["legacy_role_key"] for row in dynamic_role_rows
            }

        if role in dynamic_role_keys:
            if not role_service.is_member_eligible(member, role):
                return JsonResponse(
                    {"error": "Member not eligible for this role"},
                    status=400,
                )
        else:
            # For the allowed roles, the Member capability flag matches the role name
            # (e.g., member.instructor, member.duty_officer, member.towpilot).
            has_role = (
                _is_commercial_pilot_qualified(member)
                if role == "commercial_pilot"
                else bool(getattr(member, role, False))
            )
            if not has_role:
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
                ("commercial_pilot", "commercial_pilot_percent"),
            ]
            percent_field_by_role = {r: field for r, field in percent_fields}
            role_key_for_lookup = role if isinstance(role, str) else str(role)
            effective_role_for_flag_obj = (
                dynamic_role_legacy_by_key.get(role_key_for_lookup)
                if role_key_for_lookup in dynamic_role_keys
                else role_key_for_lookup
            )
            effective_role_for_flag = (
                effective_role_for_flag_obj
                if isinstance(effective_role_for_flag_obj, str)
                else role_key_for_lookup
            )
            eligible_role_fields = [
                field
                for r, field in percent_fields
                if (
                    _is_commercial_pilot_qualified(member)
                    if r == "commercial_pilot"
                    else getattr(member, r, False)
                )
            ]

            if len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                pct = getattr(pref, field, 0)
                if pct == 0:
                    pct = 100  # Single role, treat 0 as 100
            else:
                all_zero = all(getattr(pref, f, 0) == 0 for f in eligible_role_fields)
                target_field = percent_field_by_role.get(
                    effective_role_for_flag,
                    f"{effective_role_for_flag}_percent",
                )
                if all_zero:
                    pct = 100
                elif hasattr(pref, target_field):
                    pct = getattr(pref, target_field, 0)
                else:
                    pct = 100

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


def _removed_dates_session_key(start_date, end_date):
    """Build deterministic session key for removed proposed dates in a date range."""
    _, month_last_day = calendar.monthrange(start_date.year, start_date.month)
    if (
        start_date.day == 1
        and start_date.year == end_date.year
        and start_date.month == end_date.month
        and end_date.day == month_last_day
    ):
        return f"removed_roster_dates_{start_date.year}_{start_date.month:02d}"

    return f"removed_roster_dates_{start_date.isoformat()}_{end_date.isoformat()}"


def _set_proposed_roster_range(request, start_date, end_date):
    """Persist the selected proposal range used to build session draft roster."""
    request.session["proposed_roster_range"] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def _get_proposed_roster_range(request):
    """Read the persisted proposal range from session, if valid."""
    stored = request.session.get("proposed_roster_range")
    if not isinstance(stored, dict):
        return None

    start_raw = stored.get("start_date")
    end_raw = stored.get("end_date")
    if not start_raw or not end_raw:
        return None

    try:
        return resolve_roster_date_range(
            start_date=dt_date.fromisoformat(start_raw),
            end_date=dt_date.fromisoformat(end_raw),
        )
    except ValueError:
        return None


def _get_draft_date_range(draft):
    """Derive inclusive date range from draft entries, if any parseable dates exist."""
    draft_dates = []
    for entry in draft:
        date_raw = entry.get("date")
        if not date_raw:
            continue
        try:
            draft_dates.append(dt_date.fromisoformat(date_raw))
        except (TypeError, ValueError):
            continue

    if not draft_dates:
        return None
    return min(draft_dates), max(draft_dates)


def _effective_draft_range(request, draft, fallback_start, fallback_end):
    """Resolve effective range for draft-mutating actions.

    Priority: persisted selection range -> draft-derived range -> request fallback.
    """
    session_range = _get_proposed_roster_range(request)
    if session_range:
        return session_range

    draft_range = _get_draft_date_range(draft)
    if draft_range:
        return draft_range

    return fallback_start, fallback_end


def _resolve_proposal_range(request):
    """Resolve scheduling date range from request parameters."""
    start_raw = request.POST.get("start_date") or request.GET.get("start_date")
    end_raw = request.POST.get("end_date") or request.GET.get("end_date")
    year = request.POST.get("year") or request.GET.get("year")
    month = request.POST.get("month") or request.GET.get("month")

    start_date = dt_date.fromisoformat(start_raw) if start_raw else None
    end_date = dt_date.fromisoformat(end_raw) if end_raw else None
    year_val = int(year) if year else None
    month_val = int(month) if month else None

    range_start, range_end = resolve_roster_date_range(
        year=year_val,
        month=month_val,
        start_date=start_date,
        end_date=end_date,
    )

    range_months = count_calendar_months_inclusive(range_start, range_end)
    if range_months > MAX_PROPOSAL_RANGE_MONTHS:
        raise ValueError(
            f"Roster date range cannot exceed {MAX_PROPOSAL_RANGE_MONTHS} months."
        )

    return range_start, range_end


def _get_removed_dates_from_session(request, start_date, end_date, clean_invalid=False):
    """
    Parse removed dates from session for a date range.

    Args:
        request: Django HttpRequest with session data
        start_date: Inclusive range start date
        end_date: Inclusive range end date
        clean_invalid: If True, update session to remove malformed dates

    Returns:
        List of datetime.date objects (malformed entries are skipped)
    """
    session_key = _removed_dates_session_key(start_date, end_date)
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
    try:
        range_start, range_end = _resolve_proposal_range(request)
    except ValueError as exc:
        logger.warning("Invalid roster date range provided: %s", exc)
        if "cannot exceed" in str(exc):
            messages.error(
                request,
                f"Roster date range cannot exceed {MAX_PROPOSAL_RANGE_MONTHS} months.",
            )
        elif "cannot be after" in str(exc):
            messages.error(request, "Invalid roster date range.")
        else:
            messages.error(request, "Invalid roster date range.")
        today = timezone.now().date()
        range_start, range_end = resolve_roster_date_range(
            year=today.year,
            month=today.month,
        )

    year, month = range_start.year, range_start.month
    month_span = count_calendar_months_inclusive(range_start, range_end)
    incomplete = False

    # Get site config and determine which roles to schedule
    siteconfig = SiteConfiguration.objects.first()
    use_ortools_scheduler = bool(siteconfig and siteconfig.use_ortools_scheduler)
    role_service = RoleResolutionService(site_configuration=siteconfig)
    enabled_roles = role_service.get_enabled_roles()
    dynamic_role_labels = {}
    if siteconfig and siteconfig.enable_dynamic_duty_roles and enabled_roles:
        dynamic_role_labels = {
            role_def.key: role_def.display_name
            for role_def in DutyRoleDefinition.objects.filter(
                site_configuration=siteconfig,
                is_active=True,
                key__in=enabled_roles,
            )
            if role_def.display_name
        }
    role_labels = {
        role: dynamic_role_labels.get(role) or role_service.get_role_label(role)
        for role in enabled_roles
    }

    if not enabled_roles:
        # No scheduling for this club
        return render(
            request,
            "duty_roster/propose_roster.html",
            {
                "draft": [],
                "year": year,
                "month": month,
                "start_date": range_start,
                "end_date": range_end,
                "month_span": month_span,
                "incomplete": False,
                "enabled_roles": [],
                "role_labels": {},
                "no_scheduling": True,
                "use_ortools_scheduler": use_ortools_scheduler,
            },
        )

    # Get operational calendar information for display
    operational_info = {}
    filtered_dates = []
    if siteconfig:
        try:
            all_weekend_dates = get_weekend_dates_in_range(range_start, range_end)
            filtered_dates = [
                d for d in all_weekend_dates if not is_within_operational_season(d)
            ]

            if range_start.year == range_end.year:
                season_start, season_end = get_operational_season_bounds(
                    range_start.year
                )

                # Only show operational info if we have filtering enabled
                if season_start or season_end:
                    if season_start:
                        operational_info["season_start"] = season_start
                    if season_end:
                        operational_info["season_end"] = season_end
            else:
                # Avoid presenting misleading single-year season bounds for multi-year ranges.
                operational_info["range_spans_years"] = True
        except Exception:
            logger.exception("Error calculating operational season info")

    if request.method == "POST":
        action = request.POST.get("action")
        draft = request.session.get("proposed_roster", [])
        active_start, active_end = _effective_draft_range(
            request, draft, range_start, range_end
        )

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

                # Track removed dates so Roll Again remembers them (scoped to date range)
                session_key = _removed_dates_session_key(active_start, active_end)
                previously_removed = set(request.session.get(session_key, []))
                previously_removed.update(d.isoformat() for d in dates_to_remove_set)
                request.session[session_key] = sorted(previously_removed)

                messages.success(
                    request,
                    f"Removed {len(dates_to_remove_set)} date(s) from the proposed roster. "
                    + (
                        "These dates will stay removed on Generate For Range."
                        if use_ortools_scheduler
                        else "These dates will stay removed on Roll Again."
                    ),
                )

        elif action == "roll":
            # Retrieve dates previously removed by the user so we skip them (scoped to date range)
            exclude_dates = _get_removed_dates_from_session(
                request, range_start, range_end, clean_invalid=True
            )

            raw = generate_roster(
                year,
                month,
                roles=enabled_roles,
                exclude_dates=exclude_dates,
                start_date=range_start,
                end_date=range_end,
            )
            if not raw:
                exclude_set = set(exclude_dates)
                weekend = [
                    d
                    for d in get_weekend_dates_in_range(range_start, range_end)
                    if is_within_operational_season(d) and d not in exclude_set
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
            _set_proposed_roster_range(request, range_start, range_end)

        elif action == "publish":
            from .utils.email import send_roster_published_notifications

            default_field = Airfield.objects.get(pk=settings.DEFAULT_AIRFIELD_ID)
            created_assignments = []
            draft_entries = request.session.get("proposed_roster", [])
            member_ids = set()
            for entry in draft_entries:
                for mem in entry.get("slots", {}).values():
                    if mem:
                        try:
                            member_ids.add(int(mem))
                        except (TypeError, ValueError):
                            continue

            members_by_id = Member.objects.in_bulk(member_ids)
            role_definitions_by_key = {}
            if siteconfig and siteconfig.enable_dynamic_duty_roles:
                role_definitions_by_key = {
                    role_def.key: role_def
                    for role_def in DutyRoleDefinition.objects.filter(
                        site_configuration=siteconfig,
                        is_active=True,
                    )
                }

            try:
                with transaction.atomic():
                    # Clear all assignments for the effective publish range so removed
                    # draft dates do not leave stale assignments behind.
                    DutyAssignment.objects.filter(
                        date__gte=active_start,
                        date__lte=active_end,
                    ).delete()

                    unsupported_assigned_roles = set()
                    for e in draft_entries:
                        try:
                            edt = dt_date.fromisoformat(e["date"])
                        except (KeyError, TypeError, ValueError):
                            logger.warning(
                                "Skipping draft entry with invalid publish date: %r", e
                            )
                            continue
                        assignment_data = {
                            "date": edt,
                            "location": default_field,
                        }
                        normalized_role_rows = []
                        for role, mem in e["slots"].items():
                            if not mem:
                                continue

                            role_def = role_definitions_by_key.get(role)
                            legacy_role_key = (
                                role_def.legacy_role_key
                                if role_def and role_def.legacy_role_key
                                else role
                            )
                            field_name = DutyAssignment.LEGACY_ROLE_TO_FIELD.get(
                                legacy_role_key
                            )

                            if not field_name:
                                unsupported_assigned_roles.add(get_role_title(role))

                            try:
                                member = members_by_id.get(int(mem))
                            except (TypeError, ValueError):
                                member = None

                            if not member:
                                logger.warning(
                                    "Skipping missing/invalid member id %s for role %s on %s",
                                    mem,
                                    role,
                                    edt.isoformat(),
                                )
                                continue

                            if field_name:
                                try:
                                    assignment_data[field_name] = member
                                except Exception:
                                    logger.exception(
                                        "Failed assigning legacy field %s for %s",
                                        field_name,
                                        edt.isoformat(),
                                    )

                            # Keep dynamic role rows separate from legacy rows.
                            # Legacy rows are synced from assignment fields post-save.
                            if role not in DutyAssignment.LEGACY_ROLE_TO_FIELD:
                                normalized_role_rows.append(
                                    DutyAssignmentRole(
                                        assignment=None,
                                        role_key=role,
                                        member=member,
                                        role_definition=role_def,
                                        legacy_role_key=(
                                            legacy_role_key if field_name else ""
                                        ),
                                        shift_code=(
                                            role_def.shift_code if role_def else ""
                                        ),
                                    )
                                )

                        assignment = DutyAssignment.objects.create(**assignment_data)
                        created_assignments.append(assignment)
                        if normalized_role_rows:
                            for row in normalized_role_rows:
                                row.assignment = assignment
                            DutyAssignmentRole.objects.bulk_create(normalized_role_rows)

                if unsupported_assigned_roles:
                    unsupported_list = ", ".join(sorted(unsupported_assigned_roles))
                    messages.warning(
                        request,
                        "Some configured dynamic roles do not map to legacy assignment "
                        "columns. They were stored in normalized assignment rows only: "
                        f"{unsupported_list}.",
                    )
            except Exception:
                logger.exception("Failed publishing proposed roster")
                messages.error(
                    request,
                    "Could not publish roster due to an internal error. "
                    "Please try again later or contact an administrator.",
                )
                return redirect("duty_roster:propose_roster")

            request.session.pop("proposed_roster", None)
            request.session.pop("proposed_roster_range", None)
            # Clear removed dates for the current range
            session_key = _removed_dates_session_key(active_start, active_end)
            request.session.pop(session_key, None)

            # Send ICS calendar invites to all assigned members
            if created_assignments:
                try:
                    created_by_month = defaultdict(list)
                    for assignment in created_assignments:
                        key = (assignment.date.year, assignment.date.month)
                        created_by_month[key].append(assignment)

                    sent_count = 0
                    all_errors = []
                    for (group_year, group_month), month_assignments in sorted(
                        created_by_month.items()
                    ):
                        result = send_roster_published_notifications(
                            group_year,
                            group_month,
                            month_assignments,
                        )
                        sent_count += result["sent_count"]
                        all_errors.extend(result["errors"])

                    if sent_count > 0:
                        messages.success(
                            request,
                            "Duty roster published for "
                            f"{active_start.isoformat()} to {active_end.isoformat()}. "
                            f"Calendar invites sent to {sent_count} member(s).",
                        )
                    else:
                        messages.success(
                            request,
                            "Duty roster published for "
                            f"{active_start.isoformat()} to {active_end.isoformat()}.",
                        )
                    if all_errors:
                        for error in all_errors:
                            messages.warning(request, error)
                except Exception as e:
                    messages.success(
                        request,
                        "Duty roster published for "
                        f"{active_start.isoformat()} to {active_end.isoformat()}.",
                    )
                    messages.warning(
                        request,
                        f"Could not send calendar invites: {str(e)}",
                    )
            else:
                messages.success(
                    request,
                    "Duty roster published for "
                    f"{active_start.isoformat()} to {active_end.isoformat()}.",
                )
                messages.info(
                    request,
                    "No duty assignments to notify, so no calendar invites were sent.",
                )

            return redirect(
                "duty_roster:duty_calendar_month",
                year=active_start.year,
                month=active_start.month,
            )

        elif action == "restore_dates":
            # Clear removed dates so Roll Again includes all dates again (scoped to range)
            session_key = _removed_dates_session_key(active_start, active_end)
            request.session.pop(session_key, None)
            messages.info(
                request,
                "All previously removed dates have been restored. "
                + (
                    "Click Generate For Range to regenerate the full roster."
                    if use_ortools_scheduler
                    else "Click Roll Again to regenerate the full roster."
                ),
            )

        elif action == "cancel":
            request.session.pop("proposed_roster", None)
            request.session.pop("proposed_roster_range", None)
            # Clear removed dates for the current range
            session_key = _removed_dates_session_key(active_start, active_end)
            request.session.pop(session_key, None)
            return redirect("duty_roster:duty_calendar")
    else:
        # Retrieve any previously removed dates for this range
        exclude_dates = _get_removed_dates_from_session(request, range_start, range_end)

        raw = generate_roster(
            year,
            month,
            roles=enabled_roles,
            exclude_dates=exclude_dates,
            start_date=range_start,
            end_date=range_end,
        )
        if not raw:
            exclude_set = set(exclude_dates)
            weekend = [
                d
                for d in get_weekend_dates_in_range(range_start, range_end)
                if is_within_operational_season(d) and d not in exclude_set
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
        _set_proposed_roster_range(request, range_start, range_end)
    display = [
        {
            "date": dt_date.fromisoformat(e["date"]),
            "slots": e["slots"],
            "diagnostics": e.get("diagnostics", {}),
        }
        for e in request.session.get("proposed_roster", [])
    ]
    display_start, display_end = _effective_draft_range(
        request, request.session.get("proposed_roster", []), range_start, range_end
    )
    display_month_span = count_calendar_months_inclusive(display_start, display_end)
    # Build list of removed dates for display in the template (scoped to range)
    removed_dates = _get_removed_dates_from_session(request, display_start, display_end)

    return render(
        request,
        "duty_roster/propose_roster.html",
        {
            "draft": display,
            "year": year,
            "month": month,
            "start_date": display_start,
            "end_date": display_end,
            "month_span": display_month_span,
            "incomplete": incomplete,
            "enabled_roles": enabled_roles,
            "role_labels": role_labels,
            "no_scheduling": False,
            "operational_info": operational_info,
            "filtered_dates": filtered_dates,
            "siteconfig": siteconfig,
            "use_ortools_scheduler": use_ortools_scheduler,
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

    site_config = SiteConfiguration.objects.first()
    role_service = RoleResolutionService(site_configuration=site_config)
    enabled_role_keys = role_service.get_enabled_roles()
    role_definitions_by_key = {}
    if site_config and site_config.enable_dynamic_duty_roles and enabled_role_keys:
        role_definitions_by_key = {
            role_def.key: role_def
            for role_def in DutyRoleDefinition.objects.filter(
                site_configuration=site_config,
                is_active=True,
                key__in=enabled_role_keys,
            )
        }
    if site_config and site_config.enable_dynamic_duty_roles:
        active_flyer_ids = list(active_flyers.values_list("id", flat=True))
        active_flyers_for_resolution = Member.objects.filter(
            id__in=active_flyer_ids,
            is_active=True,
        )
        eligible_member_ids_by_role = {
            role_key: role_service.get_eligible_member_ids(
                role_key,
                members_queryset=active_flyers_for_resolution,
            )
            for role_key in enabled_role_keys
        }
    else:
        active_flyers_list = list(active_flyers)
        eligible_member_ids_by_role = {}
        for role_key in enabled_role_keys:
            if role_key == "commercial_pilot":
                eligible_member_ids_by_role[role_key] = {
                    member.id
                    for member in active_flyers_list
                    if _is_commercial_pilot_qualified(member)
                }
            else:
                eligible_member_ids_by_role[role_key] = {
                    member.id
                    for member in active_flyers_list
                    if bool(getattr(member, role_key, False))
                }
        active_flyers = active_flyers_list

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

            # Derive eligible roles from configured enabled roles.
            roles = []
            for role_key in enabled_role_keys:
                if member.id not in eligible_member_ids_by_role.get(role_key, set()):
                    continue

                dynamic_definition = role_definitions_by_key.get(role_key)
                role_label = (
                    dynamic_definition.display_name
                    if dynamic_definition and dynamic_definition.display_name
                    else role_service.get_role_label(role_key)
                )
                if role_label and role_label not in roles:
                    roles.append(role_label)

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
    Show instructors upcoming instruction requests across all duty days.

    Only visible to members who are instructors.
    """
    from .models import InstructionSlot

    if not request.user.instructor:
        messages.error(request, "Only instructors can access this page.")
        return redirect("duty_roster:duty_calendar")

    today = date.today()

    day_filter_options = [
        ("7", "Next 7 days"),
        ("14", "Next 14 days"),
        ("30", "Next 30 days"),
        ("all", "All upcoming"),
    ]
    selected_days = request.GET.get("days", "14")
    valid_day_values = {value for value, _ in day_filter_options}
    if selected_days not in valid_day_values:
        selected_days = "14"

    slot_filter = {"assignment__date__gte": today}
    assignment_filter = {"date__gte": today}
    if selected_days != "all":
        day_window = int(selected_days)
        end_date = today + timedelta(days=day_window - 1)
        slot_filter["assignment__date__lte"] = end_date
        assignment_filter["date__lte"] = end_date

    # Show all upcoming requests to any instructor (Issue #771).
    pending_slots = (
        InstructionSlot.objects.filter(
            instructor_response="pending",
            **slot_filter,
        )
        .exclude(status="cancelled")
        .select_related(
            "assignment",
            "assignment__instructor",
            "assignment__surge_instructor",
            "student",
        )
        .order_by("assignment__date", "created_at")
    )

    accepted_slots = (
        InstructionSlot.objects.filter(
            instructor_response="accepted",
            **slot_filter,
        )
        .exclude(status="cancelled")
        .select_related(
            "assignment",
            "assignment__instructor",
            "assignment__surge_instructor",
            "student",
        )
        .order_by("assignment__date", "created_at")
    )

    # Keep assignment-scoped data for the viewer's own duty days where
    # allocation controls are relevant.
    assigned_assignments = DutyAssignment.objects.filter(**assignment_filter).filter(
        models.Q(instructor=request.user) | models.Q(surge_instructor=request.user)
    )
    assigned_dates = set(assigned_assignments.values_list("date", flat=True))

    # Group by assignment date for easier display

    pending_by_date = defaultdict(list)
    for slot in pending_slots:
        slot.is_assigned_to_request_user = request.user.id in (
            slot.assignment.instructor_id,
            slot.assignment.surge_instructor_id,
        )
        pending_by_date[slot.assignment.date].append(slot)

    accepted_by_date = defaultdict(list)
    for slot in accepted_slots:
        slot.is_assigned_to_request_user = request.user.id in (
            slot.assignment.instructor_id,
            slot.assignment.surge_instructor_id,
        )
        accepted_by_date[slot.assignment.date].append(slot)

    _, instruction_surge_threshold = get_surge_thresholds()
    instruction_max_students_per_instructor = (
        get_instruction_max_students_per_instructor()
    )

    # Build a per-date allocation map for days that have both a primary and surge
    # instructor, so the template can show the three-column split view (Issue #664).
    assignment_by_date = {
        a.date: a
        for a in assigned_assignments.select_related("instructor", "surge_instructor")
    }

    # Build the allocation map for surge days (primary/surge/unassigned split).
    # NOTE: allocation_by_date is built only for surge days that have accepted
    # student slots (i.e., dates present in accepted_by_date) and where both a
    # primary and surge instructor are assigned. The Student Allocation section
    # (showing primary/surge/unassigned columns) is therefore shown only on those
    # days. The green "Accepted Students" card always uses the full accepted_by_date
    # dict (see context below), so it is never empty due to surge status (Issue #695).
    allocation_by_date = {}
    for day, slots in accepted_by_date.items():
        assignment = assignment_by_date.get(day)
        if assignment and assignment.instructor_id and assignment.surge_instructor_id:
            primary_slots = [
                s for s in slots if s.instructor_id == assignment.instructor_id
            ]
            surge_slots = [
                s for s in slots if s.instructor_id == assignment.surge_instructor_id
            ]
            # Slots with no instructor assigned or assigned to a third party
            # (should not happen in normal flow, but guard defensively).
            other_slots = [
                s
                for s in slots
                if (
                    s.instructor_id is None
                    or s.instructor_id
                    not in (assignment.instructor_id, assignment.surge_instructor_id)
                )
            ]
            allocation_by_date[day] = {
                "assignment": assignment,
                "primary": assignment.instructor,
                "surge": assignment.surge_instructor,
                "primary_slots": primary_slots,
                "surge_slots": surge_slots,
                "unassigned_slots": other_slots,
            }

    return render(
        request,
        "duty_roster/instructor_requests.html",
        {
            "pending_by_date": dict(pending_by_date),
            # Pass ALL accepted slots so the green card is populated even on
            # surge days (Issue #695 fix – previously only non-surge days were
            # included, leaving the card empty whenever a surge instructor was
            # assigned).
            "accepted_by_date": dict(accepted_by_date),
            "allocation_by_date": allocation_by_date,
            "pending_count": len(pending_slots),
            "accepted_count": sum(len(v) for v in accepted_by_date.values()),
            "today": today,
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
            "day_filter_options": day_filter_options,
            "selected_days": selected_days,
            "assigned_dates": assigned_dates,
        },
    )


def _redirect_instructor_requests_with_days(request):
    """Redirect to instructor requests while preserving an allowed days filter."""
    days = (request.POST.get("days") or request.GET.get("days") or "").strip().lower()
    base_url = reverse("duty_roster:instructor_requests")

    # Use explicit constants rather than interpolating user input into a URL.
    if days == "7":
        return redirect(f"{base_url}?days=7")
    if days == "14":
        return redirect(f"{base_url}?days=14")
    if days == "30":
        return redirect(f"{base_url}?days=30")
    if days == "all":
        return redirect(f"{base_url}?days=all")

    return redirect("duty_roster:instructor_requests")


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
        return _redirect_instructor_requests_with_days(request)

    action = request.POST.get("action")
    if action not in ["accept", "reject"]:
        messages.error(request, "Invalid action.")
        return _redirect_instructor_requests_with_days(request)

    # Per-instructor capacity check (Issue #665 / #840).
    # Applies whenever an instructor accepts a request. The quota comes from
    # SiteConfiguration.instruction_max_students_per_instructor.
    if action == "accept":
        max_students_per_instructor = get_instruction_max_students_per_instructor()
        my_accepted_count = (
            InstructionSlot.objects.filter(
                assignment=assignment,
                instructor=request.user,
                instructor_response="accepted",
            )
            .exclude(status="cancelled")
            .count()
        )
        if my_accepted_count >= max_students_per_instructor:
            if assignment.instructor and assignment.surge_instructor:
                detail = "The other instructor may still accept this student."
            else:
                detail = (
                    "Assign a surge instructor to increase total capacity for this day."
                )
            messages.error(
                request,
                f"You have reached your student capacity ({max_students_per_instructor}) for this day. "
                f"{detail}",
            )
            return _redirect_instructor_requests_with_days(request)

    form = InstructorResponseForm(request.POST, instance=slot, instructor=request.user)

    if form.is_valid():
        if action == "accept":
            form.accept()
            messages.success(
                request,
                f"Accepted {slot.student.full_display_name} for {slot.assignment.date.strftime('%B %d')}.",
            )
            # HTML email sent via signal (send_request_response_email)

            # Only check for surge need if no surge instructor yet
            _check_surge_instructor_needed(slot.assignment)

        elif action == "reject":
            form.reject()
            messages.info(
                request,
                f"Declined {slot.student.full_display_name} for {slot.assignment.date.strftime('%B %d')}.",
            )
            # HTML email sent via signal (send_request_response_email)

    return _redirect_instructor_requests_with_days(request)


@active_member_required
@require_POST
def revert_instruction_response(request, slot_id):
    """Move an accepted student request back to pending for instructor review."""
    from .models import InstructionSlot

    if not request.user.instructor:
        return HttpResponseForbidden("Only instructors can modify requests.")

    slot = get_object_or_404(InstructionSlot, id=slot_id)
    assignment = slot.assignment

    if assignment.date < date.today():
        messages.warning(
            request,
            "Past duty dates cannot be modified.",
        )
        return _redirect_instructor_requests_with_days(request)

    if request.user not in [assignment.instructor, assignment.surge_instructor]:
        return HttpResponseForbidden("You are not the instructor for this day.")

    if slot.status == "cancelled":
        messages.warning(request, "This request is already cancelled.")
        return _redirect_instructor_requests_with_days(request)

    if slot.instructor_response != "accepted":
        messages.warning(
            request,
            "Only accepted requests can be moved back to pending.",
        )
        return _redirect_instructor_requests_with_days(request)

    # Clear the instructor when reverting to pending - the "pending" state means
    # no instructor has accepted yet, mirroring the initial slot creation state.
    prior_instructor_note = slot.instructor_note

    slot.instructor = None
    slot.instructor_response = "pending"
    slot.status = "pending"
    slot.instructor_note = ""
    slot.instructor_response_at = None
    slot.save(
        update_fields=[
            "instructor",
            "instructor_response",
            "status",
            "instructor_note",
            "instructor_response_at",
            "updated_at",
        ]
    )

    try:
        from .signals import send_request_reverted_to_pending_notification

        send_request_reverted_to_pending_notification(
            slot,
            acting_instructor=request.user,
            prior_instructor_note=prior_instructor_note,
        )
    except Exception:
        logger.exception(
            "Failed to send pending-review notification for slot_id=%s",
            slot.id,
        )

    messages.success(
        request,
        f"Moved {slot.student.full_display_name} back to pending requests.",
    )
    return _redirect_instructor_requests_with_days(request)


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
        return _redirect_instructor_requests_with_days(request)

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

    return _redirect_instructor_requests_with_days(request)


@active_member_required
@never_cache
def volunteer_as_surge_instructor(request, assignment_id):
    """
    Allow an instructor to volunteer as surge instructor for a day.

    GET  – Shows a confirmation page with the date, primary instructor, and
           student count so the volunteer can confirm before committing.
    POST – Assigns the current user as surge_instructor on the DutyAssignment
           and notifies the primary instructor by email.

    Guards:
    * User must be an instructor (member.instructor == True).
    * Duty day must be today or in the future (consistent with tow-pilot flow).
    * A primary instructor must already be assigned (surge is only needed then).
    * Volunteer cannot be the primary instructor themselves.
    * If a surge instructor is already assigned the request is gracefully
      rejected with an informational message regardless of who this user is.
    """
    from .models import InstructionSlot

    assignment = get_object_or_404(DutyAssignment, id=assignment_id)
    member = request.user

    if not member.instructor:
        messages.error(
            request,
            "Only qualified instructors can volunteer as surge instructor.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: cannot volunteer for past days (mirrors tow-pilot flow).
    if assignment.date < date.today():
        messages.error(
            request,
            "Cannot volunteer for a past duty day.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: no primary instructor means surge is not needed.
    if not assignment.instructor_id:
        messages.error(
            request,
            "There is no primary instructor assigned for this day.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: volunteer cannot be the primary instructor themselves.
    if assignment.instructor_id == member.id:
        messages.info(
            request,
            "You are already the primary instructor for "
            f"{assignment.date.strftime('%B %d, %Y')}.",
        )
        return redirect("duty_roster:duty_calendar")

    # If a surge instructor is already assigned, tell the volunteer and bail out.
    if assignment.surge_instructor_id:
        if assignment.surge_instructor == member:
            messages.info(
                request,
                "You are already the surge instructor for "
                f"{assignment.date.strftime('%B %d, %Y')}.",
            )
        else:
            messages.info(
                request,
                "A surge instructor has already been assigned for "
                f"{assignment.date.strftime('%B %d, %Y')}. Thank you for your willingness!",
            )
        return redirect("duty_roster:duty_calendar")

    # Count accepted students for display on the confirmation page.
    accepted_count = (
        InstructionSlot.objects.filter(
            assignment=assignment,
            instructor_response="accepted",
        )
        .exclude(status="cancelled")
        .count()
    )

    if request.method == "POST":
        # Use select_for_update inside a transaction to guarantee only the
        # first volunteer wins (prevents last-write-wins race condition,
        # mirroring the tow-pilot surge flow).
        with transaction.atomic():
            locked = DutyAssignment.objects.select_for_update().get(id=assignment_id)
            if locked.surge_instructor_id:
                messages.info(
                    request,
                    "Someone just volunteered ahead of you for "
                    f"{assignment.date.strftime('%B %d, %Y')}. "
                    "Thank you for offering!",
                )
                return redirect("duty_roster:duty_calendar")

            locked.surge_instructor = member
            locked.save(update_fields=["surge_instructor"])

        notified = _notify_primary_instructor_surge_filled(locked)
        _notify_instructors_surge_filled(locked)
        base_msg = (
            f"You have been assigned as surge instructor for "
            f"{assignment.date.strftime('%B %d, %Y')}."
        )
        messages.success(
            request,
            (
                base_msg + " The primary instructor has been notified."
                if notified
                else base_msg
                + " The primary instructor could not be notified automatically."
            ),
        )
        return redirect("duty_roster:duty_calendar")

    # GET – render confirmation page
    return render(
        request,
        "duty_roster/surge_volunteer_confirm.html",
        {
            "assignment": assignment,
            "accepted_count": accepted_count,
        },
    )


@active_member_required
@never_cache
def volunteer_as_surge_tow_pilot(request, assignment_id):
    """
    Allow a tow pilot to volunteer as surge tow pilot for a day (Issue #688).

    GET  – Shows a confirmation page with the date and primary tow pilot.
    POST – Assigns the current user as surge_tow_pilot on the DutyAssignment.

    Guards:
    * User must be a tow pilot (member.towpilot == True).
    * If a surge tow pilot is already assigned the request is gracefully
      rejected with an informational message.
    """
    assignment = get_object_or_404(DutyAssignment, id=assignment_id)
    member = request.user

    if not getattr(member, "towpilot", False):
        messages.error(
            request,
            "Only qualified tow pilots can volunteer as surge tow pilot.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: cannot volunteer for past days
    if assignment.date < date.today():
        messages.error(
            request,
            "Cannot volunteer for a past duty day.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: no primary tow pilot means surge is not needed
    if not assignment.tow_pilot_id:
        messages.error(
            request,
            "There is no primary tow pilot assigned for this day.",
        )
        return redirect("duty_roster:duty_calendar")

    # Guard: volunteer cannot be the primary tow pilot
    if assignment.tow_pilot_id == member.id:
        messages.info(
            request,
            "You are already the primary tow pilot for "
            f"{assignment.date.strftime('%B %d, %Y')}.",
        )
        return redirect("duty_roster:duty_calendar")

    if assignment.surge_tow_pilot_id:
        if assignment.surge_tow_pilot == member:
            messages.info(
                request,
                "You are already the surge tow pilot for "
                f"{assignment.date.strftime('%B %d, %Y')}.",
            )
        else:
            messages.info(
                request,
                "A surge tow pilot has already been assigned for "
                f"{assignment.date.strftime('%B %d, %Y')}. Thank you for your willingness!",
            )
        return redirect("duty_roster:duty_calendar")

    if request.method == "POST":
        # Use select_for_update inside a transaction to guarantee only the
        # first concurrent volunteer wins (prevents last-write-wins race).
        with transaction.atomic():
            locked = DutyAssignment.objects.select_for_update().get(id=assignment_id)
            if locked.surge_tow_pilot_id:
                messages.info(
                    request,
                    "Someone just volunteered ahead of you for "
                    f"{assignment.date.strftime('%B %d, %Y')}. "
                    "Thank you for offering!",
                )
                return redirect("duty_roster:duty_calendar")

            locked.surge_tow_pilot = member
            locked.save(update_fields=["surge_tow_pilot"])

        notified = _notify_primary_tow_pilot_surge_filled(locked)
        _notify_tow_pilots_surge_filled(locked)
        base_msg = (
            f"You have been assigned as surge tow pilot for "
            f"{assignment.date.strftime('%B %d, %Y')}."
        )
        messages.success(
            request,
            (
                base_msg + " The primary tow pilot has been notified."
                if notified
                else base_msg
                + " The primary tow pilot could not be notified automatically."
            ),
        )
        return redirect("duty_roster:duty_calendar")

    # GET – render confirmation page
    return render(
        request,
        "duty_roster/surge_tow_volunteer_confirm.html",
        {"assignment": assignment},
    )


@active_member_required
@never_cache
def retract_surge_instructor(request, assignment_id):
    """Allow the assigned surge instructor to retract their own offer (Issue #801)."""
    assignment = get_object_or_404(DutyAssignment, id=assignment_id)
    member = request.user

    if not member.instructor:
        messages.error(
            request,
            "Only qualified instructors can retract a surge instructor offer.",
        )
        return redirect("duty_roster:duty_calendar")

    if assignment.date < date.today():
        messages.error(
            request,
            "Cannot retract a surge instructor offer for a past duty day.",
        )
        return redirect("duty_roster:duty_calendar")

    if not assignment.surge_instructor_id:
        messages.info(
            request,
            "There is no surge instructor assignment to retract for this day.",
        )
        return redirect("duty_roster:duty_calendar")

    if assignment.surge_instructor_id != member.id:
        return HttpResponseForbidden(
            "Only the assigned surge instructor can retract this offer."
        )

    if request.method == "POST":
        with transaction.atomic():
            locked = DutyAssignment.objects.select_for_update().get(id=assignment_id)

            if not locked.surge_instructor_id:
                messages.info(
                    request,
                    "This surge instructor offer was already retracted.",
                )
                return redirect("duty_roster:duty_calendar")

            if locked.surge_instructor_id != member.id:
                return HttpResponseForbidden(
                    "Only the assigned surge instructor can retract this offer."
                )

            withdrawn_instructor = locked.surge_instructor
            locked.surge_instructor = None
            locked.save(update_fields=["surge_instructor"])

        notified = _notify_primary_instructor_surge_withdrawn(
            locked, withdrawn_instructor
        )
        base_msg = (
            f"You have retracted your surge instructor offer for "
            f"{assignment.date.strftime('%B %d, %Y')}."
        )
        messages.success(
            request,
            (
                base_msg + " The primary instructor has been notified."
                if notified
                else base_msg
                + " The primary instructor could not be notified automatically."
            ),
        )
        return redirect("duty_roster:duty_calendar")

    return render(
        request,
        "duty_roster/surge_retract_confirm.html",
        {"assignment": assignment},
    )


@active_member_required
@never_cache
def retract_surge_tow_pilot(request, assignment_id):
    """Allow the assigned surge tow pilot to retract their own offer (Issue #801)."""
    assignment = get_object_or_404(DutyAssignment, id=assignment_id)
    member = request.user

    if not getattr(member, "towpilot", False):
        messages.error(
            request,
            "Only qualified tow pilots can retract a surge tow pilot offer.",
        )
        return redirect("duty_roster:duty_calendar")

    if assignment.date < date.today():
        messages.error(
            request,
            "Cannot retract a surge tow pilot offer for a past duty day.",
        )
        return redirect("duty_roster:duty_calendar")

    if not assignment.surge_tow_pilot_id:
        messages.info(
            request,
            "There is no surge tow pilot assignment to retract for this day.",
        )
        return redirect("duty_roster:duty_calendar")

    if assignment.surge_tow_pilot_id != member.id:
        return HttpResponseForbidden(
            "Only the assigned surge tow pilot can retract this offer."
        )

    if request.method == "POST":
        with transaction.atomic():
            locked = DutyAssignment.objects.select_for_update().get(id=assignment_id)

            if not locked.surge_tow_pilot_id:
                messages.info(
                    request,
                    "This surge tow pilot offer was already retracted.",
                )
                return redirect("duty_roster:duty_calendar")

            if locked.surge_tow_pilot_id != member.id:
                return HttpResponseForbidden(
                    "Only the assigned surge tow pilot can retract this offer."
                )

            withdrawn_tow_pilot = locked.surge_tow_pilot
            locked.surge_tow_pilot = None
            locked.save(update_fields=["surge_tow_pilot"])

        notified = _notify_primary_tow_pilot_surge_withdrawn(
            locked, withdrawn_tow_pilot
        )
        base_msg = (
            f"You have retracted your surge tow pilot offer for "
            f"{assignment.date.strftime('%B %d, %Y')}."
        )
        messages.success(
            request,
            (
                base_msg + " The primary tow pilot has been notified."
                if notified
                else base_msg
                + " The primary tow pilot could not be notified automatically."
            ),
        )
        return redirect("duty_roster:duty_calendar")

    return render(
        request,
        "duty_roster/surge_tow_retract_confirm.html",
        {"assignment": assignment},
    )


@active_member_required
@require_POST
def assign_student_to_instructor(request, slot_id):
    """
    Allow the primary or surge instructor to move an accepted student between
    their queues (Issue #664).

    POST parameters:
        action – "primary" | "surge"

    Rules:
    * The requesting user must be either the primary or surge instructor for
      the slot's assignment.
    * action="surge" requires that a surge instructor is actually assigned.
    * Only already-accepted (instructor_response="accepted") slots may be moved.
    """
    from .models import InstructionSlot

    slot = get_object_or_404(InstructionSlot, id=slot_id)
    assignment = slot.assignment

    # Auth: must be primary or surge instructor for this day
    if request.user not in (assignment.instructor, assignment.surge_instructor):
        return HttpResponseForbidden("You are not an instructor for this day.")

    if slot.status == "cancelled":
        messages.warning(request, "Cannot reassign a cancelled instruction request.")
        return redirect("duty_roster:instructor_requests")

    if slot.instructor_response != "accepted":
        messages.warning(request, "Only accepted students can be reassigned.")
        return redirect("duty_roster:instructor_requests")

    action = request.POST.get("action")
    if action not in ("primary", "surge"):
        messages.error(request, "Invalid assignment action.")
        return redirect("duty_roster:instructor_requests")

    if action == "surge" and not assignment.surge_instructor:
        messages.error(
            request,
            "No surge instructor is assigned for this day; cannot reassign.",
        )
        return redirect("duty_roster:instructor_requests")

    target_instructor = (
        assignment.instructor if action == "primary" else assignment.surge_instructor
    )

    if target_instructor is None:
        messages.error(
            request,
            "No instructor is assigned for this role; cannot reassign.",
        )
        return redirect("duty_roster:instructor_requests")

    # Guard (Issue #685): an instructor cannot be assigned as their own student.
    if slot.student == target_instructor:
        messages.error(
            request,
            f"{target_instructor.full_display_name} is the instructor for this day "
            "and cannot be assigned as their own student.",
        )
        return redirect("duty_roster:instructor_requests")

    # No-op if already assigned to the target
    if slot.instructor == target_instructor:
        messages.info(
            request,
            f"{slot.student.full_display_name} is already assigned to "
            f"{target_instructor.full_display_name}. No change made.",
        )
        return redirect("duty_roster:instructor_requests")

    slot.instructor = target_instructor
    slot.save(update_fields=["instructor"])

    messages.success(
        request,
        f"Moved {slot.student.full_display_name} to "
        f"{target_instructor.full_display_name}.",
    )

    _notify_student_instructor_assigned(slot)
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
        email_config = get_email_config()
        config = email_config["config"]
        ops_date = slot.assignment.date.strftime("%A, %B %d, %Y")

        subject = (
            f"Instruction Cancellation for {slot.assignment.date.strftime('%B %d, %Y')}"
        )
        context = {
            "student_name": slot.student.full_display_name,
            "instructor_name": instructor.full_display_name,
            "ops_date": ops_date,
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "roster_url": email_config["roster_url"],
        }

        html_message = render_to_string(
            "duty_roster/emails/instruction_cancellation.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/instruction_cancellation.txt", context
        )

        send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [instructor.email],
            html_message=html_message,
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

    Sends an HTML + plain-text multipart email using the
    ``surge_instructor_alert.html`` / ``surge_instructor_alert.txt`` templates.

    Returns True if the email was sent successfully, False otherwise.
    The caller should only set surge_notified=True when this returns True,
    so a misconfigured email address doesn't permanently suppress future attempts.
    """
    try:
        email_config = get_email_config()
        config = email_config["config"]
        instructor_email = config.instructors_email if config else ""

        if not instructor_email:
            logger.warning(
                "No instructors_email configured in SiteConfiguration; "
                "surge instructor alert for %s suppressed",
                assignment.date,
            )
            return False

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Surge Instructor Needed - {assignment.date.strftime('%B %d, %Y')}"
        _, instruction_surge_threshold = get_surge_thresholds()
        instruction_max_students_per_instructor = (
            get_instruction_max_students_per_instructor()
        )

        volunteer_url = build_absolute_url(
            reverse("duty_roster:volunteer_surge_instructor", args=[assignment.id]),
            canonical=email_config["site_url"],
        )

        context = {
            "ops_date": ops_date,
            "student_count": student_count,
            "roster_url": email_config["roster_url"],
            "volunteer_url": volunteer_url,
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_instructor_alert.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_instructor_alert.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [instructor_email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception("Failed to send surge instructor notification")
        return False


def _notify_primary_instructor_surge_filled(assignment):
    """Notify the primary instructor that a surge instructor has volunteered.

    Sends an HTML + plain-text email to the primary instructor so they know
    who will be joining them on the day.

    Returns True if the email was sent, False otherwise (errors are logged).
    """
    try:
        primary = assignment.instructor
        if not primary or not primary.email:
            logger.warning(
                "Primary instructor for assignment %s has no email; "
                "surge-filled notification suppressed",
                assignment.id,
            )
            return False

        surge = assignment.surge_instructor
        if not surge:
            return False

        email_config = get_email_config()
        config = email_config["config"]
        _, instruction_surge_threshold = get_surge_thresholds()
        instruction_max_students_per_instructor = (
            get_instruction_max_students_per_instructor()
        )

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = (
            f"Surge Instructor Confirmed - {assignment.date.strftime('%B %d, %Y')}"
        )

        context = {
            "ops_date": ops_date,
            "primary_instructor": primary,
            "surge_instructor": surge,
            "roster_url": email_config["roster_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_instructor_filled.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_instructor_filled.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [primary.email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-filled notification to primary instructor"
        )
        return False


def _notify_instructors_surge_filled(assignment):
    """Notify the instructors mailing list when a surge instructor slot is filled."""
    try:
        surge = assignment.surge_instructor
        if not surge:
            return False

        email_config = get_email_config()
        config = email_config["config"]
        _, instruction_surge_threshold = get_surge_thresholds()
        instruction_max_students_per_instructor = (
            get_instruction_max_students_per_instructor()
        )
        recipient_list = get_mailing_list(
            "INSTRUCTORS_MAILING_LIST", "instructors", config
        )

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Surge Instructor Filled - {assignment.date.strftime('%B %d, %Y')}"

        context = {
            "ops_date": ops_date,
            "primary_instructor": assignment.instructor,
            "surge_instructor": surge,
            "roster_url": email_config["roster_url"],
            "site_url": email_config["site_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_instructor_filled_broadcast.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_instructor_filled_broadcast.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-filled broadcast notification to instructors"
        )
        return False


def _notify_primary_tow_pilot_surge_filled(assignment):
    """Notify the primary tow pilot that a surge tow pilot has volunteered.

    Mirrors _notify_primary_instructor_surge_filled for the tow pilot role.
    Returns True if the email was sent, False otherwise (errors are logged).
    """
    try:
        primary = assignment.tow_pilot
        if not primary or not primary.email:
            logger.warning(
                "Primary tow pilot for assignment %s has no email; "
                "surge-filled notification suppressed",
                assignment.id,
            )
            return False

        surge = assignment.surge_tow_pilot
        if not surge:
            return False

        email_config = get_email_config()
        config = email_config["config"]

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Surge Tow Pilot Confirmed - {assignment.date.strftime('%B %d, %Y')}"

        context = {
            "ops_date": ops_date,
            "primary_tow_pilot": primary,
            "surge_tow_pilot": surge,
            "roster_url": email_config["roster_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_filled.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_filled.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [primary.email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-filled notification to primary tow pilot"
        )
        return False


def _notify_tow_pilots_surge_filled(assignment):
    """Notify the tow-pilots mailing list when a surge tow pilot slot is filled."""
    try:
        surge = assignment.surge_tow_pilot
        if not surge:
            return False

        email_config = get_email_config()
        config = email_config["config"]
        recipient_list = get_mailing_list("TOWPILOTS_MAILING_LIST", "towpilots", config)

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Surge Tow Pilot Filled - {assignment.date.strftime('%B %d, %Y')}"

        context = {
            "ops_date": ops_date,
            "primary_tow_pilot": assignment.tow_pilot,
            "surge_tow_pilot": surge,
            "roster_url": email_config["roster_url"],
            "site_url": email_config["site_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_filled_broadcast.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_filled_broadcast.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-filled broadcast notification to tow pilots"
        )
        return False


def _notify_primary_instructor_surge_withdrawn(assignment, withdrawn_instructor):
    """Notify the primary instructor that the surge instructor has withdrawn."""
    try:
        primary = assignment.instructor
        if not primary or not primary.email:
            logger.warning(
                "Primary instructor for assignment %s has no email; "
                "surge-withdrawn notification suppressed",
                assignment.id,
            )
            return False

        if not withdrawn_instructor:
            return False

        email_config = get_email_config()
        config = email_config["config"]
        _, instruction_surge_threshold = get_surge_thresholds()
        instruction_max_students_per_instructor = (
            get_instruction_max_students_per_instructor()
        )

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = (
            f"Surge Instructor Withdrawn - {assignment.date.strftime('%B %d, %Y')}"
        )

        context = {
            "ops_date": ops_date,
            "primary_instructor": primary,
            "withdrawn_instructor": withdrawn_instructor,
            "roster_url": email_config["roster_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
            "instruction_surge_threshold": instruction_surge_threshold,
            "instruction_max_students_per_instructor": instruction_max_students_per_instructor,
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_instructor_withdrawn.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_instructor_withdrawn.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [primary.email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-withdrawn notification to primary instructor"
        )
        return False


def _notify_primary_tow_pilot_surge_withdrawn(assignment, withdrawn_tow_pilot):
    """Notify the primary tow pilot that the surge tow pilot has withdrawn."""
    try:
        primary = assignment.tow_pilot
        if not primary or not primary.email:
            logger.warning(
                "Primary tow pilot for assignment %s has no email; "
                "surge-withdrawn notification suppressed",
                assignment.id,
            )
            return False

        if not withdrawn_tow_pilot:
            return False

        email_config = get_email_config()
        config = email_config["config"]

        ops_date = assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Surge Tow Pilot Withdrawn - {assignment.date.strftime('%B %d, %Y')}"

        context = {
            "ops_date": ops_date,
            "primary_tow_pilot": primary,
            "withdrawn_tow_pilot": withdrawn_tow_pilot,
            "roster_url": email_config["roster_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
        }

        html_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_withdrawn.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/surge_tow_pilot_withdrawn.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [primary.email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception(
            "Failed to send surge-withdrawn notification to primary tow pilot"
        )
        return False


def _notify_student_instructor_assigned(slot):
    """Notify a student that their assigned instructor for the day has been updated.

    Sent whenever `slot.instructor` is changed by the student-allocation flow
    (Issue #664).  Returns True on success, False on error.
    """
    try:
        student = slot.student
        if not student or not student.email:
            logger.warning(
                "Student %s has no email; instructor-assignment notification suppressed",
                getattr(student, "full_display_name", "unknown"),
            )
            return False

        assigned = slot.instructor
        if not assigned:
            return False

        email_config = get_email_config()
        config = email_config["config"]

        ops_date = slot.assignment.date.strftime("%A, %B %d, %Y")
        subject = f"Your instructor for {slot.assignment.date.strftime('%B %d, %Y')} has been confirmed"

        context = {
            "ops_date": ops_date,
            "student": student,
            "instructor": assigned,
            "roster_url": email_config["roster_url"],
            "club_name": email_config["club_name"],
            "club_logo_url": get_absolute_club_logo_url(config),
        }

        html_message = render_to_string(
            "duty_roster/emails/student_instructor_assigned.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/student_instructor_assigned.txt", context
        )

        sent_count = send_mail(
            subject,
            text_message,
            email_config["from_email"],
            [student.email],
            fail_silently=False,
            html_message=html_message,
        )
        return sent_count > 0
    except Exception:
        logger.exception("Failed to send instructor-assignment notification to student")
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


# ---------------------------------------------------------------------------
# Volunteer to fill a roster hole (Issue #679)
# ---------------------------------------------------------------------------

# Maps URL role slug →
#   (member qual attr, assignment FK attr, config title attr, default title, config schedule attr)
_HOLE_FILL_ROLE_MAP = {
    "instructor": (
        "instructor",
        "instructor",
        "instructor_title",
        "Instructor",
        "schedule_instructors",
    ),
    "tow_pilot": (
        "towpilot",
        "tow_pilot",
        "towpilot_title",
        "Tow Pilot",
        "schedule_tow_pilots",
    ),
    "duty_officer": (
        "duty_officer",
        "duty_officer",
        "duty_officer_title",
        "Duty Officer",
        "schedule_duty_officers",
    ),
    "assistant_duty_officer": (
        "assistant_duty_officer",
        "assistant_duty_officer",
        "assistant_duty_officer_title",
        "Assistant Duty Officer",
        "schedule_assistant_duty_officers",
    ),
    "commercial_pilot": (
        "__commercial_rating__",
        "commercial_pilot",
        "commercial_pilot_title",
        "Commercial Pilot",
        "schedule_commercial_pilots",
    ),
}


@active_member_required
@never_cache
def volunteer_fill_role(request, assignment_id, role):
    """
    Allow a qualified member to volunteer to fill an empty primary roster role
    on a scheduled duty day (Issue #679).

    GET  – Shows a confirmation page so the member can confirm before committing.
    POST – Assigns the current user to the role if it is still empty, then
           redirects to the duty calendar with a success message.

    Accepts ``role`` as one of: instructor, tow_pilot, duty_officer,
    assistant_duty_officer, commercial_pilot.

    Guards:
    * The ``role`` parameter must be one of the known fillable roles.
    * The role's scheduling flag must be enabled in SiteConfiguration.
    * The user must hold the appropriate qualification flag.
    * The role must still be empty (race-condition guard via conditional UPDATE query).
    * The day must be today or in the future.
    """
    if role not in _HOLE_FILL_ROLE_MAP:
        messages.error(request, "Unknown role specified.")
        return redirect("duty_roster:duty_calendar")

    qual_attr, assign_attr, config_title_attr, default_title, schedule_attr = (
        _HOLE_FILL_ROLE_MAP[role]
    )

    assignment = get_object_or_404(DutyAssignment, id=assignment_id)
    member = request.user

    # Fetch config once; derive the human-readable role label from it.
    config = SiteConfiguration.objects.first()
    role_label = (
        getattr(config, config_title_attr, None) if config else None
    ) or default_title

    # Past days are not fillable.
    if assignment.date < date.today():
        messages.error(request, "You cannot fill roles on past duty days.")
        return redirect("duty_roster:duty_calendar")

    # Reject if this role is not enabled for scheduling.
    if not (config and getattr(config, schedule_attr, False)):
        messages.error(
            request,
            f"The {role_label} role is not currently enabled for scheduling.",
        )
        return redirect("duty_roster:duty_calendar")

    # Check qualification.
    is_qualified = (
        _is_commercial_pilot_qualified(member)
        if qual_attr == "__commercial_rating__"
        else bool(getattr(member, qual_attr, False))
    )
    if not is_qualified:
        messages.error(
            request,
            f"You are not qualified to fill the {role_label} role.",
        )
        return redirect("duty_roster:duty_calendar")

    if request.method == "POST":
        # Atomically claim the slot with a conditional UPDATE so concurrent
        # volunteers cannot both succeed.  filter(..., <field>__isnull=True)
        # matches only if the role is still empty; update() returns the number
        # of rows actually modified, so 0 means someone else just got there first.
        rows = DutyAssignment.objects.filter(
            pk=assignment.id, **{f"{assign_attr}__isnull": True}
        ).update(**{assign_attr: member.id})
        if rows == 0:
            messages.info(
                request,
                f"Someone just claimed the {role_label} slot for "
                f"{assignment.date.strftime('%B %d, %Y')} ahead of you. "
                "Thank you for offering!",
            )
            return redirect("duty_roster:duty_calendar")

        # For ad-hoc days: refresh from DB so notify_ops_status sees the
        # latest state and can fire the collecting-volunteers → confirmed-ops
        # transition (issue #696).  Scheduled days short-circuit inside
        # notify_ops_status anyway, so skipping the refresh + call for them
        # avoids a redundant DB round-trip and debug log noise.
        if not assignment.is_scheduled:
            assignment.refresh_from_db()  # type: ignore[call-arg]
            notify_ops_status(assignment)

        messages.success(
            request,
            f"You have been assigned as {role_label} for "
            f"{assignment.date.strftime('%B %d, %Y')}. Thank you for volunteering!",
        )
        return redirect("duty_roster:duty_calendar")

    # GET – stale-navigation guard: if the slot was already filled before the
    # user loaded this page, give a friendly message rather than a blank confirm.
    if getattr(assignment, assign_attr) is not None:
        messages.info(
            request,
            f"The {role_label} slot for {assignment.date.strftime('%B %d, %Y')} "
            "has already been filled. Thank you for your willingness!",
        )
        return redirect("duty_roster:duty_calendar")

    # GET – render confirmation page
    return render(
        request,
        "duty_roster/volunteer_fill_confirm.html",
        {
            "assignment": assignment,
            "role": role,
            "role_label": role_label,
        },
    )
