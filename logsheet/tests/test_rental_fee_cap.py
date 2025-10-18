from decimal import Decimal

import pytest

from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member


@pytest.mark.django_db
def test_rental_cost_no_cap():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N67890",
        rental_rate=Decimal("50.00"),
        max_rental_rate=None,
    )
    airfield = Airfield.objects.create(identifier="KFRX", name="Other Field")
    towplane = Towplane.objects.create(name="Pawnee2", n_number="N88888")
    creator = Member.objects.create(
        username="creator_user2", first_name="Creator", last_name="User"
    )
    logsheet = Logsheet.objects.create(
        log_date="2025-10-13",
        airfield=airfield,
        created_by=creator,
        default_towplane=towplane,
    )
    from datetime import time

    flight = Flight.objects.create(
        pilot=member,
        glider=glider,
        logsheet=logsheet,
        launch_time=time(10, 0),
        landing_time=time(13, 0),
    )
    flight.refresh_from_db()
    # 3 hours at $50/hr = $150, no cap
    assert flight.rental_cost == Decimal("150.00")


@pytest.mark.django_db
def test_rental_cost_capped_by_max_rental_rate():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N12345",
        rental_rate=Decimal("60.00"),
        max_rental_rate=Decimal("120.00"),
    )
    # 3 hours at $60/hr = $180, but cap is $120
    airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
    towplane = Towplane.objects.create(name="Pawnee", n_number="N99999")
    creator = Member.objects.create(
        username="creator_user", first_name="Creator", last_name="User"
    )
    logsheet = Logsheet.objects.create(
        log_date="2025-10-12",
        airfield=airfield,
        created_by=creator,
        default_towplane=towplane,
    )

    from datetime import time

    flight = Flight.objects.create(
        pilot=member,
        glider=glider,
        logsheet=logsheet,
        launch_time=time(10, 0),
        landing_time=time(13, 0),
    )
    flight.refresh_from_db()
    assert flight.rental_cost == Decimal("120.00")


@pytest.mark.django_db
def test_rental_cost_below_cap():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher",
        model="ASK-21",
        n_number="N54321",
        rental_rate=Decimal("60.00"),
        max_rental_rate=Decimal("200.00"),
    )
    # 2 hours at $60/hr = $120, cap is $200
    from datetime import time

    airfield = Airfield.objects.create(identifier="KFRY", name="Below Cap Field")
    towplane = Towplane.objects.create(name="Pawnee3", n_number="N77777")
    creator = Member.objects.create(
        username="creator_user3", first_name="Creator", last_name="User"
    )
    logsheet = Logsheet.objects.create(
        log_date="2025-10-14",
        airfield=airfield,
        created_by=creator,
        default_towplane=towplane,
    )
    flight = Flight.objects.create(
        pilot=member,
        glider=glider,
        logsheet=logsheet,
        launch_time=time(10, 0),
        landing_time=time(12, 0),
    )
    flight.refresh_from_db()
    assert flight.rental_cost == Decimal("120.00")
