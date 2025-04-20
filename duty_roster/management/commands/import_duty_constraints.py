import json
import difflib
from django.core.management.base import BaseCommand
from members.models import Member
from duty_roster.models import DutyPreference, DutyPairing, DutyAvoidance, MemberBlackout
from datetime import datetime


class Command(BaseCommand):
    help = "Import duty preference and constraint data from membership.json"

    def add_arguments(self, parser):
        parser.add_argument("path", type=str, help="Path to membership.json")

    def handle(self, *args, **options):
        path = options["path"]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_members = list(Member.objects.all())
        name_map = {m.full_display_name.lower(): m for m in all_members}

        def resolve_name(raw_name):
            candidates = list(name_map.keys())
            best = difflib.get_close_matches(raw_name.lower(), candidates, n=1, cutoff=0.85)
            return name_map[best[0]] if best else None

        self.stdout.write(self.style.NOTICE(f"Processing {len(data)} member entries..."))

        for entry in data:
            raw_name = entry.get("name")
            if not raw_name:
                continue

            member = resolve_name(raw_name)
            if not member:
                self.stderr.write(self.style.ERROR(f"❌ Could not resolve: {raw_name}"))
                continue

            # Import DutyPreference
            preferred_day = entry.get("preferred-day")
            comment = entry.get("web-comment") or entry.get("comment")
            if preferred_day or comment:
                DutyPreference.objects.update_or_create(
                    member=member,
                    defaults={"preferred_day": preferred_day.lower() if preferred_day else None,
                              "comment": comment}
                )

            # Import DutyPairing
            pair_name = entry.get("schedule-with-member")
            if pair_name:
                pair_member = resolve_name(pair_name)
                if pair_member:
                    DutyPairing.objects.get_or_create(member=member, pair_with=pair_member)
                else:
                    self.stderr.write(self.style.WARNING(f"Could not resolve pair-with-member: {pair_name}"))

            # Import DutyAvoidance
            avoid_name = entry.get("dont-schedule-with-member")
            if avoid_name:
                avoid_member = resolve_name(avoid_name)
                if avoid_member:
                    DutyAvoidance.objects.get_or_create(member=member, avoid_with=avoid_member)
                else:
                    self.stderr.write(self.style.WARNING(f"Could not resolve dont-schedule-with-member: {avoid_name}"))

            blackouts = entry.get("blackouts", [])
            for date_str in blackouts:
                try:
                    d = datetime.strptime(date_str, "%m/%d/%Y").date()
                    MemberBlackout.objects.get_or_create(member=member, date=d)
                except ValueError:
                    self.stderr.write(self.style.WARNING(f"Invalid blackout date for {member}: {date_str}"))
            
            self.stdout.write(f"✅ Imported preferences for {member.full_display_name}")

        self.stdout.write(self.style.SUCCESS("🎯 All duty constraints imported."))
