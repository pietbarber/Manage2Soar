"""
Management command to display flight counts by date for 2025.
Usage: python manage.py flights_by_date_2025
"""

from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Count

from logsheet.models import Flight


class Command(BaseCommand):
    help = "Display summary of flights by date for the year 2025"

    def handle(self, *args, **options):
        # Query flights from 2025
        flights_by_date = (
            Flight.objects.filter(date__year=2025)
            .values("date")
            .annotate(flight_count=Count("id"))
            .order_by("date")
        )

        if not flights_by_date:
            self.stdout.write(self.style.WARNING("No flights found for 2025"))
            return

        # Display summary
        self.stdout.write(self.style.SUCCESS("\n=== Flight Summary for 2025 ===\n"))

        total_flights = 0
        for entry in flights_by_date:
            flight_date = entry["date"]
            count = entry["flight_count"]
            total_flights += count

            self.stdout.write(
                f"{flight_date.strftime('%Y-%m-%d (%A)')}: {count} flights"
            )

        # Display total
        self.stdout.write(
            self.style.SUCCESS(f"\nTotal flights in 2025: {total_flights}")
        )
        self.stdout.write(
            self.style.SUCCESS(f"Flying days in 2025: {flights_by_date.count()}")
        )
