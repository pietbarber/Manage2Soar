from members.models import Member
from members.constants.membership import DEFAULT_ROLES
from duty_roster.models import (
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    MemberBlackout,
)
from datetime import date
from collections import defaultdict
import random
import calendar
import logging

logger = logging.getLogger("duty_roster.generator")
# duty_roster/roster_generator.py


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
            logger.debug("%s: No DutyPreference found.", m.full_display_name)
            return False
        if p.dont_schedule:
            logger.debug("%s: 'Don't schedule' is set.", m.full_display_name)
            return False
        if p.scheduling_suspended:
            logger.debug("%s: Scheduling suspended.", m.full_display_name)
            return False
        if (m.id, day) in blackouts:
            logger.debug("%s: Blacked out on %s.", m.full_display_name, day)
            return False
        for o in assigned:
            if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                logger.debug(
                    "%s: Avoids %s.", m.full_display_name, o.full_display_name
                )
                return False
        if m in assigned:
            logger.debug("%s: Already assigned today.", m.full_display_name)
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
                    "%s: Only eligible for %s, percent is 0, treating as 100.",
                    m.full_display_name,
                    role,
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
                    "%s: All eligible role percents are zero, treating %s as 100.",
                    m.full_display_name,
                    role,
                )
        if not flag:
            logger.debug(
                "%s: Not eligible for role %s (flag is False).",
                m.full_display_name,
                role,
            )
            return False
        if pct == 0:
            logger.debug("%s: %s percent is 0.", m.full_display_name, role)
            return False
        if assignments[m.id] >= getattr(p, "max_assignments_per_month", 0):
            logger.debug(
                "%s: Max assignments per month reached.", m.full_display_name
            )
            return False
        logger.debug(
            "%s: Eligible for %s on %s (pct=%s).",
            m.full_display_name,
            role,
            day,
            pct,
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
                    "Candidate: %s, base weight: %s, final weight: %s",
                    m.full_display_name,
                    base,
                    w,
                )
            weights.append(w)
        if not weights or sum(weights) == 0:
            logger.debug(
                "No candidates with nonzero weights for role %s.", role
            )
            return None
        chosen = random.choices(cands, weights=weights, k=1)[0]
        chosen_list = [m.full_display_name for m in cands]
        logger.debug(
            "Chose %s for role %s from %s",
            chosen.full_display_name,
            role,
            chosen_list,
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
