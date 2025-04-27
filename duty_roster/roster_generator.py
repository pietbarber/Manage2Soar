# duty_roster/roster_generator.py

import calendar
import random
from collections import defaultdict
from datetime import date
from duty_roster.models import DutyPreference, DutyAvoidance, DutyPairing, MemberBlackout
from members.models import Member
from members.constants.membership import DEFAULT_ROLES

def generate_roster(year=None, month=None):
    from django.utils.timezone import now
    today = now().date()
    year = year or today.year
    month = month or today.month
    cal = calendar.Calendar()
    weekend_dates = [
        d for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() in (5, 6)
    ]
    members = list(Member.objects.filter(is_active=True))
    prefs = {p.member_id: p for p in DutyPreference.objects.select_related('member').all()}
    avoidances = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
    pairings = defaultdict(set)
    for p in DutyPairing.objects.all():
        pairings[p.member_id].add(p.pair_with_id)
    blackouts = {(b.member_id, b.date) for b in MemberBlackout.objects.filter(date__year=year, date__month=month)}
    assignments = defaultdict(int)
    def last_key(m):
        p = prefs.get(m.id)
        return getattr(p, 'last_duty_date', date(1900, 1, 1))
    def eligible(role, m, day, assigned):
        p = prefs.get(m.id)
        if not p or p.dont_schedule or p.scheduling_suspended:
            return False
        if (m.id, day) in blackouts:
            return False
        for o in assigned:
            if (m.id, o.id) in avoidances or (o.id, m.id) in avoidances:
                return False
        if m in assigned:
            return False
        flag = getattr(m, role, False)
        pct = (
            getattr(p, 'ado_percent', 0)
            if role == 'assistant_duty_officer'
            else getattr(p, f'{role}_percent', 0)
        )
        if not flag or pct == 0:
            return False
        if assignments[m.id] >= getattr(p, 'max_assignments_per_month', 0):
            return False
        return True
    def choose(cands, role, assigned):
        weights = []
        for m in cands:
            p = prefs.get(m.id)
            base = (
                getattr(p, 'ado_percent', 0)
                if role == 'assistant_duty_officer'
                else getattr(p, f'{role}_percent', 0)
            )
            w = base
            for o in assigned:
                if o.id in pairings.get(m.id, set()) or m.id in pairings.get(o.id, set()):
                    w *= 3
                    break
            weights.append(w)
        if not weights or sum(weights) == 0:
            return None
        return random.choices(cands, weights=weights, k=1)[0]
    schedule = []
    last_assigned = {role: None for role in DEFAULT_ROLES}
    for day in weekend_dates:
        assigned_today = set()
        slots = {}
        for role in DEFAULT_ROLES:
            cands = [
                m for m in members
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
        schedule.append({'date': day, 'slots': slots})
        last_assigned = slots.copy()
    return schedule
