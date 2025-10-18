import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from logsheet.models import Airfield, Logsheet, Towplane
from members.models import Member


class Command(BaseCommand):
    help = "Load sample logsheets for testing purposes."

    def handle(self, *args, **options):
        today = timezone.now().date()
        airfields = list(Airfield.objects.all())
        members = list(Member.objects.all())
        towpilots = [m for m in members if m.towpilot]
        instructors = [m for m in members if m.instructor]
        ados = [m for m in members if m.assistant_duty_officer]
        duty_officers = [m for m in members if m.duty_officer]
        towplanes = list(Towplane.objects.all())

        if not (airfields and members and towplanes):
            self.stdout.write(
                self.style.ERROR("Not enough data to generate logsheets.")
            )
            return

        created = 0
        for i in range(10):
            date = today - timedelta(days=10 - i)
            airfield = airfields[i % len(airfields)]

            if Logsheet.objects.filter(log_date=date, airfield=airfield).exists():
                continue

            logsheet = Logsheet.objects.create(
                log_date=date,
                airfield=airfield,
                created_by=random.choice(members),
                duty_officer=random.choice(duty_officers) if duty_officers else None,
                assistant_duty_officer=random.choice(ados) if ados else None,
                duty_instructor=random.choice(instructors) if instructors else None,
                surge_instructor=random.choice(instructors) if instructors else None,
                tow_pilot=random.choice(towpilots) if towpilots else None,
                surge_tow_pilot=random.choice(towpilots) if towpilots else None,
                default_towplane=random.choice(towplanes),
            )
            created += 1
            self.stdout.write(f"Created logsheet for {logsheet}")

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {created} sample logsheets.")
        )
