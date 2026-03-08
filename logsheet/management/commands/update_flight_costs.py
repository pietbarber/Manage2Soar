from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from logsheet.models import Flight, Logsheet


class Command(BaseCommand):
    help = "Update flight costs for all logsheets after a given date, only if costs are missing or zero."

    def add_arguments(self, parser):
        parser.add_argument(
            "--after",
            type=str,
            required=True,
            help="Update all logsheets with log_date > this date (YYYY-MM-DD)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        after_str = options["after"]
        after_date = parse_date(after_str)
        if not after_date:
            raise CommandError(f"Invalid date format: {after_str}. Use YYYY-MM-DD.")

        logsheets = Logsheet.objects.filter(log_date__gt=after_date).order_by(
            "log_date"
        )
        if not logsheets.exists():
            raise CommandError(f"No logsheets found after {after_str}.")

        total_updated = 0
        for logsheet in logsheets:
            flights = Flight.objects.filter(logsheet=logsheet)
            updated = 0
            for flight in flights:
                tow_actual = getattr(flight, "tow_cost_actual", None)
                rental_actual = getattr(flight, "rental_cost_actual", None)
                should_update_tow = tow_actual is None or tow_actual == 0
                should_update_rental = rental_actual is None or rental_actual == 0

                # Backfill each cost independently so existing values do not
                # block filling the other missing/zero field.
                if should_update_tow or should_update_rental:
                    tow = flight.tow_cost or 0
                    rental = flight.rental_cost or 0

                    if should_update_tow:
                        flight.tow_cost_actual = tow
                    if should_update_rental:
                        flight.rental_cost_actual = rental

                    flight.save()
                    updated += 1
                    self.stdout.write(
                        f"Updated flight ID {flight.pk} (tow: {flight.tow_cost_actual}, rental: {flight.rental_cost_actual})"
                    )
            if updated:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated {updated} flights for logsheet {logsheet} on {logsheet.log_date}"
                    )
                )
            total_updated += updated
        self.stdout.write(
            self.style.SUCCESS(
                f"Total updated flights after {after_str}: {total_updated}"
            )
        )
