from datetime import date, time
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from logsheet.models import Flight, Glider, Logsheet


@pytest.mark.django_db
def test_updates_rental_when_tow_actual_already_set(airfield, active_member):
    """Backfill rental even if tow actual already has a value."""
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="NTEST001",
        rental_rate=Decimal("20.00"),
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2026, 3, 8),
        airfield=airfield,
        created_by=active_member,
        finalized=True,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        flight_type="dual",
        launch_time=time(10, 0),
        landing_time=time(11, 0),
        tow_cost_actual=Decimal("25.00"),
        rental_cost_actual=Decimal("0.00"),
    )

    call_command("update_flight_costs", after="2026-03-01")

    flight.refresh_from_db()
    assert flight.tow_cost_actual == Decimal("25.00")
    assert flight.rental_cost_actual == Decimal("20.00")


@pytest.mark.django_db
def test_after_filter_is_strictly_greater_than(airfield, active_member):
    """Command should not update logsheets on the exact --after date."""
    glider = Glider.objects.create(
        make="Schempp-Hirth",
        model="Discus",
        n_number="NTEST002",
        rental_rate=Decimal("30.00"),
        club_owned=True,
        is_active=True,
    )
    logsheet = Logsheet.objects.create(
        log_date=date(2026, 3, 7),
        airfield=airfield,
        created_by=active_member,
        finalized=True,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        flight_type="solo",
        launch_time=time(9, 0),
        landing_time=time(10, 0),
        tow_cost_actual=Decimal("0.00"),
        rental_cost_actual=Decimal("0.00"),
    )

    with pytest.raises(CommandError, match="No logsheets found after 2026-03-07"):
        call_command("update_flight_costs", after="2026-03-07")

    flight.refresh_from_db()
    assert flight.tow_cost_actual == Decimal("0.00")
    assert flight.rental_cost_actual == Decimal("0.00")
