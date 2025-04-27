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
    assignments_per_member = defaultdict(int)
    def last_duty_sort_key(m):
        p = prefs.get(m.id)
        return getattr(p, 'last_duty_date', date(1900, 1, 1))
    def eligible_for(role, member, day, assigned):
        p = prefs.get(member.id)
        if not p or p.dont_schedule or p.scheduling_suspended:
            return False
        if (member.id, day) in blackouts:
            return False
        for other in assigned:
            if (member.id, other.id) in avoidances or (other.id, member.id) in avoidances:
                return False
        flag = getattr(member, role, False)
        pct = getattr(p, 'ado_percent', 0) if role == 'assistant_duty_officer' else getattr(p, f'{role}_percent', 0)
        if not flag or pct == 0:
            return False
        if assignments_per_member[member.id] >= getattr(p, 'max_assignments_per_month', 0):
            return False
        if member in assigned:
            return False
        return True
    def weighted_choice(cands, role, assigned):
        weights = []
        for m in cands:
            p = prefs.get(m.id)
            base = getattr(p, 'ado_percent', 0) if role == 'assistant_duty_officer' else getattr(p, f'{role}_percent', 0)
            w = base
            for a in assigned:
                if a.id in pairings.get(m.id, set()) or m.id in pairings.get(a.id, set()):
                    w *= 3
                    break
            weights.append(w)
        return None if not weights or sum(weights) == 0 else random.choices(cands, weights=weights, k=1)[0]
    schedule = []
    last_assigned = {role: None for role in DEFAULT_ROLES}
    for day in weekend_dates:
        assigned_today = set()
        slots = {}
        for role in DEFAULT_ROLES:
            cands = [
                m for m in members
                if eligible_for(role, m, day, assigned_today)
                and m.id != last_assigned.get(role)
            ]
            cands.sort(key=last_duty_sort_key)
            chosen = weighted_choice(cands, role, assigned_today)
            if chosen:
                assigned_today.add(chosen)
                assignments_per_member[chosen.id] += 1
                slots[role] = chosen.id
            else:
                slots[role] = None
        schedule.append({'date': day, 'slots': slots})
        last_assigned = slots.copy()
    return schedule