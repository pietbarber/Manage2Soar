"""
Management command to test roster generation with operational calendar filtering.
Useful for the Rostermeister to validate the operational season configuration.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from duty_roster.roster_generator import generate_roster, is_within_operational_season
from duty_roster.operational_calendar import get_operational_weekend
from siteconfig.models import SiteConfiguration


class Command(BaseCommand):
    help = "Test duty roster generation with operational calendar filtering"

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=None,
            help='Year to test (default: current year)'
        )
        parser.add_argument(
            '--month',
            type=int,
            default=None,
            help='Month to test (1-12, default: current month)'
        )
        parser.add_argument(
            '--show-config',
            action='store_true',
            help='Show current operational calendar configuration'
        )

    def handle(self, *args, **options):
        year = options['year'] or timezone.now().year
        month = options['month'] or timezone.now().month

        self.stdout.write(
            self.style.SUCCESS(f"Testing Duty Roster Generation for {year}-{month:02d}")
        )
        self.stdout.write("=" * 50)

        # Show current configuration
        config = SiteConfiguration.objects.first()
        if config and (config.operations_start_period or config.operations_end_period):
            self.stdout.write("\nCurrent Operational Calendar Configuration:")
            self.stdout.write(f"  Start: {config.operations_start_period}")
            self.stdout.write(f"  End: {config.operations_end_period}")

            if options['show_config']:
                try:
                    # Show actual season boundaries for the test year
                    start_sat, start_sun = get_operational_weekend(
                        year, config.operations_start_period)
                    end_sat, end_sun = get_operational_weekend(
                        year, config.operations_end_period)

                    season_start = min(start_sat, start_sun)
                    season_end = max(end_sat, end_sun)

                    self.stdout.write(f"\n{year} Operational Season Boundaries:")
                    self.stdout.write(
                        f"  Start: {season_start} ({season_start.strftime('%A')})")
                    self.stdout.write(
                        f"  End: {season_end} ({season_end.strftime('%A')})")

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error calculating season boundaries: {e}")
                    )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "No operational calendar configuration found - all dates will be included")
            )

        # Generate roster
        self.stdout.write(f"\nGenerating roster for {year}-{month:02d}...")

        try:
            schedule = generate_roster(year=year, month=month)

            if schedule:
                self.stdout.write(
                    self.style.SUCCESS(f"\nGenerated {len(schedule)} duty assignments:")
                )

                for entry in schedule:
                    roster_date = entry['date']
                    in_season = is_within_operational_season(roster_date)
                    status_icon = "✅" if in_season else "❌"

                    self.stdout.write(
                        f"  {roster_date.strftime('%Y-%m-%d (%A)')} {status_icon}")

            else:
                self.stdout.write(
                    self.style.WARNING("No duty assignments generated")
                )
                self.stdout.write("This could mean:")
                self.stdout.write(
                    "  - All weekend dates fall outside the operational season")
                self.stdout.write(
                    "  - No active members available for duty assignments")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error generating roster: {e}")
            )

        # Show examples for common scenarios
        if options['show_config']:
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("Example Configuration Formats:")
            self.stdout.write("  'First weekend of May' or '1st weekend of May'")
            self.stdout.write("  'Second weekend of April' or '2nd weekend of Apr'")
            self.stdout.write("  'Third weekend in October' or '3rd weekend Oct'")
            self.stdout.write("  'Last weekend of December' or 'Last weekend Dec'")
            self.stdout.write("  '4th weekend in September' or 'Fourth weekend Sep'")
            self.stdout.write(
                "\nSupported ordinals: First/1st, Second/2nd, Third/3rd, Fourth/4th, Last")
            self.stdout.write(
                "Supported months: Full names (January) or abbreviations (Jan, Sep, Dec)")
            self.stdout.write(
                "Connecting words: 'of', 'in' are optional ('1st weekend May' works)")
            self.stdout.write(
                "\n💡 The system is flexible - most reasonable formats will work!")
