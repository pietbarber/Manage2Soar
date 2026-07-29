from django.db import transaction

from billing.services import post_flight_charges
from siteconfig.models import SiteConfiguration

from .models import Flight, Logsheet, RevisionLog
from .utils.finalization_email import enqueue_finalization_summary_email_job
from .utils.flight_charges import get_billing_allocations


@transaction.atomic
def finalize_logsheet_financials(
    *, logsheet_id, actor, enqueue_summary=enqueue_finalization_summary_email_job
):
    """Lock costs, post frozen charges, and finalize one logsheet atomically."""
    locked_logsheet = Logsheet.objects.select_for_update().get(pk=logsheet_id)
    if locked_logsheet.finalized:
        return False

    if SiteConfiguration.objects.filter(billing_app_enabled=True).exists():
        # Keep nullable relationships out of the locking query. PostgreSQL rejects
        # FOR UPDATE queries that lock the nullable side of an outer join.
        locked_flights = Flight.objects.select_for_update().filter(
            logsheet=locked_logsheet
        )
        for flight in locked_flights:
            if flight.tow_cost_actual is None:
                flight.tow_cost_actual = flight.tow_cost_calculated
            if flight.rental_cost_actual is None:
                flight.rental_cost_actual = flight.rental_cost
            if flight.instruction_fee_actual is None:
                flight.instruction_fee_actual = flight.instruction_fee_calculated
            flight.save()
            post_flight_charges(
                flight=flight,
                actor=actor,
                allocations=get_billing_allocations(flight),
            )

    locked_logsheet.finalized = True
    locked_logsheet.save()
    RevisionLog.objects.create(
        logsheet=locked_logsheet,
        revised_by=actor,
        note="Logsheet finalized",
    )
    transaction.on_commit(lambda: enqueue_summary(locked_logsheet.pk))
    return True
