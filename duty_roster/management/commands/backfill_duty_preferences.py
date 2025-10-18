from django.core.management.base import BaseCommand

from duty_roster.models import DutyPreference
from members.models import Member


class Command(BaseCommand):
    help = "Backfill DutyPreference records for active members based on role flags"

    def handle(self, *args, **options):
        created = 0

        for m in Member.objects.filter(is_active=True):
            if DutyPreference.objects.filter(member=m).exists():
                continue

            defaults = {}
            if m.instructor:
                defaults["instructor_percent"] = 25
            if m.duty_officer:
                defaults["duty_officer_percent"] = 25
            if m.assistant_duty_officer:
                defaults["ado_percent"] = 25
            if m.towpilot:
                defaults["towpilot_percent"] = 25

            if defaults:
                DutyPreference.objects.create(member=m, **defaults)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"✅ Backfilled {created} duty preferences.")
        )
