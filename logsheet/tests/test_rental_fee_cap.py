import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from logsheet.models import Glider, Flight
from members.models import Member


@pytest.mark.django_db
def test_rental_cost_capped_by_max_rental_rate():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher", model="ASK-21", n_number="N12345",
        rental_rate=Decimal("60.00"), max_rental_rate=Decimal("120.00")
    )
    # 3 hours at $60/hr = $180, but cap is $120
    flight = Flight.objects.create(
        pilot=member, glider=glider, duration=timedelta(hours=3)
    )
    assert flight.rental_cost == Decimal("120.00")


@pytest.mark.django_db
def test_rental_cost_below_cap():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher", model="ASK-21", n_number="N54321",
        rental_rate=Decimal("60.00"), max_rental_rate=Decimal("200.00")
    )
    # 2 hours at $60/hr = $120, cap is $200
    flight = Flight.objects.create(
        pilot=member, glider=glider, duration=timedelta(hours=2)
    )
    assert flight.rental_cost == Decimal("120.00")


@pytest.mark.django_db
def test_rental_cost_no_cap():
    member = Member.objects.create(first_name="Test", last_name="Pilot")
    glider = Glider.objects.create(
        make="Schleicher", model="ASK-21", n_number="N67890",
        rental_rate=Decimal("50.00"), max_rental_rate=None
    )
    # 3 hours at $50/hr = $150, no cap
    flight = Flight.objects.create(
        pilot=member, glider=glider, duration=timedelta(hours=3)
    )
    assert flight.rental_cost == Decimal("150.00")
