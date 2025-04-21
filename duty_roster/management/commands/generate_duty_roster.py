from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import date, timedelta
import calendar
import random
from collections import defaultdict
from duty_roster.models import DutySlot, DutyPreference, DutyAvoidance, DutyPairing, MemberBlackout
from members.models import Member

class Command(BaseCommand):
    help = "Prototype scheduler to generate a duty roster for a given month/year"

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)
        parser.add_argument("month", type=int)

    def handle(self, *args, **options):
        year = options["year"]
        month = options["month"]
        cal = calendar.Calendar()

        weekend_dates = [
            d for d in cal.itermonthdates(year, month)
            if d.month == month and d.weekday() in (5, 6)
        ]

        def generate_schedule():
            members = list(Member.objects.filter(is_active=True))
            preferences = {p.member_id: p for p in DutyPreference.objects.select_related("member").all()}
            avoid = {(a.member_id, a.avoid_with_id) for a in DutyAvoidance.objects.all()}
            pairings = defaultdict(set)
            for p in DutyPairing.objects.all():
                pairings[p.member_id].add(p.pair_with_id)
            blackouts = {
                (b.member_id, b.date): b for b in MemberBlackout.objects.filter(date__month=month, date__year=year)
            }

            assignments_per_member = defaultdict(int)
            MAX_ASSIGNMENTS_PER_MONTH = 2
            schedule_output = []

            def last_duty_sort_key(m):
                p = preferences.get(m.id)
                return p.last_duty_date or date(1900, 1, 1)

            def eligible_for(role, member):
                p = preferences.get(member.id)
                if not p:
                    return False
                if p.dont_schedule:
                    return False
                if role == "instructor" and (not member.instructor or p.instructor_percent == 0):
                    return False
                if role == "duty_officer" and (not member.duty_officer or p.duty_officer_percent == 0):
                    return False
                if role == "ado" and (not member.assistant_duty_officer or p.ado_percent == 0):
                    return False
                if role == "towpilot" and (not member.towpilot or p.towpilot_percent == 0):
                    return False
                return True

            def weighted_choice(members, role, assigned_today):
                candidates = []
                weights = []

                for m in members:
                    p = preferences.get(m.id)
                    if not p:
                        continue
                    percent = getattr(p, f"{role}_percent", 0)
                    if percent == 0:
                        continue

                    weight = percent
                    # Bonus if paired member is already scheduled today
                    for assigned in assigned_today:
                        if assigned.id in pairings.get(m.id, set()) or m.id in pairings.get(assigned.id, set()):
                            weight *= 3  # boost priority
                            break

                    candidates.append(m)
                    weights.append(weight)

                if not weights or sum(weights) == 0:
                    return None
                return random.choices(candidates, weights=weights, k=1)[0]

            success = True

            for ops_day in weekend_dates:
                assigned_today = set()
                assigned = {}

                for role in ["instructor", "duty_officer", "ado", "towpilot"]:
                    eligible = [
                        m for m in members
                        if eligible_for(role, m)
                        and (m.id, ops_day) not in blackouts
                        and m not in assigned_today
                        and assignments_per_member[m.id] < MAX_ASSIGNMENTS_PER_MONTH
                    ]
                    random.shuffle(eligible)
                    eligible.sort(key=last_duty_sort_key)

                    chosen = weighted_choice(eligible, role, assigned_today)
                    if chosen:
                        assigned_today.add(chosen)
                        assignments_per_member[chosen.id] += 1
                    assigned[role] = chosen

                schedule_output.append((ops_day, assigned))
                if not assigned["towpilot"]:
                    success = False

            return schedule_output if success else None

        MAX_ATTEMPTS = 5
        for attempt in range(1, MAX_ATTEMPTS + 1):
            schedule = generate_schedule()
            if schedule:
                self.stdout.write(self.style.NOTICE(f"Roster generated on attempt #{attempt}"))
                break
        else:
            self.stdout.write(self.style.ERROR("❌ Could not generate a complete roster after 5 attempts."))
            return

        self.stdout.write(self.style.NOTICE(f"\n📆 Finalized Duty Roster for {calendar.month_name[month]} {year}:"))

        for ops_day, assigned in schedule:
            self.stdout.write("\n🗓️  {}:".format(ops_day.strftime("%A, %B %d")))
            for role, m in assigned.items():
                if m:
                    self.stdout.write(f"  - {role.title()}: {m.full_display_name}")
                else:
                    self.stdout.write(f"  - {role.title()}: ❌ No one available")

        self.stdout.write(self.style.SUCCESS("\n✅ Duty roster draft complete."))
