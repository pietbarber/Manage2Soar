import calendar

from django.core.management.base import BaseCommand

from members.models import Member

from duty_roster.roster_generator import generate_roster as generate_duty_roster


class Command(BaseCommand):
    help = "Prototype scheduler to generate a duty roster for a given month/year"

    def add_arguments(self, parser):
        parser.add_argument("year", type=int, help="Year for duty roster")
        parser.add_argument("month", type=int, help="Month for duty roster")

    def handle(self, *args, **options):
        year = options["year"]
        month = options["month"]
        schedule = generate_duty_roster(year, month)
        if not schedule:
            self.stdout.write(self.style.ERROR("Could not generate a complete roster."))
            return

        notice = f"\n📆 Duty Roster for {calendar.month_name[month]} {year}:"
        self.stdout.write(self.style.NOTICE(notice))
        for entry in schedule:
            day = entry["date"]
            day_line = f"\n🗓 {day.strftime('%A, %B %d')}"
            self.stdout.write(day_line)
            for role, member_id in entry["slots"].items():
                if member_id:
                    m = Member.objects.get(pk=member_id)
                    self.stdout.write(
                        f"  - {role.title()}: {m.full_display_name}"
                    )
                else:
                    none_line = f"  - {role.title()}: ❌ None"
                    self.stdout.write(none_line)
