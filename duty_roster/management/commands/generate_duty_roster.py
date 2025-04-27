from django.core.management.base import BaseCommand
from django.utils.timezone import now
from . import generate_duty_roster
import calendar
from members.models import Member

class Command(BaseCommand):
    help = "Prototype scheduler to generate a duty roster for a given month/year"

    def add_arguments(self, parser):
        parser.add_argument('year', type=int, help='Year for duty roster')
        parser.add_argument('month', type=int, help='Month for duty roster')

    def handle(self, *args, **options):
        year = options['year']
        month = options['month']
        schedule = generate_duty_roster(year, month)
        if not schedule:
            self.stdout.write(self.style.ERROR('Could not generate a complete roster.'))
            return

        self.stdout.write(self.style.NOTICE(
            f"\n📆 Duty Roster for {calendar.month_name[month]} {year}:"
        ))
        for entry in schedule:
            day = entry['date']
            self.stdout.write(f"\n🗓 {day.strftime('%A, %B %d')}")
            for role, member_id in entry['slots'].items():
                if member_id:
                    m = Member.objects.get(pk=member_id)
                    self.stdout.write(f"  - {role.title()}: {m.full_display_name}")
                else:
                    self.stdout.write(f"  - {role.title()}: ❌ None")

