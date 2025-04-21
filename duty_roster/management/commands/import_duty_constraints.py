import json
import difflib
from django.core.management.base import BaseCommand
from datetime import datetime
from members.models import Member
from duty_roster.models import DutyPreference, DutyPairing, DutyAvoidance, MemberBlackout

class Command(BaseCommand):
    help = "Import duty constraints and preferences from a legacy membership.json file"

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str)

    def handle(self, *args, **options):
        with open(options["json_file"], "r", encoding="utf-8") as f:
            data = json.load(f)

        members = list(Member.objects.all())
        name_map = {m.full_display_name: m for m in members}
        name_list = list(name_map.keys())

        def resolve(name):
            matches = difflib.get_close_matches(name, name_list, n=1, cutoff=0.85)
            return name_map[matches[0]] if matches else None

        for raw in data:
            name = raw.get("name")
            member = resolve(name)
            if not member:
                self.stdout.write(self.style.WARNING(f"Skipping {name} (no handle)"))
                continue

            # DutyPreference
            pref, _ = DutyPreference.objects.get_or_create(member=member)
            pref.preferred_day = raw.get("preferred-day") or pref.preferred_day
            pref.comment = raw.get("comment") or raw.get("web-comment") or pref.comment
            pref.dont_schedule = str(raw.get("dont-schedule", "")).lower() in ["true", "1", "yes"]

            if raw.get("last-duty-date"):
                date_str = raw["last-duty-date"]
                for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        pref.last_duty_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    self.stdout.write(self.style.WARNING(f"Bad last-duty-date for {name}: {date_str}"))

            if pref.max_assignments_per_month in (None, 0):
                pref.max_assignments_per_month = 2

            pref.save()

            # DutyPairing
            pair_with = raw.get("schedule-with-member")
            if pair_with:
                other = resolve(pair_with)
                if other:
                    DutyPairing.objects.get_or_create(member=member, pair_with=other)

            # DutyAvoidance
            avoid = raw.get("dont-schedule-with-member")
            if avoid:
                avoid_member = resolve(avoid)
                if avoid_member:
                    DutyAvoidance.objects.get_or_create(member=member, avoid_with=avoid_member)

            # MemberBlackout
            for bdate in raw.get("blackouts", []):
                try:
                    blackout_date = datetime.strptime(bdate, "%m/%d/%Y").date()
                    MemberBlackout.objects.get_or_create(member=member, date=blackout_date)
                except ValueError:
                    self.stdout.write(self.style.WARNING(f"Invalid blackout date for {name}: {bdate}"))

            self.stdout.write(self.style.SUCCESS(f"✅ Imported constraints for {name}"))
