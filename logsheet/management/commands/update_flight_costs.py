from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date
from logsheet.models import Logsheet, Flight
from django.db import transaction


class Command(BaseCommand):
    help = "Update flight costs for a logsheet on a given date, only if costs are missing or zero."

    def add_arguments(self, parser):
        parser.add_argument(
            "date", type=str, help="Date of the logsheet (YYYY-MM-DD)")

    @transaction.atomic
    def handle(self, *args, **options):
        date_str = options["date"]
        log_date = parse_date(date_str)
        if not log_date:
            raise CommandError(
                f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

        try:
            logsheet = Logsheet.objects.get(log_date=log_date)
        except Logsheet.DoesNotExist:
            raise CommandError(f"No logsheet found for date {date_str}.")

        flights = Flight.objects.filter(logsheet=logsheet)
        updated = 0
        for flight in flights:
            tow_actual = getattr(flight, 'tow_cost_actual', None)
            rental_actual = getattr(flight, 'rental_cost_actual', None)
            # Only update if both are missing or zero
            if (tow_actual is None or tow_actual == 0) and (rental_actual is None or rental_actual == 0):
                # Use model properties to calculate
                tow = flight.tow_cost or 0
                rental = flight.rental_cost or 0
                flight.tow_cost_actual = tow
                flight.rental_cost_actual = rental
                flight.save()
                updated += 1
                self.stdout.write(
                    f"Updated flight ID {flight.pk} (tow: {tow}, rental: {rental})")
        self.stdout.write(self.style.SUCCESS(
            f"Updated {updated} flights for logsheet {logsheet} on {log_date}"))
