from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date

from logsheet.models import Flight, Logsheet
from siteconfig.models import SiteConfiguration


class Command(BaseCommand):
    help = "Update flight costs for finalized logsheets after a given date, only if costs are missing or zero."

    def add_arguments(self, parser):
        parser.add_argument(
            "--after",
            type=str,
            required=True,
            help="Update finalized logsheets with log_date > this date (YYYY-MM-DD)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        after_str = options["after"]
        after_date = parse_date(after_str)
        if not after_date:
            raise CommandError(f"Invalid date format: {after_str}. Use YYYY-MM-DD.")

        # Only process finalized logsheets so we do not lock in draft costs.
        logsheets = Logsheet.objects.filter(
            log_date__gt=after_date,
            finalized=True,
        ).order_by("log_date")
        if not logsheets.exists():
            raise CommandError(f"No finalized logsheets found after {after_str}.")

        # Cache site configuration once for this run; cost properties read
        # retrieve-waiver flags from this model.
        site_config = SiteConfiguration.objects.first()

        total_updated = 0
        for logsheet in logsheets:
            flights = (
                Flight.objects.filter(logsheet=logsheet)
                .filter(
                    Q(tow_cost_actual__isnull=True)
                    | Q(tow_cost_actual=0)
                    | Q(rental_cost_actual__isnull=True)
                    | Q(rental_cost_actual=0)
                )
                .select_related("glider", "towplane__charge_scheme")
                .prefetch_related("towplane__charge_scheme__charge_tiers")
            )
            updated = 0
            for flight in flights:
                flight._site_config_cache = site_config
                tow_actual = getattr(flight, "tow_cost_actual", None)
                rental_actual = getattr(flight, "rental_cost_actual", None)
                should_update_tow = tow_actual is None or tow_actual == 0
                should_update_rental = rental_actual is None or rental_actual == 0

                # Backfill each cost independently so existing values do not
                # block filling the other missing/zero field.
                if should_update_tow or should_update_rental:
                    updates = []

                    if should_update_tow:
                        tow = flight.tow_cost
                        if tow is not None and tow != flight.tow_cost_actual:
                            flight.tow_cost_actual = tow
                            updates.append("tow_cost_actual")
                    if should_update_rental:
                        rental = flight.rental_cost
                        if rental is not None and rental != flight.rental_cost_actual:
                            flight.rental_cost_actual = rental
                            updates.append("rental_cost_actual")

                    if updates:
                        flight.save(update_fields=updates)
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
