import calendar
import random
from collections import defaultdict
from datetime import date
from duty_roster.models import DutySlot, DutyPreference, DutyAvoidance, DutyPairing, MemberBlackout
from members.models import Member


def generate_roster(year=None, month=None):
    """
    Generate a roster for the given year/month.
    Returns a list of dicts: { 'date': date, 'slots': { slot_name: member_id, ... } }
    """
    # default to current month/year if not provided
    from django.utils.timezone import now
    today = now().date()
    year = year or today.year
    month = month or today.month

    cal = calendar.Calendar()
    weekend_dates = [
        d for d in cal.itermonthdates(year, month)
        if d.month == month and d.weekday() in (5, 6)
    ]

    # prepare data
    members = list(Member.objects.filter(is_active=True))
    prefs_qs = DutyPreference.objects.select_related('member').all()
    preferences = {p.member_id: p for p in prefs_qs}
    avoid = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
    pairings = defaultdict(set)
    for p in DutyPairing.objects.all():
        pairings[p.member_id].add(p.pair_with_id)
    blackouts = {
        (b.member_id, b.date): b
        for b in MemberBlackout.objects.filter(date__year=year, date__month=month)
    }
    assignments_per_member = defaultdict(int)

    def last_duty_sort_key(m):
        p = preferences.get(m.id)
        return p.last_duty_date or date(1900, 1, 1)

    def eligible_for(role, member, day, assigned_today):
        p = preferences.get(member.id)
        if not p or p.dont_schedule or p.scheduling_suspended:
            return False
        # blackout
        if (member.id, day) in blackouts:
            return False
        # role flags
        flag = getattr(member, role)
        pct = getattr(p, f"{role}_percent", 0)
        if not flag or pct == 0:
            return False
        # max per month
        if assignments_per_member[member.id] >= p.max_assignments_per_month:
            return False
        # already assigned today
        if member in assigned_today:
            return False
        return True

    def weighted_choice(candidates, role, assigned_today):
        weights = []
        for m in candidates:
            p = preferences.get(m.id)
            base = getattr(p, f"{role}_percent", 0)
            w = base
            # pairing bonus
            for a in assigned_today:
                if a.id in pairings.get(m.id, set()) or m.id in pairings.get(a.id, set()):
                    w *= 3
                    break
            weights.append(w)
        if not weights or sum(weights) == 0:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]

    def try_generate():
        schedule = []
        success = True
        for day in weekend_dates:
            assigned_today = set()
            slots = {}
            for role in ['instructor', 'duty_officer', 'assistant_duty_officer', 'towpilot']:
                # filter DutySlot name if needed
                # get DutySlot by role name mapping
                candidates = [m for m in members if eligible_for(role, m, day, assigned_today)]
                candidates.sort(key=last_duty_sort_key)
                chosen = weighted_choice(candidates, role, assigned_today)
                if chosen:
                    assigned_today.add(chosen)
                    assignments_per_member[chosen.id] += 1
                    slots[role] = chosen.id
                else:
                    slots[role] = None
                    if role == 'towpilot':
                        success = False
            schedule.append({'date': day, 'slots': slots})
        return schedule if success else None

    # try up to 5 times
    for _ in range(5):
        result = try_generate()
        if result:
            return result
    # failed
    return []