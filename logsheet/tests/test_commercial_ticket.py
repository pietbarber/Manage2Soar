import pytest
from django.core.exceptions import ValidationError

from logsheet.models import CommercialRide, CommercialTicket, Flight


@pytest.fixture
def commercial_flight(logsheet):
    return Flight.objects.create(logsheet=logsheet, flight_type="intro")


@pytest.mark.django_db
def test_commercial_ticket_default_available():
    ticket = CommercialTicket.objects.create(ticket_number="T-100")

    assert ticket.status == CommercialTicket.Status.AVAILABLE
    assert ticket.flight is None
    assert ticket.redeemed_at is None
    assert ticket.refunded_at is None


@pytest.mark.django_db
def test_redeemed_ticket_requires_flight():
    ticket = CommercialTicket(
        ticket_number="T-101", status=CommercialTicket.Status.REDEEMED
    )

    with pytest.raises(ValidationError, match="Redeemed tickets must be linked"):
        ticket.save()


@pytest.mark.django_db
def test_refunded_ticket_cannot_have_flight(commercial_flight):
    ticket = CommercialTicket(
        ticket_number="T-102",
        status=CommercialTicket.Status.REFUNDED,
        flight=commercial_flight,
    )

    with pytest.raises(ValidationError, match="Refunded tickets cannot be linked"):
        ticket.save()


@pytest.mark.django_db
def test_transition_available_to_redeemed_sets_flight_and_timestamp(commercial_flight):
    ticket = CommercialTicket.objects.create(ticket_number="T-103")

    ticket.transition_to(CommercialTicket.Status.REDEEMED, flight=commercial_flight)
    ticket.refresh_from_db()

    assert ticket.status == CommercialTicket.Status.REDEEMED
    assert ticket.flight == commercial_flight
    assert ticket.redeemed_at is not None
    assert ticket.refunded_at is None


@pytest.mark.django_db
def test_transition_redeemed_to_refunded_is_blocked_without_override(commercial_flight):
    ticket = CommercialTicket.objects.create(ticket_number="T-104")
    ticket.transition_to(CommercialTicket.Status.REDEEMED, flight=commercial_flight)

    with pytest.raises(ValidationError, match="Invalid ticket transition"):
        ticket.transition_to(CommercialTicket.Status.REFUNDED)


@pytest.mark.django_db
def test_transition_redeemed_to_refunded_with_override_clears_flight(commercial_flight):
    ticket = CommercialTicket.objects.create(ticket_number="T-105")
    ticket.transition_to(CommercialTicket.Status.REDEEMED, flight=commercial_flight)

    ticket.transition_to(CommercialTicket.Status.REFUNDED, allow_admin_override=True)
    ticket.refresh_from_db()

    assert ticket.status == CommercialTicket.Status.REFUNDED
    assert ticket.flight is None
    assert ticket.refunded_at is not None


@pytest.mark.django_db
def test_commercial_ride_save_redeems_available_ticket(logsheet, active_member):
    flight = Flight.objects.create(
        logsheet=logsheet, flight_type="intro", pilot=active_member
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-106")

    ride = CommercialRide.objects.create(
        flight=flight,
        ticket=ticket,
        commercial_pilot=active_member,
        revenue_amount="120.00",
    )

    ticket.refresh_from_db()
    assert ride.ticket == ticket
    assert ticket.status == CommercialTicket.Status.REDEEMED
    assert ticket.flight == flight


@pytest.mark.django_db
def test_commercial_ride_rejects_refunded_ticket(logsheet, active_member):
    flight = Flight.objects.create(
        logsheet=logsheet, flight_type="intro", pilot=active_member
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-107")
    ticket.transition_to(CommercialTicket.Status.REFUNDED, allow_admin_override=True)

    with pytest.raises(ValidationError, match="must be in redeemed status"):
        CommercialRide.objects.create(
            flight=flight,
            ticket=ticket,
            commercial_pilot=active_member,
            revenue_amount="120.00",
        )
