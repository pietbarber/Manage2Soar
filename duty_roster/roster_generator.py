import logging

logger = logging.getLogger("duty_roster.generator")
# duty_roster/roster_generator.py

import calendar
import random
from collections import defaultdict
from datetime import date

from duty_roster.models import (
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
)
from members.constants.membership import DEFAULT_ROLES
from members.models import Member


def generate_roster(year=None, month=None):
    from django.utils.timezone import now

    today = now().date()
    year = year or today.year
    month = month or today.month
    cal = calendar.Calendar()
    weekend_dates = [
        d
        for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() in (5, 6)
    ]
    members = list(Member.objects.filter(is_active=True))
    prefs = {
        p.member_id: p for p in DutyPreference.objects.select_related("member").all()
    }
    avoidances = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
    pairings = defaultdict(set)
    for p in DutyPairing.objects.all():
        pairings[p.member_id].add(p.pair_with_id)
    blackouts = {
        (b.member_id, b.date)
        for b in MemberBlackout.objects.filter(date__year=year, date__month=month)
    }
    assignments = defaultdict(int)

    def last_key(m):
        p = prefs.get(m.id)
        d = getattr(p, "last_duty_date", None)
        return d or date(1900, 1, 1)

    def eligible(role, m, day, assigned):
        p = prefs.get(m.id)
        if not p:
            logger.debug(f"{m.full_display_name}: No DutyPreference found.")
            return False
        if p.dont_schedule:
            logger.debug(f"{m.full_display_name}: 'Don't schedule' is set.")
            return False
        if p.scheduling_suspended:
            logger.debug(f"{m.full_display_name}: Scheduling suspended.")
            return False
        if (m.id, day) in blackouts:
            logger.debug(f"{m.full_display_name}: Blacked out on {day}.")
            return False
        for o in assigned:
            if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                logger.debug(f"{m.full_display_name}: Avoids {o.full_display_name}.")
                return False
        if m in assigned:
            logger.debug(f"{m.full_display_name}: Already assigned today.")
            return False
        flag = getattr(m, role, False)
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
                logger.debug(
                    f"{m.full_display_name}: Only eligible for {role}, percent is 0, treating as 100%."
                )
                pct = 100
        else:
            all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
            if role == "assistant_duty_officer":
                pct = p.ado_percent if not all_zero else 100
            else:
                pct = getattr(p, f"{role}_percent", 0) if not all_zero else 100
            if all_zero:
                logger.debug(
                    f"{m.full_display_name}: All eligible role percents are zero, treating {role} as 100%."
                )
        if not flag:
            logger.debug(
                f"{m.full_display_name}: Not eligible for role {role} (flag is False)."
            )
            return False
        if pct == 0:
            logger.debug(f"{m.full_display_name}: {role} percent is 0.")
            return False
        if assignments[m.id] >= getattr(p, "max_assignments_per_month", 0):
            logger.debug(f"{m.full_display_name}: Max assignments per month reached.")
            return False
        logger.debug(
            f"{m.full_display_name}: Eligible for {role} on {day} (pct={pct})."
        )
        return True

    def choose(cands, role, assigned):
        weights = []
        for m in cands:
            p = prefs.get(m.id)
            percent_fields = [
                ("instructor", "instructor_percent"),
                ("duty_officer", "duty_officer_percent"),
                ("assistant_duty_officer", "ado_percent"),
                ("towpilot", "towpilot_percent"),
            ]
            eligible_role_fields = [
                field for r, field in percent_fields if getattr(m, r, False)
            ]
            if not p:
                base = 0
            elif len(eligible_role_fields) == 1:
                field = eligible_role_fields[0]
                base = getattr(p, field, 0)
                if base == 0:
                    base = 100
            else:
                all_zero = all(getattr(p, f, 0) == 0 for f in eligible_role_fields)
                if role == "assistant_duty_officer":
                    base = getattr(p, "ado_percent", 0) if not all_zero else 100
                else:
                    base = getattr(p, f"{role}_percent", 0) if not all_zero else 100
            w = base
            for o in assigned:
                if o.id in pairings.get(m.id, set()) or m.id in pairings.get(
                    o.id, set()
                ):
                    w *= 3
                    break
            logger.debug(
                f"Candidate: {m.full_display_name}, base weight: {base}, final weight: {w}"
            )
            weights.append(w)
        if not weights or sum(weights) == 0:
            logger.debug(f"No candidates with nonzero weights for role {role}.")
            return None
        chosen = random.choices(cands, weights=weights, k=1)[0]
        logger.debug(
            f"Chose {chosen.full_display_name} for role {role} from {[m.full_display_name for m in cands]}"
        )
        return chosen

    schedule = []
    last_assigned = {role: None for role in DEFAULT_ROLES}
    for day in weekend_dates:
        assigned_today = set()
        slots = {}
        for role in DEFAULT_ROLES:
            cands = [
                m
                for m in members
                if eligible(role, m, day, assigned_today)
                and m.id != last_assigned.get(role)
            ]
            cands.sort(key=last_key)
            sel = choose(cands, role, assigned_today)
            if sel:
                assigned_today.add(sel)
                assignments[sel.id] += 1
                slots[role] = sel.id
            else:
                slots[role] = None
        schedule.append({"date": day, "slots": slots})
        last_assigned = slots.copy()
    return schedule
